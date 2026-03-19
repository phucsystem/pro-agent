import pytest
from unittest.mock import patch
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_verify_bearer_token_valid():
    """Valid bearer token should not raise."""
    from app.auth import verify_bearer_token
    with patch("app.auth.settings") as mock_settings:
        mock_settings.auth_token = "correct-token"
        await verify_bearer_token(authorization="Bearer correct-token")


@pytest.mark.asyncio
async def test_verify_bearer_token_invalid():
    """Invalid bearer token should raise 401."""
    from app.auth import verify_bearer_token
    with patch("app.auth.settings") as mock_settings:
        mock_settings.auth_token = "correct-token"
        with pytest.raises(HTTPException) as exc_info:
            await verify_bearer_token(authorization="Bearer wrong-token")
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_bearer_token_missing():
    """Missing Authorization header should raise 401."""
    from app.auth import verify_bearer_token
    with patch("app.auth.settings") as mock_settings:
        mock_settings.auth_token = "correct-token"
        with pytest.raises(HTTPException) as exc_info:
            await verify_bearer_token(authorization="")
        assert exc_info.value.status_code == 401
