from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends
from supabase import create_async_client

from app.core.config import Settings, get_settings
from app.models.profile import Profile


class ProfileLookupError(Exception):
    """Raised when Supabase cannot return the caller's profile."""


class ProfileRepository(Protocol):
    async def get_for_user(
        self, user_id: UUID, access_token: str
    ) -> Profile | None: ...


class SupabaseProfileRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_for_user(
        self, user_id: UUID, access_token: str
    ) -> Profile | None:
        try:
            client = await create_async_client(
                self._settings.supabase_url,
                self._settings.supabase_publishable_key,
            )
            client.postgrest.auth(access_token)
            response = await (
                client.table("profiles")
                .select("id,display_name,created_at,updated_at")
                .eq("id", str(user_id))
                .maybe_single()
                .execute()
            )
            if response is None or response.data is None:
                return None
            return Profile.model_validate(response.data)
        except Exception as error:
            raise ProfileLookupError from error


def get_profile_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProfileRepository:
    return SupabaseProfileRepository(settings)

