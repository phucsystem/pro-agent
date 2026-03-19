import re
import yaml
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


def _load_agent_yaml() -> dict:
    path = Path("agent.yaml")
    if not path.exists():
        return {}
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


_yaml = _load_agent_yaml()
_model_cfg = _yaml.get("model", {})
_memory_cfg = _yaml.get("memory", {})
_tools_cfg = _yaml.get("tools", {})
_cost_cfg = _yaml.get("cost", {})


class Settings(BaseSettings):
    auth_token: str = Field(alias="AUTH_TOKEN")
    llm_api_key: str = Field(alias="LLM_API_KEY")
    llm_provider: str = Field(default="deepseek", alias="LLM_PROVIDER")
    llm_model: str = Field(default="deepseek-chat", alias="LLM_MODEL")
    llm_base_url: str = Field(default="https://api.deepseek.com/v1", alias="LLM_BASE_URL")
    llm_timeout: int = Field(default=60, alias="LLM_TIMEOUT")
    table_prefix: str = Field(default="", alias="TABLE_PREFIX")
    port: int = Field(default=8000, alias="PORT")
    postgres_url: str = Field(
        default="postgresql://agent:agent@localhost:5432/pro_agent",
        alias="POSTGRES_URL",
    )
    db_pool_min: int = Field(default=2, alias="DB_POOL_MIN")
    db_pool_max: int = Field(default=10, alias="DB_POOL_MAX")
    db_statement_timeout: int = Field(default=30, alias="DB_STATEMENT_TIMEOUT")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    search_api_key: str = Field(default="", alias="SEARCH_API_KEY")
    file_io_sandbox_dir: str = Field(default="/app/sandbox", alias="FILE_IO_SANDBOX_DIR")

    # From agent.yaml
    agent_name: str = _yaml.get("name", "Pro Agent")
    agent_role: str = _yaml.get("role", "A versatile assistant")
    agent_style: str = _yaml.get("style", "Concise and direct")
    model_temperature: float = _model_cfg.get("temperature", 0.7)
    model_max_tokens: int = _model_cfg.get("max_tokens", 4096)
    memory_top_k_turns: int = _memory_cfg.get("top_k_turns", 10)
    memory_top_k_facts: int = _memory_cfg.get("top_k_facts", 5)
    memory_similarity_threshold: float = _memory_cfg.get("similarity_threshold", 0.7)
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=1536, alias="EMBEDDING_DIMENSION")
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    embedding_api_base: str = Field(default="", alias="EMBEDDING_API_BASE")
    tools_max_calls_per_turn: int = _tools_cfg.get("max_calls_per_turn", 5)
    tools_timeout_seconds: int = _tools_cfg.get("timeout_seconds", 30)
    tools_enabled: list[str] = _tools_cfg.get("enabled", [])
    cost_max_per_request: float = _cost_cfg.get("max_per_request", 1.00)

    @field_validator("table_prefix")
    @classmethod
    def validate_table_prefix(cls, value: str) -> str:
        if value and not re.match(r"^[a-z0-9_]+$", value):
            raise ValueError("TABLE_PREFIX must match ^[a-z0-9_]+$ (lowercase, digits, underscores)")
        return value

    @field_validator("embedding_dimension")
    @classmethod
    def validate_embedding_dimension(cls, value: int) -> int:
        if value < 1 or value > 8192:
            raise ValueError("EMBEDDING_DIMENSION must be between 1 and 8192")
        return value

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
