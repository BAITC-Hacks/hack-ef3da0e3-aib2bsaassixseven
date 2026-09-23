from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

import app.services.profiles as profiles_module
from app.core.auth import AuthenticatedUser, InvalidAccessToken, get_token_verifier
from app.core.config import Settings
from app.models.profile import Profile
from app.services.profiles import (
    ProfileLookupError,
    ProfileRepository,
    SupabaseProfileRepository,
    get_profile_repository,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 9, 22, tzinfo=UTC)


class AcceptingVerifier:
    async def verify(self, token: str) -> AuthenticatedUser:
        if token != "valid":
            raise InvalidAccessToken
        return AuthenticatedUser(
            id=USER_ID,
            email="hacker@example.com",
            role="authenticated",
        )


class FakeProfileRepository:
    def __init__(self, profile: Profile | None) -> None:
        self.profile = profile

    async def get_for_user(
        self, user_id: UUID, access_token: str
    ) -> Profile | None:
        return self.profile


class FailingProfileRepository:
    async def get_for_user(
        self, user_id: UUID, access_token: str
    ) -> Profile | None:
        raise ProfileLookupError


def configure_dependencies(
    app: FastAPI, repository: ProfileRepository
) -> None:
    app.dependency_overrides[get_token_verifier] = lambda: AcceptingVerifier()
    app.dependency_overrides[get_profile_repository] = lambda: repository


async def test_me_returns_identity_and_own_profile(
    app: FastAPI, client: AsyncClient
) -> None:
    profile = Profile(
        id=USER_ID,
        display_name="Hacker",
        created_at=NOW,
        updated_at=NOW,
    )
    configure_dependencies(app, FakeProfileRepository(profile))

    response = await client.get(
        "/api/v1/me", headers={"Authorization": "Bearer valid"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "id": str(USER_ID),
            "email": "hacker@example.com",
            "role": "authenticated",
        },
        "profile": {
            "id": str(USER_ID),
            "display_name": "Hacker",
            "created_at": "2026-09-22T00:00:00Z",
            "updated_at": "2026-09-22T00:00:00Z",
        },
    }


async def test_me_allows_a_missing_profile(
    app: FastAPI, client: AsyncClient
) -> None:
    configure_dependencies(app, FakeProfileRepository(None))

    response = await client.get(
        "/api/v1/me", headers={"Authorization": "Bearer valid"}
    )

    assert response.status_code == 200
    assert response.json()["profile"] is None


async def test_me_maps_profile_failure_to_502(
    app: FastAPI, client: AsyncClient
) -> None:
    configure_dependencies(app, FailingProfileRepository())

    response = await client.get(
        "/api/v1/me", headers={"Authorization": "Bearer valid"}
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Supabase profile request failed"}


class FakePostgrest:
    def __init__(self) -> None:
        self.authorization_token: str | None = None

    def auth(self, token: str) -> None:
        self.authorization_token = token


class FakeQuery:
    def select(self, columns: str) -> "FakeQuery":
        return self

    def eq(self, column: str, value: str) -> "FakeQuery":
        return self

    def maybe_single(self) -> "FakeQuery":
        return self

    async def execute(self) -> SimpleNamespace:
        return SimpleNamespace(
            data={
                "id": str(USER_ID),
                "display_name": "Hacker",
                "created_at": "2026-09-22T00:00:00Z",
                "updated_at": "2026-09-22T00:00:00Z",
            },
            count=None,
        )


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.postgrest = FakePostgrest()

    def table(self, name: str) -> FakeQuery:
        assert name == "profiles"
        return FakeQuery()


async def test_repository_forwards_access_token_to_postgrest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeSupabaseClient()

    async def create_fake_client(url: str, key: str) -> FakeSupabaseClient:
        return client

    monkeypatch.setattr(profiles_module, "create_async_client", create_fake_client)
    repository = SupabaseProfileRepository(Settings())

    profile = await repository.get_for_user(USER_ID, "access-token")

    assert client.postgrest.authorization_token == "access-token"
    assert profile is not None
    assert profile.id == USER_ID
