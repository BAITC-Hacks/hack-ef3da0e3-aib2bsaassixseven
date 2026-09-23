"""Explicit, offline prepared-example seeding for a dedicated demo account.

This module is never called by the public upload route or coordinator. The
fixture's audio digest is pinned, so unrelated uploads cannot receive its text.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from app.models.insights import ResultBundleV1, canonical_json
from app.models.meeting import Meeting, MeetingMetadata, MeetingSource
from app.services.artifact_store import LocalArtifactStore

SOURCE_LABEL = "Подготовленный пример · обработка выполнена заранее"


def seed_demo_fixture(
    store: LocalArtifactStore,
    *,
    owner_id: UUID,
    demo_owner_id: UUID,
    recording_path: Path,
    fixture_path: Path,
    allow_synthetic_test_fixture: bool = False,
) -> Meeting:
    """Create a new precomputed meeting after explicit owner and audio checks.

    A production caller must supply the configured dedicated demo account ID.
    Synthetic contract data is rejected unless a test explicitly opts in.
    Existing meetings and uploaded results are never replaced.
    """
    if owner_id != demo_owner_id:
        raise ValueError("Prepared example is restricted to the demo account")
    raw: object = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Invalid prepared example")
    fixture = cast(dict[str, object], raw)
    if fixture.get("purpose") == "synthetic_contract_test":
        if not allow_synthetic_test_fixture:
            raise ValueError("Synthetic contract data is not a stage demo")
    elif fixture.get("purpose") != "prepared_demo":
        raise ValueError("Invalid prepared example purpose")
    fixture_owner = fixture.get("demo_owner_id")
    if fixture_owner != str(demo_owner_id):
        raise ValueError("Prepared example is bound to another demo account")
    fixture_id = fixture.get("fixture_id")
    expected_hash = fixture.get("recording_sha256")
    if not isinstance(fixture_id, str) or not fixture_id.strip():
        raise ValueError("Prepared example needs a fixture ID")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError("Prepared example needs a pinned audio SHA-256")
    audio = recording_path.read_bytes()
    if hashlib.sha256(audio).hexdigest() != expected_hash:
        raise ValueError("Recording does not match prepared example")
    metadata = MeetingMetadata.model_validate(fixture["metadata"])
    meeting = store.create_meeting(owner_id, metadata, audio)
    try:
        transcript = dict(cast(dict[str, object], fixture["transcript"]))
        insights = dict(cast(dict[str, object], fixture["insights"]))
        transcript["meeting_id"] = str(meeting.id)
        insights["meeting_id"] = str(meeting.id)
        payload: dict[str, object] = {
            "schema_version": 1,
            "job_id": str(uuid4()),
            "transcript": transcript,
            "insights": insights,
            "model_versions": fixture["model_versions"],
        }
        payload["result_hash"] = hashlib.sha256(canonical_json(payload)).hexdigest()
        bundle = ResultBundleV1.model_validate(payload)
        store.publish_results(owner_id, meeting.id, bundle)
        store.delete_upload(owner_id, meeting.id)
        record = store.read_record(owner_id, meeting.id)
        record.audio_sha256 = None
        record.local_cleanup_status = "deleted"
        record.jobs[0].cleanup_status = "deleted"
        record.jobs[0].ack_pending = False
        record.meeting.cleanup_status = "deleted"
        record.meeting.source_available = False
        record.meeting.temporary_expires_at = None
        record.meeting.source = MeetingSource(
            kind="demo_fixture", label=SOURCE_LABEL, fixture_id=fixture_id
        )
        record.meeting.updated_at = datetime.now(UTC)
        return store.update_meeting(owner_id, record)
    except BaseException:
        # Never expose a partially seeded meeting as a valid prepared example.
        # Deletion is safe here: this meeting was created by this invocation.
        store.delete_meeting(owner_id, meeting.id)
        raise
