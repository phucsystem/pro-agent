import os
import pytest

os.environ.setdefault("AUTH_TOKEN", "test-token-for-testing")
os.environ.setdefault("LLM_API_KEY", "sk-test")
os.environ.setdefault("LLM_PROVIDER", "deepseek")
os.environ.setdefault("LLM_MODEL", "deepseek-chat")
os.environ.setdefault("POSTGRES_URL", "postgresql://agent:agent@localhost:5432/pro_agent")
