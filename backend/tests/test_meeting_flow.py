"""Synthetic HTTP flow through durable upload, fake GPU, review, and export."""

import asyncio
import json
import logging
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pypdf import PdfReader
from test_artifact_store import bundle
from test_coordinator import FakeGPUClient
from test_meetings_api import metadata, wav_bytes

from app.api.routes.meetings import get_artifact_store
from app.core.auth import AuthenticatedUser, InvalidAccessToken, get_token_verifier
from app.models.gpu import GPUContextV1, JobV1
from app.services.artifact_store import LocalArtifactStore
from app.services.coordinator import MeetingCoordinator
from app.services.demo_fixture import SOURCE_LABEL, seed_demo_fixture

OWNER = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
HEADERS = {"Authorization": "Bearer owner"}
AUDIO_MARKER = "PRIVATE_AUDIO_SENTINEL_93"
TOKEN_MARKER = "private-token-sentinel-93"
TEXT_MARKER = "PRIVATE_MEETING_TEXT_SENTINEL_93"


class Verifier:
    async def verify(self, token: str) -> AuthenticatedUser:
        if token in {"owner", TOKEN_MARKER}:
            return AuthenticatedUser(id=OWNER, role="authenticated")
        if token == "other":
            return AuthenticatedUser(id=OTHER, role="authenticated")
        raise InvalidAccessToken


class UploadGPU(FakeGPUClient):
    expected_audio: bytes = wav_bytes()

    async def submit(
        self,
        audio_path: Path,
        context: GPUContextV1,
        *,
        audio_extension: str | None = None,
    ) -> JobV1:
        assert audio_path.read_bytes() == self.expected_audio
        assert audio_extension == ".wav"
        self.audio_extensions.append(audio_extension)
        self.contexts.append(context)
        self.check("submit")
        return self.job


@pytest.fixture
def store(app: FastAPI, tmp_path: Path) -> LocalArtifactStore:
    result = LocalArtifactStore(tmp_path / "artifacts")
    app.dependency_overrides[get_artifact_store] = lambda: result
    app.dependency_overrides[get_token_verifier] = lambda: Verifier()
    return result


