import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.models.insights import ResultBundleV1
from app.models.meeting import MeetingMetadata
from app.services.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotReady,
    LocalArtifactStore,
    MeetingNotFound,
    UnsafePath,
)


def metadata() -> MeetingMetadata:
    return MeetingMetadata.model_validate(
        {
            "title": "Синтетическая встреча",
            "meeting_date": "2026-09-23",
            "timezone": "Asia/Almaty",
            "participants": ["Алия"],
            "recording_notice_confirmed": True,
        }
    )


def bundle(meeting_id: UUID) -> ResultBundleV1:
    payload: dict[str, object] = {
        "schema_version": 1,
        "job_id": str(uuid4()),
        "transcript": {
            "schema_version": 1,
            "meeting_id": str(meeting_id),
            "revision": 0,
            "speakers": [
                {
                    "speaker_id": "speaker_1",
                    "display_name": None,
                    "identity_status": "unreviewed",
                }
            ],
            "segments": [
                {
                    "id": "76424ccb-f8d4-46f2-b7fc-81e888a01775",
                    "start_ms": 100,
                    "end_ms": 900,
                    "speaker_id": "speaker_1",
                    "language": "kk",
                    "text": "Жақсы.",
                    "edited": False,
                }
            ],
        },
        "insights": {
            "schema_version": 1,
            "meeting_id": str(meeting_id),
            "revision": 0,
            "summary": [
                {
                    "id": str(uuid4()),
                    "text": "Согласовано",
                    "evidence": [
                        {
                            "segment_id": "76424ccb-f8d4-46f2-b7fc-81e888a01775",
                            "start_ms": 100,
                            "end_ms": 900,
                        }
                    ],
                }
            ],
            "action_items": [],
        },
        "model_versions": {
            "asr": "fixture@1",
            "diarization": "fixture@1",
            "analysis": "fixture@1",
        },
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    payload["result_hash"] = hashlib.sha256(raw).hexdigest()
    return ResultBundleV1.model_validate(payload)


def test_restart_persists_complete_results_and_owner_isolation(tmp_path: Path) -> None:
    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    meeting = store.create_meeting(owner, metadata(), b"synthetic audio")
    result = bundle(meeting.id)
    store.publish_results(owner, meeting.id, result)
    restarted = LocalArtifactStore(tmp_path)
    assert restarted.read_meeting(owner, meeting.id).status == "review_required"
    assert restarted.read_results(owner, meeting.id) == (
        result.transcript,
        result.insights,
    )
    assert restarted.list_meetings(owner)[0].id == meeting.id
    assert restarted.list_meetings(uuid4()) == []
    with pytest.raises(MeetingNotFound):
        restarted.read_results(uuid4(), meeting.id)
    assert "owner_id" not in restarted.read_meeting(owner, meeting.id).model_dump()


def test_missing_manifest_never_means_ready(tmp_path: Path) -> None:
    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    meeting = store.create_meeting(owner, metadata(), b"synthetic")
    result = bundle(meeting.id)
    store.publish_results(owner, meeting.id, result)
    folder = tmp_path / "users" / str(owner) / "meetings" / str(meeting.id)
    (folder / "manifest.json").unlink()
    restarted = LocalArtifactStore(tmp_path)
    assert restarted.read_meeting(owner, meeting.id).status == "processing"
    with pytest.raises(ArtifactNotReady):
        restarted.read_results(owner, meeting.id)
    restarted.publish_results(owner, meeting.id, result)
    assert restarted.read_results(owner, meeting.id)[0] == result.transcript


def test_hash_corruption_and_machine_output_overwrite_rejected(tmp_path: Path) -> None:
    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    meeting = store.create_meeting(owner, metadata(), b"synthetic")
    result = bundle(meeting.id)
    store.publish_results(owner, meeting.id, result)
    store.publish_results(owner, meeting.id, result)
    with pytest.raises(ArtifactIntegrityError):
        store.publish_results(owner, meeting.id, bundle(meeting.id))
    folder = tmp_path / "users" / str(owner) / "meetings" / str(meeting.id)
    (folder / "transcript.txt").write_text("corrupt")
    with pytest.raises(ArtifactIntegrityError):
        store.read_results(owner, meeting.id)
    with pytest.raises(ArtifactIntegrityError):
        store.read_meeting(owner, meeting.id)


def test_interrupted_write_can_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    meeting = store.create_meeting(owner, metadata(), b"synthetic")
    result = bundle(meeting.id)
    original = store._atomic_write  # pyright: ignore[reportPrivateUsage]

    def interrupted(path: Path, data: bytes, *, immutable: bool = False) -> None:
        if path.name == "insights.json":
            raise OSError("simulated full disk")
        original(path, data, immutable=immutable)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_atomic_write", interrupted)
        with pytest.raises(OSError):
            store.publish_results(owner, meeting.id, result)
    with pytest.raises(ArtifactNotReady):
        LocalArtifactStore(tmp_path).read_results(owner, meeting.id)
    store.publish_results(owner, meeting.id, result)
    assert store.read_manifest(owner, meeting.id).result_hash == result.result_hash


@pytest.mark.parametrize("component", ["users", "owner", "meeting", "artifact"])
def test_rejects_symlinks(tmp_path: Path, component: str) -> None:
    owner = uuid4()
    root = tmp_path / "data"
    store = LocalArtifactStore(root)
    meeting = store.create_meeting(owner, metadata(), b"synthetic")
    paths = {
        "users": root / "users",
        "owner": root / "users" / str(owner),
        "meeting": root / "users" / str(owner) / "meetings" / str(meeting.id),
        "artifact": root
        / "users"
        / str(owner)
        / "meetings"
        / str(meeting.id)
        / "meeting.json",
    }
    selected = paths[component]
    target = tmp_path / "moved"
    selected.rename(target)
    selected.symlink_to(target, target_is_directory=target.is_dir())
    with pytest.raises(UnsafePath):
        store.read_meeting(owner, meeting.id)


def test_traversal_and_incomplete_creation_not_listed(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    owner = uuid4()
    with pytest.raises((ValueError, UnsafePath)):
        store.read_meeting(owner, "../outside")  # type: ignore[arg-type]
    pending = tmp_path / "users" / str(owner) / "meetings" / str(uuid4())
    pending.mkdir(parents=True)
    (pending / "upload.bin").write_bytes(b"incomplete")
    assert store.list_meetings(owner) == []


def test_strict_versions_and_invalid_evidence_rejected() -> None:
    result = bundle(uuid4())
    for version in [True, 2, "1"]:
        payload = result.model_dump(mode="json")
        payload["schema_version"] = version
        with pytest.raises(ValidationError):
            ResultBundleV1.model_validate(payload)
    payload = result.model_dump(mode="json")
    payload["insights"]["summary"][0]["evidence"][0]["end_ms"] = 901
    with pytest.raises(ValidationError):
        ResultBundleV1.model_validate(payload)
    payload = result.model_dump(mode="json")
    payload["result_hash"] = "0" * 64
    with pytest.raises(ValidationError):
        ResultBundleV1.model_validate(payload)


def test_stream_upload_and_fixed_expiry(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta
    from io import BytesIO

    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    stream = BytesIO(b"synthetic" * 200_000)
    meeting = store.create_meeting(owner, metadata(), stream)
    assert not stream.closed
    assert store.upload_path(owner, meeting.id).stat().st_size == 1_800_000
    record = store.read_record(owner, meeting.id)
    record.meeting.temporary_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    store.update_meeting(owner, record)
    assert not store.read_meeting(owner, meeting.id).source_available
    assert store.read_meeting(owner, meeting.id).cleanup_status == "pending"
    with pytest.raises(FileNotFoundError):
        store.upload_path(owner, meeting.id)


def test_staging_path_review_and_pdf_owner_boundaries(tmp_path: Path) -> None:
    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    staged = store.temporary_upload_path()
    staged.write_bytes(b"test synthetic bytes")
    meeting = store.create_meeting(owner, metadata(), staged)
    assert store.upload_path(owner, meeting.id).read_bytes() == b"test synthetic bytes"
    assert store.read_review(owner, meeting.id) is None
    assert store.pdf_path(owner, meeting.id, 2).name == "review-2.pdf"
    with pytest.raises(MeetingNotFound):
        store.review_path(uuid4(), meeting.id)
    with pytest.raises(ValueError):
        store.pdf_path(owner, meeting.id, -1)
    store.review_path(owner, meeting.id).symlink_to(staged)
    with pytest.raises(UnsafePath):
        store.read_review(owner, meeting.id)


def test_retry_archives_previous_attempt_without_overwrite(tmp_path: Path) -> None:
    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    meeting = store.create_meeting(owner, metadata(), b"synthetic")
    first = bundle(meeting.id)
    store.publish_results(owner, meeting.id, first)
    record = store.read_record(owner, meeting.id)
    record.meeting.status = "failed"
    store.update_meeting(owner, record)
    record.meeting.status = "queued"
    record.meeting.attempt = 2
    store.update_meeting(owner, record)
    with pytest.raises(ArtifactNotReady):
        store.read_results(owner, meeting.id)
    second = bundle(meeting.id)
    store.publish_results(owner, meeting.id, second)
    assert store.read_results(owner, meeting.id)[1] == second.insights
    archived = (
        tmp_path
        / "users"
        / str(owner)
        / "meetings"
        / str(meeting.id)
        / "attempts"
        / "1"
    )
    assert (
        json.loads((archived / "manifest.json").read_bytes())["result_hash"]
        == first.result_hash
    )


@pytest.mark.parametrize(
    "change", ["speaker", "bounds", "duplicate", "edited", "extra"]
)
def test_invalid_machine_transcripts_rejected(change: str) -> None:
    payload = bundle(uuid4()).model_dump(mode="json")
    transcript = payload["transcript"]
    if change == "speaker":
        transcript["segments"][0]["speaker_id"] = "speaker_2"
    elif change == "bounds":
        transcript["segments"][0]["end_ms"] = 100
    elif change == "duplicate":
        transcript["segments"].append(transcript["segments"][0])
    elif change == "edited":
        transcript["segments"][0]["edited"] = True
    else:
        transcript["unrecognized"] = "data"
    unsigned = {key: value for key, value in payload.items() if key != "result_hash"}
    payload["result_hash"] = hashlib.sha256(
        json.dumps(
            unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    with pytest.raises(ValidationError):
        ResultBundleV1.model_validate(payload)


def test_documented_canonical_hash_vector() -> None:
    result = ResultBundleV1.model_validate(
        {
            "schema_version": 1,
            "job_id": "c0b59629-8ca7-453d-812c-70e3c9e970ac",
            "transcript": {
                "schema_version": 1,
                "meeting_id": "81df6d39-16dd-4227-98b0-d45e531e091e",
                "revision": 0,
                "speakers": [],
                "segments": [],
            },
            "insights": {
                "schema_version": 1,
                "meeting_id": "81df6d39-16dd-4227-98b0-d45e531e091e",
                "revision": 0,
                "summary": [],
                "action_items": [],
            },
            "model_versions": {
                "asr": "fixture-asr@1",
                "diarization": "fixture-diarization@1",
                "analysis": "fixture-analysis@1",
            },
            "result_hash": (
                "d25981e522342820a7f13aa73ef6ad1cd92f432fd06b5cd31fe46786fcb11a94"
            ),
        }
    )
    assert result.transcript.segments == []


def test_missing_artifact_with_manifest_is_corrupt(tmp_path: Path) -> None:
    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    meeting = store.create_meeting(owner, metadata(), b"synthetic")
    store.publish_results(owner, meeting.id, bundle(meeting.id))
    folder = tmp_path / "users" / str(owner) / "meetings" / str(meeting.id)
    (folder / "insights.json").unlink()
    with pytest.raises(ArtifactIntegrityError):
        LocalArtifactStore(tmp_path).read_results(owner, meeting.id)


def test_interrupted_upload_stays_invisible(tmp_path: Path) -> None:
    from io import BytesIO

    class BrokenUpload(BytesIO):
        def read(self, size: int | None = -1, /) -> bytes:
            raise OSError("simulated stream failure")

    store = LocalArtifactStore(tmp_path)
    owner = uuid4()
    with pytest.raises(OSError):
        store.create_meeting(owner, metadata(), BrokenUpload(b"synthetic"))
    assert LocalArtifactStore(tmp_path).list_meetings(owner) == []


@pytest.mark.parametrize("sync_point", ["meeting_folder", "meetings_parent"])
def test_post_rename_creation_sync_failure_stays_invisible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sync_point: str
) -> None:
    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    original = store._sync_directory  # pyright: ignore[reportPrivateUsage]
    meetings_parent = tmp_path / "users" / str(owner) / "meetings"
    failed = False

    def fail_after_rename(path: Path) -> None:
        nonlocal failed
        folders = list(meetings_parent.iterdir()) if meetings_parent.exists() else []
        committed = any((folder / "meeting.json").exists() for folder in folders)
        target = (
            path.parent == meetings_parent
            if sync_point == "meeting_folder"
            else path == meetings_parent
        )
        if target and committed and not failed:
            failed = True
            raise OSError("synthetic post-rename sync failure")
        original(path)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_sync_directory", fail_after_rename)
        with pytest.raises(OSError, match="post-rename"):
            store.create_meeting(owner, metadata(), b"synthetic")
    assert failed
    restarted = LocalArtifactStore(tmp_path)
    assert restarted.list_meetings(owner) == []
    assert not list(meetings_parent.glob("*/meeting.json"))


def test_evidence_validation_independent_of_bundle_hash() -> None:
    from app.models.insights import InsightsV1

    result = bundle(uuid4())
    for field, value in [
        ("end_ms", 901),
        ("start_ms", 99),
        ("segment_id", str(uuid4())),
    ]:
        data = result.insights.model_dump(mode="json")
        data["summary"][0]["evidence"][0][field] = value
        insights = InsightsV1.model_validate(data)
        with pytest.raises(ValueError, match="Evidence"):
            insights.validate_against(result.transcript)


def test_machine_text_bytes_are_not_normalized_before_hashing() -> None:
    data = bundle(uuid4()).model_dump(mode="json")
    data["transcript"]["segments"][0]["text"] = "  Жақсы.  "
    unsigned = {key: value for key, value in data.items() if key != "result_hash"}
    data["result_hash"] = hashlib.sha256(
        json.dumps(
            unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    assert (
        ResultBundleV1.model_validate(data).transcript.segments[0].text == "  Жақсы.  "
    )


def test_manifest_sync_failure_blocks_ack_on_every_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    meeting = store.create_meeting(owner, metadata(), b"synthetic")
    result = bundle(meeting.id)
    folder = tmp_path / "users" / str(owner) / "meetings" / str(meeting.id)
    original = store._sync_directory  # pyright: ignore[reportPrivateUsage]

    def fail_manifest_sync(path: Path) -> None:
        if path == folder and (folder / "manifest.json").exists():
            raise OSError("manifest directory sync failed")
        original(path)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_sync_directory", fail_manifest_sync)
        with pytest.raises(OSError, match="manifest directory"):
            store.publish_results(owner, meeting.id, result)
        assert (folder / "manifest.json").exists()
        with pytest.raises(OSError, match="manifest directory"):
            store.publish_results(owner, meeting.id, result)
    assert (
        store.publish_results(owner, meeting.id, result).result_hash
        == result.result_hash
    )


def test_identical_artifact_retry_reestablishes_durability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalArtifactStore(tmp_path)
    target = tmp_path / "transcript.txt"

    def fail_sync(_path: Path) -> None:
        raise OSError("directory sync failed")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_sync_directory", fail_sync)
        for _ in range(2):
            with pytest.raises(OSError, match="directory sync"):
                store._atomic_write(target, b"synthetic", immutable=True)  # pyright: ignore[reportPrivateUsage]
    assert target.read_bytes() == b"synthetic"


def test_archive_ancestor_sync_failure_preserves_originals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    meeting = store.create_meeting(owner, metadata(), b"synthetic")
    result = bundle(meeting.id)
    store.publish_results(owner, meeting.id, result)
    record = store.read_record(owner, meeting.id)
    record.meeting.status = "failed"
    store.update_meeting(owner, record)
    record.meeting.status = "queued"
    record.meeting.attempt = 2
    folder = tmp_path / "users" / str(owner) / "meetings" / str(meeting.id)
    original = store._sync_directory  # pyright: ignore[reportPrivateUsage]

    def fail_archive_parent(path: Path) -> None:
        if path == folder / "attempts":
            raise OSError("archive ancestor sync failed")
        original(path)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_sync_directory", fail_archive_parent)
        for _ in range(2):
            with pytest.raises(OSError, match="archive ancestor"):
                store.update_meeting(owner, record)
            assert (folder / "manifest.json").exists()
            assert (folder / "transcript.json").exists()
            assert store.read_record(owner, meeting.id).meeting.attempt == 1
    store.update_meeting(owner, record)
    assert store.read_record(owner, meeting.id).meeting.attempt == 2
    assert (folder / "attempts" / "1" / "transcript.json").exists()


def test_new_storage_and_owner_ancestors_are_synced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synced: list[Path] = []
    original = LocalArtifactStore._sync_directory  # pyright: ignore[reportPrivateUsage]

    def record_sync(path: Path) -> None:
        original(path)
        synced.append(path)

    monkeypatch.setattr(
        LocalArtifactStore, "_sync_directory", staticmethod(record_sync)
    )
    root = tmp_path / "new-parent" / "data"
    store = LocalArtifactStore(root)
    owner = uuid4()
    meeting = store.create_meeting(owner, metadata(), b"synthetic")
    folder = root / "users" / str(owner) / "meetings" / str(meeting.id)
    assert {
        tmp_path,
        root.parent,
        root,
        root / "users",
        root / "users" / str(owner),
        folder.parent,
        folder,
    } <= set(synced)


def action_bundle_data() -> dict[str, object]:
    result = bundle(uuid4()).model_dump(mode="json")
    item = result["insights"]["summary"][0]
    result["insights"]["action_items"] = [
        {
            **item,
            "assignee_speaker_id": None,
            "assignee_name": "Бухгалтерия",
            "due_date": "1970-01-01",
            "due_date_text": None,
        }
    ]
    unsigned = {key: value for key, value in result.items() if key != "result_hash"}
    result["result_hash"] = hashlib.sha256(
        json.dumps(
            unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return result


def test_raw_hash_rejects_fields_that_normalize_to_a_different_signed_value() -> None:
    for field, value in [("due_date", 0), ("assignee_name", " Бухгалтерия ")]:
        data = ResultBundleV1.model_validate(action_bundle_data()).model_dump(
            mode="json"
        )
        data["insights"]["action_items"][0][field] = value
        # Keep the original hash: coerced values must not pass its verification.
        with pytest.raises(ValidationError, match="hash"):
            ResultBundleV1.model_validate(data)


def test_raw_signed_numeric_date_and_padded_name_are_rejected() -> None:
    for field, value in [("due_date", 0), ("assignee_name", " Бухгалтерия ")]:
        data = ResultBundleV1.model_validate(action_bundle_data()).model_dump(
            mode="json"
        )
        data["insights"]["action_items"][0][field] = value
        unsigned = {key: value for key, value in data.items() if key != "result_hash"}
        data["result_hash"] = hashlib.sha256(
            json.dumps(
                unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        with pytest.raises(ValidationError, match="due_date|assignee_name"):
            ResultBundleV1.model_validate(data)


def test_failed_directory_creation_sync_cannot_expose_a_meeting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    original = store._sync_directory  # pyright: ignore[reportPrivateUsage]

    def fail_owner_ancestor(path: Path) -> None:
        if path == tmp_path / "users":
            raise OSError("owner ancestor sync failed")
        original(path)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_sync_directory", fail_owner_ancestor)
        for _ in range(2):
            with pytest.raises(OSError, match="owner ancestor"):
                store.create_meeting(owner, metadata(), b"synthetic")
            assert store.list_meetings(owner) == []
    meeting = store.create_meeting(owner, metadata(), b"synthetic")
    assert store.list_meetings(owner)[0].id == meeting.id
