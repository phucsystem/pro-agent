import hmac
from fastapi import Header, HTTPException
from app.config import settings


async def verify_bearer_token(authorization: str = Header(...)) -> None:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization[7:]
    if not hmac.compare_digest(token.encode(), settings.auth_token.encode()):
        raise HTTPException(status_code=401, detail="Unauthorized")
