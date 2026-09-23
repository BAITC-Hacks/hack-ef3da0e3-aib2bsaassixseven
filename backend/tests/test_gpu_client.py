import hashlib
import json
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from app.models.gpu import GPUContextV1
from app.models.insights import canonical_json
from app.models.meeting import AudioExtension
from app.services.gpu_client import (
    GPUClient,
    GPUDomainError,
    GPUInputError,
    GPUProtocolError,
    GPUUnavailable,
)

MEETING_ID = UUID("81df6d39-16dd-4227-98b0-d45e531e091e")
JOB_ID = UUID("c0b59629-8ca7-453d-812c-70e3c9e970ac")
HASH = "d25981e522342820a7f13aa73ef6ad1cd92f432fd06b5cd31fe46786fcb11a94"


def context() -> GPUContextV1:
    return GPUContextV1.model_validate(
        {
            "schema_version": 1,
            "meeting_id": str(MEETING_ID),
            "attempt": 2,
            "meeting_date": "2026-09-23",
            "timezone": "Asia/Almaty",
            "participants": ["Алия", "Ернур"],
            "language_hint": "mixed",
            "audio_sha256": hashlib.sha256(b"abc").hexdigest(),
        }
    )


def job() -> dict[str, object]:
    return {
        "job_id": str(JOB_ID),
        "status": "queued",
        "stage": None,
        "failure": None,
        "result_hash": None,
        "cleanup_status": "pending",
        "expires_at": "2026-09-24T09:00:10Z",
        "receipt_expires_at": None,
    }


def bundle() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "job_id": str(JOB_ID),
        "transcript": {
            "schema_version": 1,
            "meeting_id": str(MEETING_ID),
            "revision": 0,
            "speakers": [],
            "segments": [],
        },
        "insights": {
            "schema_version": 1,
            "meeting_id": str(MEETING_ID),
            "revision": 0,
            "summary": [],
            "action_items": [],
        },
        "model_versions": {
            "asr": "fixture-asr@1",
            "diarization": "fixture-diarization@1",
            "analysis": "fixture-analysis@1",
        },
    }
    payload["result_hash"] = hashlib.sha256(canonical_json(payload)).hexdigest()
    return payload


@pytest.mark.asyncio
async def test_submit_exact_multipart_headers_and_stable_key(tmp_path: Path) -> None:
    audio = tmp_path / "private-recording.wav"
    audio.write_bytes(b"abc")
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json=job())

    async with GPUClient(
        "https://gpu.example", "service-secret", transport=httpx.MockTransport(respond)
    ) as client:
        first = await client.submit(audio, context())
        second = await client.submit(audio, context())

    assert first.job_id == second.job_id == JOB_ID
    assert len(requests) == 2
    for request in requests:
        assert request.method == "POST"
        assert str(request.url) == "https://gpu.example/internal/v1/jobs"
        assert request.headers["authorization"] == "Bearer service-secret"
        assert request.headers["idempotency-key"] == f"{MEETING_ID}:2"
        message = BytesParser(policy=default).parsebytes(
            b"Content-Type: "
            + request.headers["content-type"].encode()
            + b"\r\n\r\n"
            + request.read()
        )
        parts = {
            part.get_param("name", header="content-disposition"): part
            for part in message.iter_parts()
        }
        assert set(parts) == {"audio", "context"}
        assert parts["audio"].get_payload(decode=True) == b"abc"
        assert parts["audio"].get_content_type() == "audio/wav"
        assert parts["audio"].get_filename() == "audio.wav"
        assert parts["context"].get_content_type() == "application/json"
        context_payload = parts["context"].get_payload(decode=True)
        assert isinstance(context_payload, bytes)
        assert json.loads(context_payload) == {
            "schema_version": 1,
            "meeting_id": str(MEETING_ID),
            "attempt": 2,
            "meeting_date": "2026-09-23",
            "timezone": "Asia/Almaty",
            "participants": ["Алия", "Ернур"],
            "language_hint": "mixed",
            "audio_sha256": hashlib.sha256(b"abc").hexdigest(),
        }


@pytest.mark.parametrize(
    ("extension", "content_type"),
    [
        (".wav", "audio/wav"),
        (".mp3", "audio/mpeg"),
        (".m4a", "audio/mp4"),
        (".ogg", "audio/ogg"),
        (".webm", "audio/webm"),
    ],
)
async def test_submit_preserves_validated_upload_format_after_private_rename(
    tmp_path: Path, extension: AudioExtension, content_type: str
) -> None:
    audio = tmp_path / "upload.bin"
    audio.write_bytes(b"abc")
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json=job())

    async with GPUClient(
        "https://gpu.example", "service-secret", transport=httpx.MockTransport(respond)
    ) as client:
        await client.submit(audio, context(), audio_extension=extension)

    message = BytesParser(policy=default).parsebytes(
        b"Content-Type: "
        + requests[0].headers["content-type"].encode()
        + b"\r\n\r\n"
        + requests[0].read()
    )
    audio_part = next(
        part
        for part in message.iter_parts()
        if part.get_param("name", header="content-disposition") == "audio"
    )
    assert audio_part.get_content_type() == content_type
    assert audio_part.get_filename() == f"audio{extension}"


