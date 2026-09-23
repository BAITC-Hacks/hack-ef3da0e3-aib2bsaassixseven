from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class Profile(BaseModel):
    id: UUID
    display_name: str | None = None
    created_at: datetime
    updated_at: datetime

