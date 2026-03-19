import logging
import httpx
from langchain_core.tools import BaseTool, tool

logger = logging.getLogger(__name__)


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

    @tool
    async def github(query: str) -> str:
        """Search GitHub issues and repositories. Query format: 'owner/repo' for repo info, or 'owner/repo issues' for open issues."""
        token = settings.github_token
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            parts = query.strip().split()
            repo = parts[0] if parts else query
            action = parts[1] if len(parts) > 1 else "info"

            async with httpx.AsyncClient(timeout=15) as client:
                if action == "issues":
                    url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page=10"
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    issues = response.json()
                    if not issues:
                        return f"No open issues in {repo}"
                    lines = [f"#{iss['number']}: {iss['title']}" for iss in issues[:10]]
                    return f"Open issues in {repo}:\n" + "\n".join(lines)
                else:
                    url = f"https://api.github.com/repos/{repo}"
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    return (
                        f"{data['full_name']}: {data.get('description', 'No description')}\n"
                        f"Stars: {data['stargazers_count']} | Forks: {data['forks_count']} | "
                        f"Language: {data.get('language', 'N/A')}"
                    )
        except httpx.HTTPStatusError as exc:
            return f"Error: GitHub API returned {exc.response.status_code}"
        except Exception as exc:
            return f"Error: {exc}"

    return github


def _build_file_io_tool() -> list[BaseTool] | None:
    from app.config import settings
    from pathlib import Path
    try:
        sandbox = Path(settings.file_io_sandbox_dir)
        sandbox.mkdir(parents=True, exist_ok=True)

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
            built = _build_web_search_tool()
            if built:
                result.append(built)
        elif tool_name == "github":
            built = _build_github_tool()
            if built:
                result.append(built)
        elif tool_name == "file_io":
            built = _build_file_io_tool()
            if built:
                if isinstance(built, list):
                    result.extend(built)
                else:
                    result.append(built)
    logger.info(f"Loaded {len(result)} tools: {[t.name for t in result]}")
    return result


_registered_tools: list[BaseTool] | None = None


def get_registered_tools() -> list[BaseTool]:
    global _registered_tools
    if _registered_tools is None:
        _registered_tools = load_tools()
    return _registered_tools
