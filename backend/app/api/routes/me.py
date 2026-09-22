from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import AuthenticatedUser, get_access_token, get_current_user
from app.models.profile import Profile
from app.services.profiles import (
    ProfileLookupError,
    ProfileRepository,
    get_profile_repository,
)

router = APIRouter(tags=["account"])


class MeResponse(BaseModel):
    user: AuthenticatedUser
    profile: Profile | None


@router.get("/me", response_model=MeResponse)
async def read_me(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    access_token: Annotated[str, Depends(get_access_token)],
    profiles: Annotated[ProfileRepository, Depends(get_profile_repository)],
) -> MeResponse:
    try:
        profile = await profiles.get_for_user(user.id, access_token)
    except ProfileLookupError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase profile request failed",
        ) from error
    return MeResponse(user=user, profile=profile)
