import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok():
    """Health endpoint should return 200 with status ok (no auth required)."""
    with patch("app.main.settings") as mock_settings:
        mock_settings.auth_token = "test-token"
        mock_settings.llm_provider = "deepseek"
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.langfuse_public_key = ""
        mock_settings.langfuse_secret_key = ""
        mock_settings.langfuse_host = ""
        mock_settings.postgres_url = "postgresql://agent:agent@localhost:5432/pro_agent"
        mock_settings.db_pool_min = 2
        mock_settings.db_pool_max = 10
        mock_settings.db_statement_timeout = 30

        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "uptime" in data
            assert "memory_stats" in data


@pytest.mark.asyncio
async def test_health_no_auth_required():
    """Health endpoint should NOT require authentication."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
