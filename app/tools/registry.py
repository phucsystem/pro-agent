import logging
from functools import lru_cache
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)
_tools: list[BaseTool] = []


def _build_web_search_tool() -> BaseTool | None:
    try:
        from langchain_community.tools import DuckDuckGoSearchRun
        return DuckDuckGoSearchRun(name="web_search")
    except Exception as exc:
        logger.warning(f"web_search tool unavailable: {exc}")
        return None


def _build_github_tool() -> BaseTool | None:
    from app.config import settings
    if not settings.github_token:
        return None
    try:
        from langchain_community.tools.github.tool import GitHubAction
        from langchain_community.utilities.github import GitHubAPIWrapper
        wrapper = GitHubAPIWrapper(github_app_private_key=settings.github_token)
        return GitHubAction(api_wrapper=wrapper, mode="get_issues", name="github")
    except Exception as exc:
        logger.warning(f"github tool unavailable: {exc}")
        return None


def _build_file_io_tool() -> BaseTool | None:
    from app.config import settings
    from pathlib import Path
    try:
        from langchain_community.tools import ReadFileTool, WriteFileTool
        sandbox = Path(settings.file_io_sandbox_dir)
        sandbox.mkdir(parents=True, exist_ok=True)

        # Custom sandboxed tool wrapping ReadFileTool
        from langchain_core.tools import tool

        @tool
        def file_read(path: str) -> str:
            """Read a file from the sandbox directory. Path must be relative."""
            safe = (sandbox / path).resolve()
            sandbox_str = str(sandbox.resolve()) + "/"
            if not str(safe).startswith(sandbox_str):
                return "Error: path outside sandbox"
            if not safe.exists():
                return f"Error: file not found: {path}"
            return safe.read_text()[:4000]

        @tool
        def file_write(path: str, content: str) -> str:
            """Write content to a file in the sandbox directory. Path must be relative. Max 100KB."""
            safe = (sandbox / path).resolve()
            sandbox_str = str(sandbox.resolve()) + "/"
            if not str(safe).startswith(sandbox_str):
                return "Error: path outside sandbox"
            if len(content) > 100_000:
                return "Error: content exceeds 100KB limit"
            safe.parent.mkdir(parents=True, exist_ok=True)
            safe.write_text(content)
            return f"Written {len(content)} bytes to {path}"

        return [file_read, file_write]
    except Exception as exc:
        logger.warning(f"file_io tool unavailable: {exc}")
        return None


def load_tools() -> list[BaseTool]:
    from app.config import settings
    result = []
    for tool_name in settings.tools_enabled:
        if tool_name == "web_search":
            t = _build_web_search_tool()
            if t:
                result.append(t)
        elif tool_name == "github":
            t = _build_github_tool()
            if t:
                result.append(t)
        elif tool_name == "file_io":
            ts = _build_file_io_tool()
            if ts:
                if isinstance(ts, list):
                    result.extend(ts)
                else:
                    result.append(ts)
    logger.info(f"Loaded {len(result)} tools: {[t.name for t in result]}")
    return result


_registered_tools: list[BaseTool] | None = None


def get_registered_tools() -> list[BaseTool]:
    global _registered_tools
    if _registered_tools is None:
        _registered_tools = load_tools()
    return _registered_tools
