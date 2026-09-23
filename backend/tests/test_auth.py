from collections.abc import Mapping
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.auth import (
    AuthenticatedUser,
    InvalidAccessToken,
    TokenVerifier,
    get_current_user,
    get_token_verifier,
    validate_claims,
)
from app.core.config import Settings

USER_ID = UUID("11111111-1111-4111-8111-111111111111")


class AcceptingVerifier:
    async def verify(self, token: str) -> AuthenticatedUser:
        if token != "valid":
            raise InvalidAccessToken
        return AuthenticatedUser(
            id=USER_ID,
            email="hacker@example.com",
            role="authenticated",
        )


class RejectingVerifier:
    async def verify(self, token: str) -> AuthenticatedUser:
        raise InvalidAccessToken


def override_verifier(app: FastAPI, verifier: TokenVerifier) -> None:
    app.dependency_overrides[get_token_verifier] = lambda: verifier


async def test_missing_bearer_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing bearer token"}


async def test_invalid_token_returns_401(
    app: FastAPI, client: AsyncClient
) -> None:
    override_verifier(app, RejectingVerifier())

    response = await client.get(
        "/api/v1/me", headers={"Authorization": "Bearer invalid"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired access token"}


async def test_valid_token_returns_verified_identity() -> None:
    user = await get_current_user("valid", AcceptingVerifier())

    assert user == AuthenticatedUser(
        id=USER_ID,
        email="hacker@example.com",
        role="authenticated",
    )


def valid_claims(**updates: Any) -> Mapping[str, Any]:
    claims: dict[str, Any] = {
        "sub": str(USER_ID),
        "email": "hacker@example.com",
        "role": "authenticated",
        "iss": "https://project.supabase.co/auth/v1",
        "aud": "authenticated",
    }
    claims.update(updates)
    return claims


@pytest.mark.parametrize(
    "claims",
    [
        valid_claims(iss="https://attacker.example/auth/v1"),
        valid_claims(aud="anon"),
        valid_claims(sub=None),
    ],
)
def test_invalid_identity_claims_are_rejected(claims: Mapping[str, Any]) -> None:
    settings = Settings(supabase_url="https://project.supabase.co")

    with pytest.raises(InvalidAccessToken):
        validate_claims(claims, settings)
