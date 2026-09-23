"""Public meeting API tests use only generated WAV bytes and temporary storage."""

import io
import json
import wave
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response

from app.api.routes.meetings import get_artifact_store
from app.core.auth import AuthenticatedUser, InvalidAccessToken, get_token_verifier
from app.services import uploads
from app.services.artifact_store import LocalArtifactStore

OWNER = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
HEADERS = {"Authorization": "Bearer valid"}


class Verifier:
    async def verify(self, token: str) -> AuthenticatedUser:
        if token == "valid":
            return AuthenticatedUser(id=OWNER, role="authenticated")
        if token == "other":
            return AuthenticatedUser(id=OTHER, role="authenticated")
        raise InvalidAccessToken


@pytest.fixture
def store(app: FastAPI, tmp_path: Path) -> LocalArtifactStore:
    result = LocalArtifactStore(tmp_path / "artifacts")
    app.dependency_overrides[get_artifact_store] = lambda: result
    app.dependency_overrides[get_token_verifier] = lambda: Verifier()
    return result


def wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\x00\x00" * 100)
    return output.getvalue()


def metadata(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "title": "План запуска",
        "meeting_date": "2026-09-23",
        "timezone": "Asia/Almaty",
        "participants": ["Алия", "Ернур"],
        "recording_notice_confirmed": True,
    }
    result.update(updates)
    return result


async def upload(
    client: AsyncClient,
    *,
    filename: str = "meeting.wav",
    content: bytes | None = None,
    payload: object | None = None,
    metadata_type: str = "application/json",
    token: str = "valid",
) -> Response:
    return await client.post(
        "/api/v1/meetings",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "audio": (
                filename,
                wav_bytes() if content is None else content,
                "audio/wav",
            ),
            "metadata": (
                None,
                json.dumps(metadata() if payload is None else payload),
                metadata_type,
            ),
        },
    )


