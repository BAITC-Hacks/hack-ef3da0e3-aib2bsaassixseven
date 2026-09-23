"""Durable local artifacts for the single coordinator MVP.

Only server-generated UUIDs form directory names. Original result files are
write-once; identical publication retries are safe. A verified manifest is the
commit marker. Callers must map these exceptions to safe public error codes.
"""

import fcntl
import hashlib
import io
import os
import shutil
import stat
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.core.config import Settings
from app.models.insights import InsightsV1, ResultBundleV1, canonical_json
from app.models.meeting import (
    ArtifactHashes,
    JobRecord,
    Meeting,
    MeetingMetadata,
    MeetingRecord,
    MeetingSource,
    ReadyManifest,
)
from app.models.transcript import TranscriptV1


class MeetingNotFound(Exception):
    """No committed meeting exists in this owner's namespace."""


class ArtifactNotReady(Exception):
    """No complete result has been committed for the current attempt."""


class ArtifactIntegrityError(Exception):
    """Stored contents are corrupt, inconsistent, or an immutable write conflicts."""


class UnsafePath(ValueError):
    """The artifact tree contains a symlink or non-regular file."""


class LocalArtifactStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root if root is not None else Settings().data_root).absolute()
        for ancestor in [*reversed(self.root.parents), self.root]:
            if ancestor.is_symlink():
                raise UnsafePath("Symlink in storage root")
        self._make_directory(self.root)

    def _check(self, path: Path) -> Path:
        try:
            relative = path.relative_to(self.root)
        except ValueError as error:
            raise UnsafePath("Path outside storage root") from error
        if ".." in relative.parts:
            raise UnsafePath("Traversal is forbidden")
        for ancestor in self.root.parents:
            if ancestor.is_symlink():
                raise UnsafePath("Symlink in storage ancestor")
        current = self.root
        for part in ("", *relative.parts):
            if part:
                current /= part
            if current.is_symlink():
                raise UnsafePath("Symlink in artifact path")
            if current.exists() and not (current.is_dir() or current.is_file()):
                raise UnsafePath("Non-regular artifact")
        return path

    def _folder(self, owner_id: UUID, meeting_id: UUID) -> Path:
        # Reparse to protect runtime callers that bypass type checking.
        owner = UUID(str(owner_id))
        meeting = UUID(str(meeting_id))
        return self._check(self.root / "users" / str(owner) / "meetings" / str(meeting))

    def _read(self, path: Path) -> bytes:
        self._check(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise UnsafePath("Non-regular artifact")
            return stream.read()

    @staticmethod
    def _sync_directory(path: Path) -> None:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _make_directory(self, path: Path) -> None:
        """Make every ancestor durable, even if a prior mkdir/fsync was interrupted."""
        self._check(path)
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Sync existing ancestors too: existence does not prove a previous sync
        # succeeded, including when retrying construction of the storage root.
        for directory in (path, *path.parents):
            self._sync_directory(directory)

    def _sync_file(self, path: Path) -> None:
        self._check(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise UnsafePath("Non-regular artifact")
            os.fsync(fd)
        finally:
            os.close(fd)

    def _atomic_write(
        self, path: Path, data: bytes, *, immutable: bool = False
    ) -> None:
        self._check(path)
        if immutable and path.exists():
            if self._read(path) != data:
                raise ArtifactIntegrityError("Original artifact already exists")
            self._sync_file(path)
            self._sync_directory(path.parent)
            return
        fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            self._check(path)
            if immutable:
                try:
                    os.link(temporary, path, follow_symlinks=False)
                except FileExistsError:
                    if self._read(path) != data:
                        raise ArtifactIntegrityError(
                            "Original artifact conflict"
                        ) from None
                    self._sync_file(path)
            else:
                os.replace(temporary, path)
            self._sync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def temporary_upload_path(self) -> Path:
        """Reserve a private staging file; caller streams and enforces upload cap.

        Caller owns removal of this staging file after create_meeting succeeds or
        fails. Client filenames must never be passed into this interface.
        """
        staging = self._check(self.root / "uploads")
        self._make_directory(staging)
        self._sweep_stale_uploads(staging)
        path = self._check(staging / f"{uuid4()}.upload")
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        return path

    def _sweep_stale_uploads(self, staging: Path) -> None:
        """Best-effort cleanup of private staging files older than 24 hours.

        A failed unlink after a committed upload must not change its HTTP result.
        Such files remain private and are retried on a later upload or timer tick.
        """
        cutoff = time.time() - 24 * 60 * 60
        removed = False
        for path in staging.iterdir():
            if path.suffix != ".upload":
                continue
            try:
                UUID(path.stem)
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_mtime >= cutoff:
                    continue
                path.unlink()
                removed = True
            except (ValueError, OSError):
                continue
        if removed:
            with suppress(OSError):
                self._sync_directory(staging)

    def sweep_stale_uploads(self) -> None:
        """Sweep private staging on a timer, even when no new upload arrives."""
        staging = self._check(self.root / "uploads")
        if staging.is_dir():
            self._sweep_stale_uploads(staging)

    def create_meeting(
        self,
        owner_id: UUID,
        metadata: MeetingMetadata,
        audio: BinaryIO | bytes | Path,
        *,
        retention_hours: int = 24,
    ) -> Meeting:
        """Commit upload and queued coordinator state before exposing a meeting.

        Stream/file inputs are copied in 1 MiB chunks. Paths must be staging files
        under this store root. Content validation and size limits belong to upload.
        """
        metadata = MeetingMetadata.model_validate(metadata.model_dump())
        if retention_hours <= 0:
            raise ValueError("Retention must be positive")
        meeting_id = uuid4()
        folder = self._folder(owner_id, meeting_id)
        self._make_directory(folder)
        now = datetime.now(UTC)
        meeting = Meeting(
            **metadata.model_dump(),
            id=meeting_id,
            created_at=now,
            updated_at=now,
            attempt=1,
            revision=0,
            status="queued",
            stage=None,
            source_available=True,
            cleanup_status="pending",
            temporary_expires_at=now + timedelta(hours=retention_hours),
            source=MeetingSource(kind="uploaded_audio"),
            failure=None,
        )
        close_source = isinstance(audio, bytes | Path)
        if isinstance(audio, Path):
            self._check(audio)
            source = os.fdopen(os.open(audio, os.O_RDONLY | os.O_NOFOLLOW), "rb")
        elif isinstance(audio, bytes):
            source = io.BytesIO(audio)
        else:
            source = audio
        digest = hashlib.sha256()
        target = self._check(folder / "upload.bin")
        try:
            fd = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(fd, "wb") as output:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        finally:
            if close_source:
                source.close()
        record = MeetingRecord(
            schema_version=1,
            owner_id=owner_id,
            meeting=meeting,
            audio_sha256=digest.hexdigest(),
            local_cleanup_status="pending",
            jobs=[JobRecord(attempt=1)],
        )
        marker = self._check(folder / "meeting.json")
        try:
            self._atomic_write(marker, record.model_dump_json().encode())
            self._sync_directory(folder.parent)
        except BaseException:
            # _atomic_write may have renamed meeting.json before a directory
            # fsync failed. Remove the visibility marker before reporting a
            # failed creation, so readers never see an unacknowledged meeting.
            marker.unlink(missing_ok=True)
            self._sync_directory(folder)
            self._sync_directory(folder.parent)
            raise
        return meeting

    def read_record(self, owner_id: UUID, meeting_id: UUID) -> MeetingRecord:
        folder = self._folder(owner_id, meeting_id)
        try:
            record = MeetingRecord.model_validate_json(
                self._read(folder / "meeting.json")
            )
        except FileNotFoundError as error:
            raise MeetingNotFound() from error
        except ValidationError as error:
            raise ArtifactIntegrityError("Invalid meeting state") from error
        if record.owner_id != owner_id or record.meeting.id != meeting_id:
            raise MeetingNotFound()
        return record

    def read_meeting(self, owner_id: UUID, meeting_id: UUID) -> Meeting:
        meeting = self.read_record(owner_id, meeting_id).meeting
        if meeting.status in {"review_required", "approved"}:
            try:
                self.read_results(owner_id, meeting_id)
            except ArtifactNotReady:
                meeting = meeting.model_copy(
                    update={"status": "processing", "stage": "saving_results"}
                )
        upload = self._check(self._folder(owner_id, meeting_id) / "upload.bin")
        available = (
            upload.is_file()
            and meeting.temporary_expires_at is not None
            and datetime.now(UTC) < meeting.temporary_expires_at
        )
        return meeting.model_copy(update={"source_available": available})

    def list_meetings(self, owner_id: UUID) -> list[Meeting]:
        owner_id = UUID(str(owner_id))
        parent = self._check(self.root / "users" / str(owner_id) / "meetings")
        if not parent.exists():
            return []
        meetings: list[Meeting] = []
        for folder in parent.iterdir():
            self._check(folder)
            try:
                meeting_id = UUID(folder.name)
            except ValueError:
                continue
            try:
                meetings.append(self.read_meeting(owner_id, meeting_id))
            except MeetingNotFound:
                continue
        return sorted(
            meetings,
            key=lambda meeting: (meeting.created_at, str(meeting.id)),
            reverse=True,
        )

    def update_meeting(self, owner_id: UUID, record: MeetingRecord) -> Meeting:
        """Persist validated internal state; caller owns lifecycle transition rules."""
        record = MeetingRecord.model_validate_json(record.model_dump_json())
        old = self.read_record(owner_id, record.meeting.id)
        if (
            record.owner_id != owner_id
            or record.meeting.created_at != old.meeting.created_at
        ):
            raise ValueError("Immutable meeting identity changed")
        if record.meeting.attempt != old.meeting.attempt:
            if not (
                old.meeting.status == "failed"
                and record.meeting.status == "queued"
                and record.meeting.attempt == old.meeting.attempt + 1
            ):
                raise ValueError("Attempt changes require failed-to-queued retry")
            self._archive_attempt(owner_id, old)
        if record.meeting.status in {"review_required", "approved"}:
            self.read_results(owner_id, record.meeting.id)
        path = self._folder(owner_id, record.meeting.id) / "meeting.json"
        self._atomic_write(path, record.model_dump_json().encode())
        return self.read_meeting(owner_id, record.meeting.id)

    def _archive_attempt(self, owner_id: UUID, old: MeetingRecord) -> None:
        """Preserve prior originals before changing attempts; resumable on failure."""
        folder = self._folder(owner_id, old.meeting.id)
        archive = self._check(folder / "attempts" / str(old.meeting.attempt))
        self._make_directory(archive)
        self._atomic_write(
            archive / "meeting.json", old.model_dump_json().encode(), immutable=True
        )
        # Remove the commit marker first: remaining partial originals are never ready.
        for name in (
            "manifest.json",
            "transcript.json",
            "insights.json",
            "transcript.txt",
        ):
            source = self._check(folder / name)
            if source.exists():
                self._atomic_write(archive / name, self._read(source), immutable=True)
                source.unlink()
                self._sync_directory(folder)
        self._sync_directory(archive.parent)

    def upload_path(self, owner_id: UUID, meeting_id: UUID) -> Path:
        """Return temporary audio only while present and before its fixed deadline."""
        if not self.read_meeting(owner_id, meeting_id).source_available:
            raise FileNotFoundError("Temporary source unavailable")
        return self._check(self._folder(owner_id, meeting_id) / "upload.bin")

    def upload_present(self, owner_id: UUID, meeting_id: UUID) -> bool:
        """Check physical source presence even after the upload TTL."""
        self.read_record(owner_id, meeting_id)
        return self._check(self._folder(owner_id, meeting_id) / "upload.bin").exists()

    def delete_upload(self, owner_id: UUID, meeting_id: UUID) -> None:
        """Remove and durably sync the upload; caller tracks cleanup state.

        Idempotent even after unlink succeeded but directory fsync failed.
        Unlike upload_path, cleanup also works after the source deadline.
        """
        self.read_record(owner_id, meeting_id)
        folder = self._folder(owner_id, meeting_id)
        self._check(folder / "upload.bin").unlink(missing_ok=True)
        self._sync_directory(folder)

    @contextmanager
    def lifecycle_lock(
        self, owner_id: UUID, meeting_id: UUID, *, blocking: bool = True
    ) -> Generator[bool]:
        """Serialize all mutations of a meeting across API workers."""
        self.read_record(owner_id, meeting_id)
        path = self._check(self._folder(owner_id, meeting_id) / ".lifecycle.lock")
        try:
            fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        except FileNotFoundError as error:
            # A DELETE may have moved the meeting after the authorization read.
            raise MeetingNotFound() from error
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise UnsafePath("Non-regular lifecycle lock")
            flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            try:
                fcntl.flock(fd, flags)
            except BlockingIOError:
                yield False
            else:
                yield True
        finally:
            os.close(fd)

    @contextmanager
    def coordinator_lock(self) -> Generator[bool]:
        """Allow one scheduler tick across all processes sharing this data root."""
        path = self._check(self.root / ".coordinator.lock")
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise UnsafePath("Non-regular coordinator lock")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
            else:
                yield True
        finally:
            os.close(fd)

    def delete_meeting(self, owner_id: UUID, meeting_id: UUID) -> None:
        """Durably hide a completed meeting, then remove its local artifacts.

        A private tombstone survives interrupted physical removal. A later
        housekeeping sweep may finish removing it without exposing the meeting.
        """
        self.read_record(owner_id, meeting_id)
        folder = self._folder(owner_id, meeting_id)
        tombstone = self._check(folder.parent / f".deleted-{meeting_id}-{uuid4()}")
        os.rename(folder, tombstone)
        try:
            self._sync_directory(folder.parent)
        except OSError:
            os.rename(tombstone, folder)
            self._sync_directory(folder.parent)
            raise
        try:
            shutil.rmtree(tombstone)
            self._sync_directory(folder.parent)
        except OSError:
            # The logical deletion is durable. Physical removal is retried by
            # periodic maintenance; never restore a partially deleted folder.
            pass

    def publish_results(
        self, owner_id: UUID, meeting_id: UUID, bundle: ResultBundleV1
    ) -> ReadyManifest:
        """Validate, fsync originals, verify bytes, then publish manifest last.

        A successful return is the only permission for the coordinator to ACK.
        The original files never change; retries may only write identical bytes.
        """
        bundle = ResultBundleV1.model_validate_json(bundle.model_dump_json())
        record = self.read_record(owner_id, meeting_id)
        if bundle.transcript.meeting_id != meeting_id:
            raise ArtifactIntegrityError("Result belongs to another meeting")
        job = next(
            (job for job in record.jobs if job.attempt == record.meeting.attempt), None
        )
        if job is not None and job.job_id is not None and job.job_id != bundle.job_id:
            raise ArtifactIntegrityError("Result belongs to another job")
        folder = self._folder(owner_id, meeting_id)
        manifest_path = self._check(folder / "manifest.json")
        if manifest_path.exists():
            manifest = self.read_manifest(owner_id, meeting_id)
            if manifest.result_hash != bundle.result_hash:
                raise ArtifactIntegrityError("Result already published")
            self.read_results(owner_id, meeting_id)
            # A prior link/replace may have succeeded before directory fsync
            # failed. Verified reads alone never authorize ACK after that failure.
            for name in (
                "transcript.json",
                "insights.json",
                "transcript.txt",
                "meeting.json",
                "manifest.json",
            ):
                self._sync_file(folder / name)
            self._make_directory(folder)
            return manifest
        artifacts = {
            "transcript.json": canonical_json(
                bundle.transcript.model_dump(mode="json")
            ),
            "insights.json": canonical_json(bundle.insights.model_dump(mode="json")),
            "transcript.txt": "\n".join(
                f"[{s.start_ms}-{s.end_ms}] {s.speaker_id}: {s.text}"
                for s in bundle.transcript.segments
            ).encode("utf-8"),
        }
        hashes = {
            name: hashlib.sha256(data).hexdigest() for name, data in artifacts.items()
        }
        for name, data in artifacts.items():
            self._atomic_write(folder / name, data, immutable=True)
            if hashlib.sha256(self._read(folder / name)).hexdigest() != hashes[name]:
                raise ArtifactIntegrityError("Artifact verification failed")
        manifest = ReadyManifest(
            schema_version=1,
            owner_id=owner_id,
            meeting_id=meeting_id,
            attempt=record.meeting.attempt,
            job_id=bundle.job_id,
            result_hash=bundle.result_hash,
            model_versions=bundle.model_versions,
            artifacts=ArtifactHashes(
                transcript_json=hashes["transcript.json"],
                insights_json=hashes["insights.json"],
                transcript_txt=hashes["transcript.txt"],
            ),
        )
        record.meeting = record.meeting.model_copy(
            update={
                "status": "review_required",
                "stage": None,
                "updated_at": datetime.now(UTC),
                "failure": None,
            }
        )
        if job is None:
            job = JobRecord(attempt=record.meeting.attempt)
            record.jobs.append(job)
        job.job_id = bundle.job_id
        job.result_hash = bundle.result_hash
        job.ack_pending = True
        self._atomic_write(folder / "meeting.json", record.model_dump_json().encode())
        self._atomic_write(
            manifest_path, manifest.model_dump_json().encode(), immutable=True
        )
        return manifest

    def read_manifest(self, owner_id: UUID, meeting_id: UUID) -> ReadyManifest:
        record = self.read_record(owner_id, meeting_id)
        try:
            manifest = ReadyManifest.model_validate_json(
                self._read(self._folder(owner_id, meeting_id) / "manifest.json")
            )
        except FileNotFoundError as error:
            raise ArtifactNotReady() from error
        except ValidationError as error:
            raise ArtifactIntegrityError("Invalid ready manifest") from error
        if manifest.owner_id != owner_id or manifest.meeting_id != meeting_id:
            raise ArtifactIntegrityError("Manifest identity mismatch")
        if manifest.attempt != record.meeting.attempt:
            raise ArtifactNotReady()
        return manifest

    def read_results(
        self, owner_id: UUID, meeting_id: UUID
    ) -> tuple[TranscriptV1, InsightsV1]:
        manifest = self.read_manifest(owner_id, meeting_id)
        folder = self._folder(owner_id, meeting_id)
        expected = {
            "transcript.json": manifest.artifacts.transcript_json,
            "insights.json": manifest.artifacts.insights_json,
            "transcript.txt": manifest.artifacts.transcript_txt,
        }
        contents: dict[str, bytes] = {}
        for name, expected_hash in expected.items():
            try:
                contents[name] = self._read(folder / name)
            except FileNotFoundError as error:
                raise ArtifactIntegrityError("Committed artifact missing") from error
            if hashlib.sha256(contents[name]).hexdigest() != expected_hash:
                raise ArtifactIntegrityError("Artifact hash mismatch")
        try:
            transcript = TranscriptV1.model_validate_json(contents["transcript.json"])
            insights = InsightsV1.model_validate_json(contents["insights.json"])
            ResultBundleV1(
                schema_version=1,
                job_id=manifest.job_id,
                transcript=transcript,
                insights=insights,
                model_versions=manifest.model_versions,
                result_hash=manifest.result_hash,
            )
        except ValueError as error:
            raise ArtifactIntegrityError("Invalid committed result") from error
        if transcript.meeting_id != meeting_id:
            raise ArtifactIntegrityError("Artifact meeting mismatch")
        return transcript, insights

    def review_path(self, owner_id: UUID, meeting_id: UUID) -> Path:
        """Private path for later review transaction implementation."""
        self.read_record(owner_id, meeting_id)
        return self._check(self._folder(owner_id, meeting_id) / "review.json")

    def read_review(self, owner_id: UUID, meeting_id: UUID) -> bytes | None:
        """Read raw review bytes; the review service owns its versioned schema."""
        path = self.review_path(owner_id, meeting_id)
        try:
            return self._read(path)
        except FileNotFoundError:
            return None

    def pdf_path(self, owner_id: UUID, meeting_id: UUID, revision: int) -> Path:
        """Private revision-specific PDF cache path; authorization belongs to export."""
        if type(revision) is not int or revision < 0:
            raise ValueError("Invalid revision")
        self.read_record(owner_id, meeting_id)
        return self._check(
            self._folder(owner_id, meeting_id) / f"review-{revision}.pdf"
        )
