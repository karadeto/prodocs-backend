from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

_bearer = HTTPBearer(auto_error=False)


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UUID:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            leeway=30,
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token has no sub claim")
    return UUID(sub)