async def test_valid_upload_is_durable_and_owner_scoped(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    response = await upload(client)
    assert response.status_code == 202
    meeting = response.json()
    assert meeting["status"] == "queued"
    assert meeting["stage"] is None
    assert meeting["source"] == {
        "kind": "uploaded_audio",
        "label": None,
        "fixture_id": None,
    }
    assert meeting["recording_notice_confirmed"] is True
    assert "owner_id" not in meeting
    assert "path" not in json.dumps(meeting).lower()
    meeting_id = UUID(meeting["id"])
    record = store.read_record(OWNER, meeting_id)
    assert record.jobs[0].attempt == 1
    assert store.upload_path(OWNER, meeting_id).read_bytes() == wav_bytes()

    same = await client.get(f"/api/v1/meetings/{meeting_id}", headers=HEADERS)
    assert same.status_code == 200
    assert same.json()["id"] == str(meeting_id)
    for suffix in ("", "/transcript", "/insights"):
        foreign = await client.get(
            f"/api/v1/meetings/{meeting_id}{suffix}",
            headers={"Authorization": "Bearer other"},
        )
        assert foreign.status_code == 404
        assert foreign.json() == {
            "detail": "Встреча не найдена",
            "code": "meeting_not_found",
        }
    for suffix in ("/transcript", "/insights"):
        pending = await client.get(
            f"/api/v1/meetings/{meeting_id}{suffix}", headers=HEADERS
        )
        assert pending.status_code == 409
        assert pending.json()["code"] == "invalid_state"


async def test_uploaded_filename_is_never_a_storage_path(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    result = await upload(client, filename="../../outside.wav")
    assert result.status_code == 202
    meeting_id = UUID(result.json()["id"])
    assert store.upload_path(OWNER, meeting_id).name == "upload.bin"
    assert not (store.root.parent / "outside.wav").exists()


async def test_list_pagination_and_cursor_validation(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    ids: list[str] = []
    for index in range(3):
        response = await upload(client, payload=metadata(title=f"Meeting {index}"))
        assert response.status_code == 202
        ids.append(response.json()["id"])
    foreign = await upload(client, token="other")
    assert foreign.status_code == 202

    first = await client.get("/api/v1/meetings?limit=2", headers=HEADERS)
    assert first.status_code == 200
    first_data = first.json()
    assert [item["id"] for item in first_data["items"]] == ids[::-1][:2]
    assert isinstance(first_data["next_cursor"], str)
    second = await client.get(
        "/api/v1/meetings",
        headers=HEADERS,
        params={"limit": "2", "cursor": first_data["next_cursor"]},
    )
    assert second.status_code == 200
    assert [item["id"] for item in second.json()["items"]] == ids[:1]
    assert second.json()["next_cursor"] is None
    for query in ("limit=0", "limit=101", "limit=nope", "cursor=bad"):
        bad = await client.get(f"/api/v1/meetings?{query}", headers=HEADERS)
        assert bad.status_code == 422
        assert bad.json()["code"] == "invalid_request"


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("meeting.wav", b"broken", 415),
        ("meeting.mp3", b"not an mp3", 415),
        ("meeting.mp3", wav_bytes(), 415),
        ("meeting.txt", wav_bytes(), 415),
        ("../meeting.wav", b"broken", 415),
    ],
)
async def test_invalid_audio_does_not_create_meeting(
    client: AsyncClient,
    store: LocalArtifactStore,
    filename: str,
    content: bytes,
    expected: int,
) -> None:
    result = await upload(client, filename=filename, content=content)
    assert result.status_code == expected
    assert result.json()["code"] == "unsupported_media_type"
    assert store.list_meetings(OWNER) == []


async def test_oversize_rejected_while_parsing(
    client: AsyncClient, store: LocalArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(uploads, "MAX_AUDIO_BYTES", 100)
    result = await upload(client)
    assert result.status_code == 413
    assert result.json()["code"] == "file_too_large"
    assert store.list_meetings(OWNER) == []


@pytest.mark.parametrize(
    "payload",
    [
        metadata(recording_notice_confirmed=False),
        metadata(meeting_date="2026-02-30"),
        metadata(meeting_date=1_000_000),
        metadata(timezone="Not/A_Zone"),
        metadata(participants=["Алия", "Алия"]),
        metadata(title=""),
        {},
        ["not", "object"],
    ],
)
async def test_invalid_metadata_has_no_meeting(
    client: AsyncClient, store: LocalArtifactStore, payload: object
) -> None:
    result = await upload(client, payload=payload)
    assert result.status_code == 422
    assert result.json() == {
        "detail": "Некорректные данные запроса",
        "code": "invalid_request",
    }
    assert store.list_meetings(OWNER) == []


async def test_bad_metadata_media_type_and_uuid(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    wrong_type = await upload(client, metadata_type="text/plain")
    assert wrong_type.status_code == 422
    assert store.list_meetings(OWNER) == []
    invalid_id = await client.get("/api/v1/meetings/not-a-uuid", headers=HEADERS)
    assert invalid_id.status_code == 422
    assert invalid_id.json()["code"] == "invalid_request"


async def test_missing_parts_are_422_without_meeting(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    missing_audio = await client.post(
        "/api/v1/meetings",
        headers=HEADERS,
        files={"metadata": (None, json.dumps(metadata()), "application/json")},
    )
    missing_metadata = await client.post(
        "/api/v1/meetings",
        headers=HEADERS,
        files={"audio": ("meeting.wav", wav_bytes(), "audio/wav")},
    )
    assert missing_audio.status_code == 422
    assert missing_metadata.status_code == 422
    assert store.list_meetings(OWNER) == []


async def test_staging_failure_is_503_and_creates_no_meeting(
    client: AsyncClient, store: LocalArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_staging() -> Path:
        raise OSError("synthetic failure")

    monkeypatch.setattr(store, "temporary_upload_path", fail_staging)
    result = await upload(client)
    assert result.status_code == 503
    assert result.json()["code"] == "storage_failed"
    assert store.list_meetings(OWNER) == []


async def test_existing_401_shape_is_preserved(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    missing = await client.get("/api/v1/meetings")
    invalid = await client.get(
        "/api/v1/meetings", headers={"Authorization": "Bearer bad"}
    )
    assert missing.json() == {"detail": "Missing bearer token"}
    assert invalid.json() == {"detail": "Invalid or expired access token"}
