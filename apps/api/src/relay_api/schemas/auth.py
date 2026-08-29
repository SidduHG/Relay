import uuid
from datetime import datetime

from pydantic import BaseModel


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str

    model_config = {"from_attributes": True}


class ApiKeyCreateRequest(BaseModel):
    name: str


class ApiKeyCreateResponse(BaseModel):
    """The only response that ever carries the raw secret — issued once,
    never retrievable again. ApiKeyOut (list/read) never includes it."""

    id: uuid.UUID
    secret: str
    prefix: str
    name: str


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    prefix: str
    name: str
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
