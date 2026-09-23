"""Public meeting API tests use generated WAV and tiny encoded audio fixtures."""

import io
import json
import os
import time
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
FIXTURES = Path(__file__).parent / "fixtures"


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
    assert record.audio_extension == ".wav"
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


async def test_browser_recording_source_survives_read_and_list(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    encoded_audio = (FIXTURES / "browser-recording.webm").read_bytes()
    response = await upload(
        client,
        filename="recording.webm",
        content=encoded_audio,
        payload=metadata(source_kind="browser_recording"),
    )
    assert response.status_code == 202
    meeting = response.json()
    assert meeting["source"]["kind"] == "browser_recording"
    assert "source_kind" not in meeting
    meeting_id = meeting["id"]
    read = await client.get(f"/api/v1/meetings/{meeting_id}", headers=HEADERS)
    listed = await client.get("/api/v1/meetings", headers=HEADERS)
    assert read.json()["source"]["kind"] == "browser_recording"
    assert listed.json()["items"][0]["source"]["kind"] == "browser_recording"
    assert store.upload_path(OWNER, UUID(meeting_id)).read_bytes() == encoded_audio
    assert store.read_record(OWNER, UUID(meeting_id)).audio_extension == ".webm"


@pytest.mark.parametrize("extension", [".mp3", ".m4a", ".ogg"])
async def test_existing_encoded_upload_formats_preserve_their_extension(
    client: AsyncClient, store: LocalArtifactStore, extension: str
) -> None:
    encoded_audio = (FIXTURES / f"upload{extension}").read_bytes()
    response = await upload(
        client, filename=f"upload{extension}", content=encoded_audio
    )
    assert response.status_code == 202
    meeting_id = UUID(response.json()["id"])
    assert response.json()["source"]["kind"] == "uploaded_audio"
    assert store.read_record(OWNER, meeting_id).audio_extension == extension
    assert store.upload_path(OWNER, meeting_id).read_bytes() == encoded_audio


@pytest.mark.parametrize(
    "fixture",
    ["webm-vorbis.webm", "matroska-opus.mkv"],
)
async def test_browser_recording_rejects_non_webm_opus(
    client: AsyncClient, store: LocalArtifactStore, fixture: str
) -> None:
    response = await upload(
        client,
        filename="recording.webm",
        content=(FIXTURES / fixture).read_bytes(),
        payload=metadata(source_kind="browser_recording"),
    )
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_media_type"
    assert store.list_meetings(OWNER) == []


@pytest.mark.parametrize("source_kind", ["demo_fixture", "unknown", None, 1])
async def test_public_upload_rejects_invalid_source_kind(
    client: AsyncClient, store: LocalArtifactStore, source_kind: object
) -> None:
    result = await upload(client, payload=metadata(source_kind=source_kind))
    assert result.status_code == 422
    assert store.list_meetings(OWNER) == []


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


async def test_native_formdata_metadata_field_without_content_type(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    result = await upload(client, metadata_type="")
    assert result.status_code == 202
    assert len(store.list_meetings(OWNER)) == 1


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


async def test_post_rename_sync_failure_is_503_without_visible_meeting(
    client: AsyncClient, store: LocalArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_sync = store._sync_directory  # pyright: ignore[reportPrivateUsage]
    meetings_parent = store.root / "users" / str(OWNER) / "meetings"
    failed = False

    def fail_once(path: Path) -> None:
        nonlocal failed
        if (
            path.parent == meetings_parent
            and (path / "meeting.json").exists()
            and not failed
        ):
            failed = True
            raise OSError("synthetic post-rename failure")
        original_sync(path)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_sync_directory", fail_once)
        result = await upload(client)
    assert failed
    assert result.status_code == 503
    assert result.json()["code"] == "storage_failed"
    assert LocalArtifactStore(store.root).list_meetings(OWNER) == []


async def test_post_commit_staging_unlink_failure_still_returns_202_and_sweeps(
    client: AsyncClient, store: LocalArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_unlink = Path.unlink

    def fail_staging_unlink(path: Path, missing_ok: bool = False) -> None:
        if path.suffix == ".upload":
            raise OSError("synthetic staging cleanup failure")
        original_unlink(path, missing_ok=missing_ok)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_staging_unlink)
        result = await upload(client)
    assert result.status_code == 202
    meeting_id = UUID(result.json()["id"])
    assert store.read_meeting(OWNER, meeting_id).status == "queued"
    staged = list((store.root / "uploads").glob("*.upload"))
    assert len(staged) == 1
    old = time.time() - 25 * 3600
    os.utime(staged[0], (old, old))
    new_staged = store.temporary_upload_path()
    assert not staged[0].exists()
    new_staged.unlink()


@pytest.mark.parametrize("truncated", ["missing_frames", "partial_frame"])
async def test_truncated_wav_is_rejected(
    client: AsyncClient, store: LocalArtifactStore, truncated: str
) -> None:
    data = bytearray(wav_bytes())
    if truncated == "missing_frames":
        data[4:8] = (36 + 16000).to_bytes(4, "little")
        data[40:44] = (16000).to_bytes(4, "little")
    else:
        data = data[:45]
    result = await upload(client, content=bytes(data))
    assert result.status_code == 415
    assert result.json()["code"] == "unsupported_media_type"
    assert store.list_meetings(OWNER) == []


async def test_oversized_stream_stops_early_and_closes_spool(
    client: AsyncClient,
    store: LocalArtifactStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tempfile import SpooledTemporaryFile

    import starlette.formparsers as formparsers

    files: list[SpooledTemporaryFile[bytes]] = []
    continued = False

    def tracked_spool(*args: object, **kwargs: object) -> SpooledTemporaryFile[bytes]:
        spool: SpooledTemporaryFile[bytes] = SpooledTemporaryFile(max_size=1024)  # noqa: SIM115
        files.append(spool)
        return spool

    async def body():  # pyright: ignore[reportUnknownParameterType,reportMissingParameterType]
        nonlocal continued
        yield (
            b'--test-boundary\r\nContent-Disposition: form-data; name="audio"; '
            b'filename="meeting.wav"\r\nContent-Type: audio/wav\r\n\r\n' + b"x" * 101
        )
        continued = True
        yield b"--test-boundary--\r\n"

    monkeypatch.setattr(uploads, "MAX_AUDIO_BYTES", 100)
    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", tracked_spool)
    result = await client.post(
        "/api/v1/meetings",
        headers={
            **HEADERS,
            "Content-Type": "multipart/form-data; boundary=test-boundary",
        },
        content=body(),
    )
    assert result.status_code == 413
    assert not continued
    assert files and all(item.closed for item in files)
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
