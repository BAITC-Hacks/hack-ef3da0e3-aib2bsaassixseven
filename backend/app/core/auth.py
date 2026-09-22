from collections.abc import Mapping
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from supabase import create_async_client
from supabase_auth.errors import AuthError

from app.core.config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


class InvalidAccessToken(Exception):
    """Raised when a bearer token cannot identify a trusted Supabase user."""


class AuthenticatedUser(BaseModel):
    id: UUID
    email: str | None = None
    role: str


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> AuthenticatedUser: ...


def validate_claims(
    claims: Mapping[str, Any], settings: Settings
) -> AuthenticatedUser:
    expected_issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
    if claims.get("iss") != expected_issuer:
        raise InvalidAccessToken

    audience = claims.get("aud")
    audiences = {audience} if isinstance(audience, str) else set(audience or [])
    if settings.supabase_jwt_audience not in audiences:
        raise InvalidAccessToken

    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidAccessToken from error

    email = claims.get("email")
    role = claims.get("role")
    return AuthenticatedUser(
        id=user_id,
        email=email if isinstance(email, str) else None,
        role=role if isinstance(role, str) else settings.supabase_jwt_audience,
    )


class SupabaseTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def verify(self, token: str) -> AuthenticatedUser:
        try:
            client = await create_async_client(
                self._settings.supabase_url,
                self._settings.supabase_publishable_key,
            )
            response = await client.auth.get_claims(jwt=token)
            if response is None:
                raise InvalidAccessToken
            return validate_claims(response["claims"], self._settings)
        except (AuthError, KeyError, TypeError, ValueError) as error:
            raise InvalidAccessToken from error


def get_token_verifier(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenVerifier:
    return SupabaseTokenVerifier(settings)


def get_access_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


async def get_current_user(
    token: Annotated[str, Depends(get_access_token)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> AuthenticatedUser:
    try:
        return await verifier.verify(token)
    except InvalidAccessToken as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

