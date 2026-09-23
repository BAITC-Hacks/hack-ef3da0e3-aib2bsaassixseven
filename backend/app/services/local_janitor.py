"""Periodic, conservative removal of local temporary meeting data."""

import os
import re
import shutil
import stat
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.models.meeting import MeetingRecord
from app.services.artifact_store import (
    ArtifactIntegrityError,
    LocalArtifactStore,
    MeetingNotFound,
    UnsafePath,
)

_DAY_SECONDS = 24 * 60 * 60
_TOMBSTONE = re.compile(r"\.deleted-([0-9a-f-]{36})-([0-9a-f-]{36})\Z")


def _canonical_uuid(name: str) -> UUID | None:
    try:
        parsed = UUID(name)
    except ValueError:
        return None
    return parsed if str(parsed) == name else None


def _regular_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _stale_tree(path: Path, cutoff: float) -> bool:
    """Do not remove a directory with recent entries or any symlink."""
    try:
        for current, dirs, files in os.walk(path, followlinks=False):
            for name in ["", *dirs, *files]:
                candidate = Path(current) / name if name else Path(current)
                info = candidate.lstat()
                if stat.S_ISLNK(info.st_mode) or info.st_mtime >= cutoff:
                    return False
        return True
    except OSError:
        return False


class LocalJanitor:
    def __init__(self, store: LocalArtifactStore) -> None:
        self.store = store

    def sweep(self) -> None:
        """Run under the shared coordinator lock; retry failures on later ticks."""
        with suppress(OSError, UnsafePath):
            self.store.sweep_stale_uploads()
        users = self.store.root / "users"
        if not _regular_directory(users):
            return
        cutoff = time.time() - _DAY_SECONDS
        try:
            owner_dirs = list(users.iterdir())
        except OSError:
            return
        for owner_dir in owner_dirs:
            owner_id = _canonical_uuid(owner_dir.name)
            if owner_id is None or not _regular_directory(owner_dir):
                continue
            meetings = owner_dir / "meetings"
            if not _regular_directory(meetings):
                continue
            try:
                entries = list(meetings.iterdir())
            except OSError:
                continue
            for entry in entries:
                try:
                    self._sweep_entry(owner_id, entry, cutoff)
                except (OSError, UnsafePath, ArtifactIntegrityError, MeetingNotFound):
                    continue

    def _sweep_entry(self, owner_id: UUID, entry: Path, cutoff: float) -> None:
        if not _regular_directory(entry):
            return
        tombstone = _TOMBSTONE.fullmatch(entry.name)
        if tombstone is not None:
            if all(_canonical_uuid(name) is not None for name in tombstone.groups()):
                shutil.rmtree(entry)
                _sync_directory(entry.parent)
            return
        meeting_id = _canonical_uuid(entry.name)
        if meeting_id is None:
            return
        marker = entry / "meeting.json"
        try:
            marker.lstat()
        except FileNotFoundError:
            if _stale_tree(entry, cutoff):
                shutil.rmtree(entry)
                _sync_directory(entry.parent)
            return
        with self.store.lifecycle_lock(
            owner_id, meeting_id, blocking=False
        ) as acquired:
            if acquired:
                self._expire_upload(owner_id, meeting_id)

    def _expire_upload(self, owner_id: UUID, meeting_id: UUID) -> None:
        record = self.store.read_record(owner_id, meeting_id)
        expires_at = record.meeting.temporary_expires_at
        now = datetime.now(UTC)
        if (
            record.local_cleanup_status != "pending"
            or expires_at is None
            or now < expires_at
        ):
            return
        try:
            self.store.delete_upload(owner_id, meeting_id)
        except OSError:
            # The deadline has passed even if physical cleanup must be retried.
            record.meeting.source_available = False
            record.meeting.updated_at = now
            self.store.update_meeting(owner_id, record)
            return
        self._record_expiry(record, now)
        self.store.update_meeting(owner_id, record)

    @staticmethod
    def _record_expiry(record: MeetingRecord, now: datetime) -> None:
        record.local_cleanup_status = "expired"
        record.meeting.source_available = False
        record.meeting.updated_at = now
        for job in record.jobs:
            if job.job_id is None and job.cleanup_status == "pending":
                job.cleanup_status = "expired"
        states = [
            record.local_cleanup_status,
            *(job.cleanup_status for job in record.jobs),
        ]
        record.meeting.cleanup_status = (
            "pending"
            if "pending" in states
            else "expired"
            if "expired" in states
            else "deleted"
        )