async def test_upload_fake_gpu_review_approval_pdf_and_later_edit(
    client: AsyncClient, store: LocalArtifactStore, caplog: pytest.LogCaptureFixture
) -> None:
    # This scoped assertion catches accidental logging of these test markers.
    caplog.set_level(logging.DEBUG)
    audio = bytearray(wav_bytes())
    audio[44 : 44 + len(AUDIO_MARKER)] = AUDIO_MARKER.encode("ascii")
    audio_bytes = bytes(audio)
    headers = {"Authorization": f"Bearer {TOKEN_MARKER}"}
    upload = await client.post(
        "/api/v1/meetings",
        headers=headers,
        files={
            "audio": ("meeting.wav", audio_bytes, "audio/wav"),
            "metadata": (
                None,
                json.dumps(metadata(title=TEXT_MARKER)),
                "application/json",
            ),
        },
    )
    assert upload.status_code == 202
    created = upload.json()
    meeting_id = UUID(created["id"])
    url = f"/api/v1/meetings/{meeting_id}"
    assert created["status"] == "queued"
    assert created["source"]["kind"] == "uploaded_audio"
    assert (await client.get(url + "/export.pdf", headers=headers)).status_code == 409

    fake_gpu = UploadGPU(bundle(meeting_id))
    fake_gpu.expected_audio = audio_bytes
    coordinator = MeetingCoordinator(store, fake_gpu)
    processing = await coordinator.process_once(OWNER, meeting_id)
    assert processing.status == "processing"
    fake_gpu.job = fake_gpu.job.model_copy(
        update={
            "status": "completed",
            "stage": None,
            "result_hash": fake_gpu.result.result_hash,
        }
    )
    ready = await coordinator.process_once(OWNER, meeting_id)
    assert ready.status == "review_required"
    assert ready.cleanup_status == "deleted"
    assert fake_gpu.calls == ["submit", "poll", "result", "ack"]
    assert not store.upload_present(OWNER, meeting_id)

    # Once committed, reviewed reads and export no longer call the GPU.
    restarted = LocalArtifactStore(store.root)
    transcript_response = await client.get(url + "/transcript", headers=headers)
    insights_response = await client.get(url + "/insights", headers=headers)
    assert transcript_response.status_code == insights_response.status_code == 200
    transcript = transcript_response.json()
    insights = insights_response.json()
    assert restarted.read_meeting(OWNER, meeting_id).status == "review_required"
    assert (
        await client.post(url + "/approve", headers=headers, json={"base_revision": 0})
    ).status_code == 409
    for suffix in ("", "/transcript", "/insights", "/export.pdf"):
        foreign = await client.get(
            url + suffix, headers={"Authorization": "Bearer other"}
        )
        assert foreign.status_code == 404

    segment = transcript["segments"][0]
    reviewed_text = "Жақсы, сметаны жұмаға дайындаймыз. " + TEXT_MARKER
    review: dict[str, Any] = {
        "base_revision": 0,
        "speaker_mappings": [
            {
                "speaker_id": "speaker_1",
                "display_name": "Алия",
                "identity_status": "named",
            }
        ],
        "segment_edits": [
            {
                "segment_id": segment["id"],
                "text": reviewed_text,
                "speaker_id": "speaker_1",
            }
        ],
        "summary": insights["summary"],
        "action_items": insights["action_items"],
    }
    saved = await client.put(url + "/review", headers=headers, json=review)
    assert saved.status_code == 200
    assert saved.json() == {"revision": 1, "status": "review_required"}
    assert (
        await client.put(url + "/review", headers=headers, json=review)
    ).status_code == 409
    assert (await client.get(url + "/export.pdf", headers=headers)).status_code == 409
    approved = await client.post(
        url + "/approve", headers=headers, json={"base_revision": 1}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    pdf = await client.get(url + "/export.pdf", headers=headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF-")
    pdf_text = "\n".join(
        page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages
    )
    assert reviewed_text in pdf_text
    assert (
        await client.get(url + "/export.pdf", headers=headers)
    ).content == pdf.content

    # A later full review invalidates the approved revision and its export.
    review["base_revision"] = 1
    review["segment_edits"][0]["text"] = "Жақсы, сметаны дүйсенбіге дайындаймыз."
    changed = await client.put(url + "/review", headers=headers, json=review)
    assert changed.status_code == 200
    assert changed.json() == {"revision": 2, "status": "review_required"}
    assert (await client.get(url + "/export.pdf", headers=headers)).status_code == 409
    after_restart = LocalArtifactStore(store.root)
    assert after_restart.read_meeting(OWNER, meeting_id).revision == 2
    current = await client.get(url + "/transcript", headers=headers)
    assert current.json()["segments"][0]["text"] == review["segment_edits"][0]["text"]
    assert current.json()["revision"] == 2
    assert (
        await client.post(url + "/approve", headers=headers, json={"base_revision": 1})
    ).status_code == 409
    reapproved = await client.post(
        url + "/approve", headers=headers, json={"base_revision": 2}
    )
    assert reapproved.status_code == 200
    newer_pdf = await client.get(url + "/export.pdf", headers=headers)
    assert newer_pdf.status_code == 200
    assert newer_pdf.content.startswith(b"%PDF-")
    assert newer_pdf.content != pdf.content
    newer_text = "\n".join(
        page.extract_text() for page in PdfReader(BytesIO(newer_pdf.content)).pages
    )
    assert review["segment_edits"][0]["text"] in newer_text

    for marker in (AUDIO_MARKER, TOKEN_MARKER, TEXT_MARKER):
        assert marker not in caplog.text


async def test_prepared_example_is_account_bound_audio_bound_and_separate(
    client: AsyncClient, store: LocalArtifactStore, tmp_path: Path
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "demo_meeting" / "synthetic.json"
    recording = tmp_path / "contract.wav"
    recording.write_bytes(wav_bytes())
    with pytest.raises(ValueError, match="demo account"):
        seed_demo_fixture(
            store,
            owner_id=OTHER,
            demo_owner_id=OWNER,
            recording_path=recording,
            fixture_path=fixture,
            allow_synthetic_test_fixture=True,
        )
    with pytest.raises(ValueError, match="another demo account"):
        seed_demo_fixture(
            store,
            owner_id=OTHER,
            demo_owner_id=OTHER,
            recording_path=recording,
            fixture_path=fixture,
            allow_synthetic_test_fixture=True,
        )
    with pytest.raises(ValueError, match="not a stage demo"):
        seed_demo_fixture(
            store,
            owner_id=OWNER,
            demo_owner_id=OWNER,
            recording_path=recording,
            fixture_path=fixture,
        )
    recording.write_bytes(b"different upload")
    with pytest.raises(ValueError, match="does not match"):
        seed_demo_fixture(
            store,
            owner_id=OWNER,
            demo_owner_id=OWNER,
            recording_path=recording,
            fixture_path=fixture,
            allow_synthetic_test_fixture=True,
        )
    assert store.list_meetings(OWNER) == []
    recording.write_bytes(wav_bytes())
    seeded = seed_demo_fixture(
        store,
        owner_id=OWNER,
        demo_owner_id=OWNER,
        recording_path=recording,
        fixture_path=fixture,
        allow_synthetic_test_fixture=True,
    )
    assert seeded.status == "review_required"
    assert seeded.source.kind == "demo_fixture"
    assert seeded.source.label == SOURCE_LABEL
    assert seeded.source.fixture_id == "synthetic-contract-v1"
    assert seeded.source_available is False
    assert seeded.cleanup_status == "deleted"
    assert not store.upload_present(OWNER, seeded.id)
    assert store.read_results(OWNER, seeded.id)[0].revision == 0
    assert (
        LocalArtifactStore(store.root).read_meeting(OWNER, seeded.id).source.label
        == SOURCE_LABEL
    )
    assert store.list_meetings(OTHER) == []
    url = f"/api/v1/meetings/{seeded.id}"
    visible = await client.get(url, headers=HEADERS)
    assert visible.status_code == 200
    assert visible.json()["source"] == {
        "kind": "demo_fixture",
        "label": SOURCE_LABEL,
        "fixture_id": "synthetic-contract-v1",
    }
    assert (
        await client.get(url, headers={"Authorization": "Bearer other"})
    ).status_code == 404
    _, insights = store.read_results(OWNER, seeded.id)
    review = {
        "base_revision": 0,
        "speaker_mappings": [
            {
                "speaker_id": "speaker_1",
                "display_name": None,
                "identity_status": "unknown",
            }
        ],
        "segment_edits": [],
        "summary": [item.model_dump(mode="json") for item in insights.summary],
        "action_items": [],
    }
    saved = await client.put(url + "/review", headers=HEADERS, json=review)
    assert saved.status_code == 200
    approved = await client.post(
        url + "/approve", headers=HEADERS, json={"base_revision": 1}
    )
    assert approved.status_code == 200
    assert approved.json()["source"]["label"] == SOURCE_LABEL
    exported = await client.get(url + "/export.pdf", headers=HEADERS)
    assert exported.status_code == 200
    pdf_text = "\n".join(
        page.extract_text() for page in PdfReader(BytesIO(exported.content)).pages
    )
    assert SOURCE_LABEL in pdf_text


async def test_concurrent_reviews_accept_only_one_revision(
    client: AsyncClient, store: LocalArtifactStore, tmp_path: Path
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "demo_meeting" / "synthetic.json"
    recording = tmp_path / "contract.wav"
    recording.write_bytes(wav_bytes())
    meeting = seed_demo_fixture(
        store,
        owner_id=OWNER,
        demo_owner_id=OWNER,
        recording_path=recording,
        fixture_path=fixture,
        allow_synthetic_test_fixture=True,
    )
    url = f"/api/v1/meetings/{meeting.id}/review"
    transcript, insights = store.read_results(OWNER, meeting.id)
    base = {
        "base_revision": 0,
        "speaker_mappings": [
            {
                "speaker_id": "speaker_1",
                "display_name": None,
                "identity_status": "unknown",
            }
        ],
        "segment_edits": [],
        "summary": [item.model_dump(mode="json") for item in insights.summary],
        "action_items": [],
    }
    assert transcript.revision == 0
    first, second = await asyncio.gather(
        client.put(url, headers=HEADERS, json=base),
        client.put(url, headers=HEADERS, json=base),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert LocalArtifactStore(store.root).read_meeting(OWNER, meeting.id).revision == 1
