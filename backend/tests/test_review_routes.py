"""Public review and export route contract with synthetic local results."""

import asyncio
import hashlib
import json
import threading
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader
from starlette.types import Message, Receive, Scope, Send

from app.api.routes import meetings as meeting_routes
from app.api.routes.meetings import get_artifact_store
from app.core.auth import AuthenticatedUser, get_token_verifier
from app.models.insights import InsightsV1, ResultBundleV1
from app.models.meeting import Meeting, MeetingMetadata
from app.models.transcript import TranscriptV1
from app.services.artifact_store import LocalArtifactStore
from app.services.reviews import read_reviewed_results

OWNER = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
SEGMENT = UUID("76424ccb-f8d4-46f2-b7fc-81e888a01775")
HEADERS = {"Authorization": "Bearer valid"}


class Verifier:
    async def verify(self, token: str) -> AuthenticatedUser:
        owner = OTHER if token == "other" else OWNER
        return AuthenticatedUser(id=owner, role="authenticated")


def ready_meeting(app: FastAPI, root: Path) -> tuple[LocalArtifactStore, UUID]:
    store = LocalArtifactStore(root)
    app.dependency_overrides[get_artifact_store] = lambda: store
    app.dependency_overrides[get_token_verifier] = lambda: Verifier()
    metadata = MeetingMetadata.model_validate(
        {
            "title": "Тест Жақсы",
            "meeting_date": "2026-09-23",
            "timezone": "Asia/Almaty",
            "participants": ["Алия"],
            "recording_notice_confirmed": True,
        }
    )
    meeting = store.create_meeting(OWNER, metadata, b"synthetic audio")
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
                }
            ],
            "segments": [
                {
                    "id": str(SEGMENT),
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
    store.publish_results(OWNER, meeting.id, ResultBundleV1.model_validate(payload))
    return store, meeting.id


def review_payload(revision: int, text: str = "Жақсы, келісілді.") -> dict[str, object]:
    return {
        "base_revision": revision,
        "speaker_mappings": [
            {
                "speaker_id": "speaker_1",
                "display_name": "Алия",
                "identity_status": "named",
            }
        ],
        "segment_edits": [
            {"segment_id": str(SEGMENT), "text": text, "speaker_id": "speaker_1"}
        ],
        "summary": [],
        "action_items": [],
    }


async def test_review_approve_export_and_later_edit(
    client: AsyncClient, app: FastAPI, tmp_path: Path
) -> None:
    store, meeting_id = ready_meeting(app, tmp_path / "data")
    url = f"/api/v1/meetings/{meeting_id}"
    blocked = await client.get(f"{url}/export.pdf", headers=HEADERS)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "review_required"

    edited = await client.put(
        f"{url}/review", headers=HEADERS, json=review_payload(0)
    )
    assert edited.status_code == 200
    assert edited.json() == {"revision": 1, "status": "review_required"}
    stale = await client.put(
        f"{url}/review", headers=HEADERS, json=review_payload(0)
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_revision"
    assert (await client.get(f"{url}/transcript", headers=HEADERS)).json()[
        "segments"
    ][0]["text"] == "Жақсы, келісілді."
    assert LocalArtifactStore(store.root).read_meeting(OWNER, meeting_id).revision == 1

    approved = await client.post(
        f"{url}/approve", headers=HEADERS, json={"base_revision": 1}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    pdf = await client.get(f"{url}/export.pdf", headers=HEADERS)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")

    changed = await client.put(
        f"{url}/review", headers=HEADERS, json=review_payload(1, "Түзетілді.")
    )
    assert changed.status_code == 200
    assert changed.json() == {"revision": 2, "status": "review_required"}
    assert (await client.get(f"{url}/export.pdf", headers=HEADERS)).status_code == 409
    assert not store.pdf_path(OWNER, meeting_id, 1).exists()


async def test_export_and_edit_serialize_on_meeting_lock(
    client: AsyncClient,
    app: FastAPI,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, meeting_id = ready_meeting(app, tmp_path / "data")
    url = f"/api/v1/meetings/{meeting_id}"
    assert (
        await client.put(f"{url}/review", headers=HEADERS, json=review_payload(0))
    ).status_code == 200
    assert (
        await client.post(
            f"{url}/approve", headers=HEADERS, json={"base_revision": 1}
        )
    ).status_code == 200

    started = threading.Event()
    release = threading.Event()
    original_render = meeting_routes.render_pdf

    def slow_render(
        meeting: Meeting, transcript: TranscriptV1, insights: InsightsV1
    ) -> bytes:
        started.set()
        if not release.wait(timeout=3):
            raise TimeoutError("test renderer was not released")
        return original_render(meeting, transcript, insights)

    monkeypatch.setattr(meeting_routes, "render_pdf", slow_render)
    exporting = asyncio.create_task(client.get(f"{url}/export.pdf", headers=HEADERS))
    assert await asyncio.to_thread(started.wait, 3)
    editing = asyncio.create_task(
        client.put(f"{url}/review", headers=HEADERS, json=review_payload(1))
    )
    await asyncio.sleep(0.05)
    assert not editing.done()
    release.set()
    exported, edited = await asyncio.gather(exporting, editing)
    assert exported.status_code == 200
    assert edited.status_code == 200
    assert (await client.get(f"{url}/export.pdf", headers=HEADERS)).status_code == 409


async def test_edit_waits_until_export_response_is_sent(
    client: AsyncClient, app: FastAPI, tmp_path: Path
) -> None:
    _, meeting_id = ready_meeting(app, tmp_path / "data")
    url = f"/api/v1/meetings/{meeting_id}"
    assert (
        await client.put(f"{url}/review", headers=HEADERS, json=review_payload(0))
    ).status_code == 200
    assert (
        await client.post(
            f"{url}/approve", headers=HEADERS, json={"base_revision": 1}
        )
    ).status_code == 200

    sending = asyncio.Event()
    release = asyncio.Event()

    async def pause_export_send(scope: Scope, receive: Receive, send: Send) -> None:
        async def paused_send(message: Message) -> None:
            if (
                scope["path"].endswith("/export.pdf")
                and message.get("type") == "http.response.start"
            ):
                sending.set()
                await release.wait()
            await send(message)

        await app(scope, receive, paused_send)

    transport = ASGITransport(app=pause_export_send)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as export_client:
        exporting = asyncio.create_task(
            export_client.get(f"{url}/export.pdf", headers=HEADERS)
        )
        try:
            await asyncio.wait_for(sending.wait(), 3)
            editing = asyncio.create_task(
                client.put(f"{url}/review", headers=HEADERS, json=review_payload(1))
            )
            await asyncio.sleep(0.05)
            assert not editing.done()
        finally:
            release.set()
        exported, edited = await asyncio.gather(exporting, editing)
        assert exported.status_code == 200
        assert edited.status_code == 200


async def test_corrupt_cache_is_not_served_and_stale_stage_is_cleared(
    client: AsyncClient, app: FastAPI, tmp_path: Path
) -> None:
    store, meeting_id = ready_meeting(app, tmp_path / "data")
    url = f"/api/v1/meetings/{meeting_id}"
    assert (
        await client.put(f"{url}/review", headers=HEADERS, json=review_payload(0))
    ).status_code == 200
    assert (
        await client.post(
            f"{url}/approve", headers=HEADERS, json={"base_revision": 1}
        )
    ).status_code == 200
    assert (await client.get(f"{url}/export.pdf", headers=HEADERS)).status_code == 200
    cache = store.pdf_path(OWNER, meeting_id, 1)
    cache.write_bytes(b"%PDF-broken")
    record = store.read_record(OWNER, meeting_id)
    record.meeting.stage = "exporting"
    store.update_meeting(OWNER, record)

    result = await client.get(f"{url}/export.pdf", headers=HEADERS)
    assert result.status_code == 200
    assert result.content.startswith(b"%PDF")
    assert result.content != b"%PDF-broken"
    assert store.read_meeting(OWNER, meeting_id).stage is None


async def test_foreign_malformed_review_is_not_disclosed(
    client: AsyncClient, app: FastAPI, tmp_path: Path
) -> None:
    _, meeting_id = ready_meeting(app, tmp_path / "data")
    for method, suffix in (("PUT", "/review"), ("POST", "/approve")):
        response = await client.request(
            method,
            f"/api/v1/meetings/{meeting_id}{suffix}",
            headers={"Authorization": "Bearer other"},
            content=b"{broken",
        )
        assert response.status_code == 404
        assert response.json()["code"] == "meeting_not_found"


async def test_cancelled_export_keeps_edit_waiting_for_renderer(
    client: AsyncClient,
    app: FastAPI,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, meeting_id = ready_meeting(app, tmp_path / "data")
    url = f"/api/v1/meetings/{meeting_id}"
    assert (
        await client.put(f"{url}/review", headers=HEADERS, json=review_payload(0))
    ).status_code == 200
    assert (
        await client.post(
            f"{url}/approve", headers=HEADERS, json={"base_revision": 1}
        )
    ).status_code == 200
    started = threading.Event()
    release = threading.Event()
    original_render = meeting_routes.render_pdf

    def slow_render(
        meeting: Meeting, transcript: TranscriptV1, insights: InsightsV1
    ) -> bytes:
        started.set()
        if not release.wait(timeout=3):
            raise TimeoutError("test renderer was not released")
        return original_render(meeting, transcript, insights)

    monkeypatch.setattr(meeting_routes, "render_pdf", slow_render)
    exporting = asyncio.create_task(client.get(f"{url}/export.pdf", headers=HEADERS))
    assert await asyncio.to_thread(started.wait, 3)
    exporting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await exporting
    editing = asyncio.create_task(
        client.put(f"{url}/review", headers=HEADERS, json=review_payload(1))
    )
    try:
        await asyncio.sleep(0.05)
        assert not editing.done()
    finally:
        release.set()
    edited = await asyncio.wait_for(editing, 3)
    assert edited.status_code == 200


async def test_valid_but_swapped_pdf_cache_is_rejected(
    client: AsyncClient, app: FastAPI, tmp_path: Path
) -> None:
    store, meeting_id = ready_meeting(app, tmp_path / "data")
    url = f"/api/v1/meetings/{meeting_id}"
    assert (
        await client.put(f"{url}/review", headers=HEADERS, json=review_payload(0))
    ).status_code == 200
    assert (
        await client.post(
            f"{url}/approve", headers=HEADERS, json={"base_revision": 1}
        )
    ).status_code == 200
    assert (await client.get(f"{url}/export.pdf", headers=HEADERS)).status_code == 200
    meeting = store.read_meeting(OWNER, meeting_id)
    transcript, insights = read_reviewed_results(store, OWNER, meeting_id)
    altered = meeting.model_copy(update={"title": "Чужой секрет"})
    swapped = meeting_routes.render_pdf(altered, transcript, insights)
    cache_path = store.pdf_path(OWNER, meeting_id, 1)
    cache_path.write_bytes(swapped)
    cache_path.with_name(cache_path.name + ".sha256").write_bytes(
        hashlib.sha256(swapped).hexdigest().encode("ascii")
    )

    response = await client.get(f"{url}/export.pdf", headers=HEADERS)
    assert response.status_code == 200
    pages = PdfReader(BytesIO(response.content)).pages
    text = "\n".join(page.extract_text() for page in pages)
    assert "Тест Жақсы" in text
    assert "Чужой секрет" not in text
