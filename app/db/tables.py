from app.config import settings

_prefix = settings.table_prefix

SESSIONS = f"{_prefix}sessions"
CONVERSATION_TURNS = f"{_prefix}conversation_turns"
USER_FACTS = f"{_prefix}user_facts"
TOOL_CALL_LOGS = f"{_prefix}tool_call_logs"