@pytest.mark.asyncio
async def test_lookup_by_key_uses_authenticated_path_and_parses_job() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == (
            f"https://gpu.example/internal/v1/jobs/by-key/{MEETING_ID}/2"
        )
        assert request.headers["authorization"] == "Bearer token"
        assert request.read() == b""
        return httpx.Response(200, json=job())

    async with GPUClient(
        "https://gpu.example", "token", transport=httpx.MockTransport(respond)
    ) as client:
        recovered = await client.get_job_by_key(MEETING_ID, 2)
    assert recovered.job_id == JOB_ID


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code"), [(409, "submission_pending"), (404, "job_not_found")]
)
async def test_lookup_by_key_preserves_pending_and_missing_as_distinct_domain_errors(
    status: int, code: str
) -> None:
    async with GPUClient(
        "https://gpu.example",
        "token",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                status, json={"detail": "safe", "code": code}
            )
        ),
    ) as client:
        with pytest.raises(GPUDomainError) as caught:
            await client.get_job_by_key(MEETING_ID, 2)
    assert (caught.value.status_code, caught.value.code) == (status, code)


@pytest.mark.asyncio
async def test_get_result_validates_raw_hash_and_schema() -> None:
    valid = bundle()
    assert valid["result_hash"] == HASH

    async def get(response_payload: dict[str, object]) -> object:
        async with GPUClient(
            "https://gpu.example",
            "token",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json=response_payload)
            ),
        ) as client:
            return await client.get_result(JOB_ID)

    result = await get(valid)
    assert result.result_hash == HASH  # type: ignore[attr-defined]

    bad_hash = {**valid, "result_hash": "0" * 64}
    with pytest.raises(GPUProtocolError, match="Invalid GPU response"):
        await get(bad_hash)
    bad_schema = {**valid, "schema_version": 2}
    bad_schema["result_hash"] = hashlib.sha256(
        canonical_json(
            {key: value for key, value in bad_schema.items() if key != "result_hash"}
        )
    ).hexdigest()
    with pytest.raises(GPUProtocolError, match="Invalid GPU response"):
        await get(bad_schema)


@pytest.mark.asyncio
async def test_timeout_and_transport_errors_are_safe() -> None:
    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret path and body")

    async with GPUClient(
        "https://gpu.example", "token", transport=httpx.MockTransport(timeout)
    ) as client:
        with pytest.raises(GPUUnavailable) as caught:
            await client.get_job(JOB_ID)
    assert caught.value.reason == "timeout"
    assert "secret" not in str(caught.value)

    def connection(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret token")

    async with GPUClient(
        "https://gpu.example", "token", transport=httpx.MockTransport(connection)
    ) as client:
        with pytest.raises(GPUUnavailable) as caught:
            await client.get_job(JOB_ID)
    assert caught.value.reason == "connection"
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_missing_local_audio_error_hides_path(tmp_path: Path) -> None:
    missing = tmp_path / "sensitive-name.wav"
    async with GPUClient(
        "https://gpu.example",
        "token",
        transport=httpx.MockTransport(lambda _: httpx.Response(202, json=job())),
    ) as client:
        with pytest.raises(GPUInputError) as caught:
            await client.submit(missing, context())
    assert "sensitive-name" not in str(caught.value)


@pytest.mark.asyncio
async def test_job_rejects_extra_fields_and_invalid_state() -> None:
    async def get(payload: dict[str, object]) -> None:
        async with GPUClient(
            "https://gpu.example",
            "token",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
        ) as client:
            await client.get_job(JOB_ID)

    with pytest.raises(GPUProtocolError):
        await get({**job(), "internal_path": "/secret"})
    with pytest.raises(GPUProtocolError):
        await get({**job(), "status": "completed"})
    with pytest.raises(GPUProtocolError):
        await get({**job(), "cleanup_status": "deleted"})
    with pytest.raises(GPUProtocolError):
        await get(
            {
                **job(),
                "cleanup_status": "expired",
                "receipt_expires_at": "2026-09-30T09:05:00Z",
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "reason"),
    [
        (401, "unauthorized", "unauthorized"),
        (503, "queue_unavailable", "service_unavailable"),
    ],
)
async def test_transient_internal_errors(status: int, code: str, reason: str) -> None:
    async with GPUClient(
        "https://gpu.example",
        "token",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                status, json={"code": code, "detail": "secret"}
            )
        ),
    ) as client:
        with pytest.raises(GPUUnavailable) as caught:
            await client.get_job(JOB_ID)
    assert caught.value.reason == reason
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code"),
    [(409, "result_not_ready"), (409, "idempotency_conflict"), (410, "source_expired")],
)
async def test_definitive_gpu_errors(status: int, code: str) -> None:
    async with GPUClient(
        "https://gpu.example",
        "token",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                status, json={"code": code, "detail": "secret"}
            )
        ),
    ) as client:
        with pytest.raises(GPUDomainError) as caught:
            await client.get_result(JOB_ID)
    assert (caught.value.status_code, caught.value.code) == (status, code)
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_ack_has_only_hash_and_checks_receipt() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == f"https://gpu.example/internal/v1/jobs/{JOB_ID}/ack"
        assert request.headers["authorization"] == "Bearer token"
        assert request.headers["content-type"] == "application/json"
        assert json.loads(request.read()) == {"result_hash": HASH}
        return httpx.Response(
            200,
            json={
                "job_id": str(JOB_ID),
                "result_hash": HASH,
                "cleanup_status": "deleted",
                "receipt_expires_at": "2026-09-30T09:05:00Z",
            },
        )

    async with GPUClient(
        "https://gpu.example", "token", transport=httpx.MockTransport(respond)
    ) as client:
        receipt = await client.ack(JOB_ID, HASH)
    assert receipt.cleanup_status == "deleted"
