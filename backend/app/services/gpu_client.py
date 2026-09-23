"""Authenticated, transport-injectable client for the internal GPU API."""

import json
from pathlib import Path
from typing import TypeVar, cast
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

from app.models.gpu import AckV1, GPUContextV1, JobV1
from app.models.insights import ResultBundleV1, Sha256

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)

_DOMAIN_CODES: dict[int, frozenset[str]] = {
    404: frozenset({"job_not_found"}),
    409: frozenset(
        {
            "idempotency_conflict",
            "result_not_ready",
            "job_failed",
            "result_hash_mismatch",
        }
    ),
    410: frozenset({"payload_deleted", "source_expired"}),
    413: frozenset({"file_too_large"}),
    415: frozenset({"unsupported_media_type"}),
    422: frozenset({"invalid_request"}),
}
_AUDIO_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
}


class GPUClientError(Exception):
    """Safe base error; never contains a remote detail or request content."""


class GPUUnavailable(GPUClientError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"GPU unavailable: {reason}")


class GPUDomainError(GPUClientError):
    def __init__(self, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(f"GPU rejected operation: {code}")


class GPUProtocolError(GPUClientError):
    def __init__(self) -> None:
        super().__init__("Invalid GPU response")


class GPUInputError(GPUClientError):
    def __init__(self) -> None:
        super().__init__("GPU audio source is unavailable")


class GPUClient:
    """One operation per call; submit never retries or changes the attempt."""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not service_token:
            raise ValueError("GPU service token is required")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/internal/v1/",
            headers={"Authorization": f"Bearer {service_token}"},
            transport=transport,
            timeout=timeout,
        )

    async def __aenter__(self) -> "GPUClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def submit(self, audio_path: Path, context: GPUContextV1) -> JobV1:
        suffix = audio_path.suffix.lower()
        content_type = _AUDIO_TYPES.get(suffix, "application/octet-stream")
        headers = {"Idempotency-Key": f"{context.meeting_id}:{context.attempt}"}
        context_json = json.dumps(
            context.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        try:
            with audio_path.open("rb") as audio:
                request = self._client.build_request(
                    "POST",
                    "jobs",
                    headers=headers,
                    files={
                        "audio": (f"audio{suffix}", audio, content_type),
                        "context": (None, context_json, "application/json"),
                    },
                )
                response = await self._send(request, 202)
        except OSError:
            raise GPUInputError() from None
        return self._parse(response, JobV1)

    async def get_job(self, job_id: UUID) -> JobV1:
        response = await self._send(
            self._client.build_request("GET", f"jobs/{job_id}"), 200
        )
        job = self._parse(response, JobV1)
        if job.job_id != job_id:
            raise GPUProtocolError()
        return job

    async def get_result(self, job_id: UUID) -> ResultBundleV1:
        response = await self._send(
            self._client.build_request("GET", f"jobs/{job_id}/result"), 200
        )
        bundle = self._parse(response, ResultBundleV1)
        if bundle.job_id != job_id:
            raise GPUProtocolError()
        return bundle

    async def ack(self, job_id: UUID, result_hash: Sha256) -> AckV1:
        response = await self._send(
            self._client.build_request(
                "POST", f"jobs/{job_id}/ack", json={"result_hash": result_hash}
            ),
            200,
        )
        receipt = self._parse(response, AckV1)
        if receipt.job_id != job_id or receipt.result_hash != result_hash:
            raise GPUProtocolError()
        return receipt

    async def _send(
        self, request: httpx.Request, expected_status: int
    ) -> httpx.Response:
        try:
            response = await self._client.send(request)
        except httpx.TimeoutException:
            raise GPUUnavailable("timeout") from None
        except httpx.RequestError:
            raise GPUUnavailable("connection") from None
        if response.status_code == expected_status:
            return response
        if response.status_code == 401:
            raise GPUUnavailable("unauthorized")
        if response.status_code >= 500:
            raise GPUUnavailable("service_unavailable")
        codes = _DOMAIN_CODES.get(response.status_code)
        if codes is None:
            raise GPUProtocolError()
        try:
            body_value: object = response.json()
        except ValueError:
            raise GPUProtocolError() from None
        if not isinstance(body_value, dict):
            raise GPUProtocolError()
        body = cast(dict[str, object], body_value)
        code = body.get("code")
        if not isinstance(code, str) or code not in codes:
            raise GPUProtocolError()
        raise GPUDomainError(response.status_code, code)

    @staticmethod
    def _parse(response: httpx.Response, model: type[ResponseModel]) -> ResponseModel:
        try:
            return model.model_validate_json(response.content)
        except (ValidationError, ValueError):
            raise GPUProtocolError() from None
