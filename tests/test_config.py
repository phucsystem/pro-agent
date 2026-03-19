import os
import pytest


def test_table_prefix_valid():
    """Valid TABLE_PREFIX patterns should pass validation."""
    from app.config import Settings
    os.environ["TABLE_PREFIX"] = "agent1_"
    os.environ["AUTH_TOKEN"] = "test"
    os.environ["LLM_API_KEY"] = "sk-test"
    config = Settings()
    assert config.table_prefix == "agent1_"
    os.environ.pop("TABLE_PREFIX", None)


def test_table_prefix_invalid():
    """Invalid TABLE_PREFIX should raise ValueError."""
    from app.config import Settings
    os.environ["TABLE_PREFIX"] = "Agent-1!"
    os.environ["AUTH_TOKEN"] = "test"
    os.environ["LLM_API_KEY"] = "sk-test"
    with pytest.raises(Exception):
        Settings()
    os.environ.pop("TABLE_PREFIX", None)


def test_table_prefix_empty_is_valid():
    """Empty TABLE_PREFIX (default) should pass."""
    from app.config import Settings
    os.environ.pop("TABLE_PREFIX", None)
    os.environ["AUTH_TOKEN"] = "test"
    os.environ["LLM_API_KEY"] = "sk-test"
    config = Settings()
    assert config.table_prefix == ""


def test_embedding_dimension_default():
    """Default embedding dimension should be 1536."""
    from app.config import Settings
    os.environ["AUTH_TOKEN"] = "test"
    os.environ["LLM_API_KEY"] = "sk-test"
    os.environ.pop("EMBEDDING_DIMENSION", None)
    config = Settings()
    assert config.embedding_dimension == 1536


def test_embedding_dimension_custom():
    """Custom EMBEDDING_DIMENSION should be accepted."""
    from app.config import Settings
    os.environ["AUTH_TOKEN"] = "test"
    os.environ["LLM_API_KEY"] = "sk-test"
    os.environ["EMBEDDING_DIMENSION"] = "768"
    config = Settings()
    assert config.embedding_dimension == 768
    os.environ.pop("EMBEDDING_DIMENSION", None)


def test_llm_timeout_default():
    """Default LLM_TIMEOUT should be 60."""
    from app.config import Settings
    os.environ["AUTH_TOKEN"] = "test"
    os.environ["LLM_API_KEY"] = "sk-test"
    os.environ.pop("LLM_TIMEOUT", None)
    config = Settings()
    assert config.llm_timeout == 60
