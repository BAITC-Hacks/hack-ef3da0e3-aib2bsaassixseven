"""Review transactions use synthetic result data only."""

import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.models.insights import ResultBundleV1
from app.models.meeting import MeetingMetadata
from app.services.artifact_store import LocalArtifactStore
from app.services.reviews import (
    ApprovalRequest,
    ReviewConflict,
    ReviewRequest,
    ReviewValidationError,
    approve_review,
    read_reviewed_results,
    read_reviewed_results_unlocked,
    update_review,
)

SEGMENT_ID = UUID("76424ccb-f8d4-46f2-b7fc-81e888a01775")


def _ready_store(tmp_path: Path) -> tuple[LocalArtifactStore, UUID, UUID]:
    owner = uuid4()
    store = LocalArtifactStore(tmp_path)
    metadata = MeetingMetadata.model_validate(
        {
            "title": "Синтетическая встреча",
            "meeting_date": "2026-09-23",
            "timezone": "Asia/Almaty",
            "participants": ["Алия"],
            "recording_notice_confirmed": True,
        }
    )
    meeting = store.create_meeting(owner, metadata, b"synthetic audio")
    payload: dict[str, object] = {
        "schema_version": 1,
        "job_id": str(uuid4()),
        "transcript": {
            "schema_version": 1,
            "meeting_id": str(meeting.id),
            "revision": 0,
            "speakers": [
                {
                    "speaker_id": "speaker_1",
                    "display_name": None,
                    "identity_status": "unreviewed",
                },
                {
                    "speaker_id": "speaker_2",
                    "display_name": None,
                    "identity_status": "unreviewed",
                },
            ],
            "segments": [
                {
                    "id": str(SEGMENT_ID),
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
            "meeting_id": str(meeting.id),
            "revision": 0,
            "summary": [],
            "action_items": [],
        },
        "model_versions": {
            "asr": "fixture@1",
            "diarization": "fixture@1",
            "analysis": "fixture@1",
        },
    }
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    payload["result_hash"] = hashlib.sha256(raw).hexdigest()
    store.publish_results(owner, meeting.id, ResultBundleV1.model_validate(payload))
    return store, owner, meeting.id


def _review(
    revision: int,
    *,
    name: str = "Алия",
    text: str = "Тексерілді.",
    evidence_end: int = 900,
) -> ReviewRequest:
    return ReviewRequest.model_validate(
        {
            "base_revision": revision,
            "speaker_mappings": [
                {
                    "speaker_id": "speaker_1",
                    "display_name": name,
                    "identity_status": "named",
                },
                {
                    "speaker_id": "speaker_2",
                    "display_name": None,
                    "identity_status": "unknown",
                },
            ],
            "segment_edits": [
                {
                    "segment_id": str(SEGMENT_ID),
                    "text": text,
                    "speaker_id": "speaker_2",
                }
            ],
            "summary": [
                {
                    "id": str(uuid4()),
                    "text": "Решение подтверждено",
                    "evidence": [
                        {
                            "segment_id": str(SEGMENT_ID),
                            "start_ms": 100,
                            "end_ms": evidence_end,
                        }
                    ],
                }
            ],
            "action_items": [],
        }
    )


def test_full_replacement_approval_and_reapproval(tmp_path: Path) -> None:
    store, owner, meeting_id = _ready_store(tmp_path)
    with pytest.raises(ReviewConflict) as incomplete:
        approve_review(store, owner, meeting_id, ApprovalRequest(base_revision=0))
    assert incomplete.value.code == "review_required"

    first = update_review(store, owner, meeting_id, _review(0))
    assert (first.revision, first.status) == (1, "review_required")
    transcript, insights = read_reviewed_results(store, owner, meeting_id)
    assert transcript.revision == insights.revision == 1
    assert transcript.segments[0].text == "Тексерілді."
    assert transcript.segments[0].speaker_id == "speaker_2"
    assert transcript.segments[0].edited is True
    with store.lifecycle_lock(owner, meeting_id):
        assert read_reviewed_results_unlocked(store, owner, meeting_id) == (
            transcript,
            insights,
        )
    assert approve_review(
        store, owner, meeting_id, ApprovalRequest(base_revision=1)
    ).status == "approved"

    old_pdf = store.pdf_path(owner, meeting_id, 1)
    store.write_pdf_cache(owner, meeting_id, 1, b"cached")
    second = _review(1, text="Қайта қаралды.")
    second.segment_edits = []
    second.summary = []
    result = update_review(store, owner, meeting_id, second)
    assert (result.revision, result.status) == (2, "review_required")
    assert not old_pdf.exists()
    assert not old_pdf.with_name(old_pdf.name + ".sha256").exists()
    transcript, insights = read_reviewed_results(store, owner, meeting_id)
    assert transcript.segments[0].text == "Жақсы."
    assert transcript.segments[0].speaker_id == "speaker_1"
    assert transcript.segments[0].edited is False
    assert insights.summary == []
    assert store.read_results(owner, meeting_id)[0].segments[0].text == "Жақсы."
    with pytest.raises(ReviewConflict) as stale:
        approve_review(store, owner, meeting_id, ApprovalRequest(base_revision=1))
    assert stale.value.code == "stale_revision"


def test_rejects_invalid_references_without_changing_revision(tmp_path: Path) -> None:
    store, owner, meeting_id = _ready_store(tmp_path)
    request = _review(0, evidence_end=901)
    with pytest.raises(ReviewValidationError):
        update_review(store, owner, meeting_id, request)
    assert store.read_meeting(owner, meeting_id).revision == 0
    assert store.read_review(owner, meeting_id) is None

    request = _review(0)
    request.speaker_mappings = request.speaker_mappings[:1]
    with pytest.raises(ReviewValidationError):
        update_review(store, owner, meeting_id, request)
    assert store.read_meeting(owner, meeting_id).revision == 0


def test_marker_failure_keeps_approved_snapshot_with_regenerable_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, owner, meeting_id = _ready_store(tmp_path)
    update_review(store, owner, meeting_id, _review(0))
    approve_review(store, owner, meeting_id, ApprovalRequest(base_revision=1))
    pdf = store.pdf_path(owner, meeting_id, 1)
    store.write_pdf_cache(owner, meeting_id, 1, b"cached")
    original_write = store._atomic_write  # pyright: ignore[reportPrivateUsage]

    def fail_marker(path: Path, data: bytes, *, immutable: bool = False) -> None:
        if path.name == "meeting.json":
            raise OSError("simulated interrupted marker write")
        original_write(path, data, immutable=immutable)

    monkeypatch.setattr(store, "_atomic_write", fail_marker)
    with pytest.raises(OSError):
        update_review(store, owner, meeting_id, _review(1, text="Новая правка"))
    restarted = LocalArtifactStore(tmp_path)
    assert restarted.read_meeting(owner, meeting_id).status == "approved"
    assert restarted.read_meeting(owner, meeting_id).revision == 1
    assert read_reviewed_results(restarted, owner, meeting_id)[0].segments[0].text == (
        "Тексерілді."
    )
    assert not pdf.exists()
    assert not pdf.with_name(pdf.name + ".sha256").exists()
    recovered = update_review(
        restarted, owner, meeting_id, _review(1, text="Другая новая правка")
    )
    assert (recovered.revision, recovered.status) == (2, "review_required")
    assert read_reviewed_results(restarted, owner, meeting_id)[0].segments[0].text == (
        "Другая новая правка"
    )
    assert not pdf.exists()


@pytest.mark.parametrize("failure", ["path_lookup", "delete"])
def test_pdf_cleanup_failure_keeps_old_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    store, owner, meeting_id = _ready_store(tmp_path)
    update_review(store, owner, meeting_id, _review(0))
    approve_review(store, owner, meeting_id, ApprovalRequest(base_revision=1))
    pdf = store.pdf_path(owner, meeting_id, 1)
    store.write_pdf_cache(owner, meeting_id, 1, b"cached")
    with monkeypatch.context() as patch:
        if failure == "path_lookup":

            def fail_pdf_path(owner_id: UUID, target_id: UUID, revision: int) -> Path:
                raise OSError("simulated path lookup failure")

            patch.setattr(store, "pdf_path", fail_pdf_path)
        else:

            def fail_delete(owner_id: UUID, target_id: UUID, revision: int) -> None:
                raise OSError("simulated cleanup failure")

            patch.setattr(store, "delete_pdf_cache", fail_delete)
        with pytest.raises(OSError):
            update_review(store, owner, meeting_id, _review(1))
    assert store.read_meeting(owner, meeting_id).revision == 1
    assert store.read_meeting(owner, meeting_id).status == "approved"
    assert pdf.exists()
    assert store.read_pdf_cache(owner, meeting_id, 1) == b"cached"
    assert read_reviewed_results(store, owner, meeting_id)[0].revision == 1
