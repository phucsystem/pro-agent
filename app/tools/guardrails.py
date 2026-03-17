import time
import logging

logger = logging.getLogger(__name__)


class ToolGuardrails:
    def __init__(self, max_calls: int = 5, timeout_seconds: int = 30):
        self.max_calls = max_calls
        self.timeout_seconds = timeout_seconds
        self._call_count = 0
        self._start_time = time.time()

    def reset(self) -> None:
        self._call_count = 0
        self._start_time = time.time()

    def check(self) -> tuple[bool, str | None]:
        """Return (allowed, block_reason). Increments counter if allowed."""
        if self._call_count >= self.max_calls:
            reason = f"Tool call limit reached ({self.max_calls})"
            logger.warning(reason)
            return False, reason
        elapsed = time.time() - self._start_time
        if elapsed > self.timeout_seconds * self.max_calls:
            reason = "Total tool execution time exceeded"
            logger.warning(reason)
            return False, reason
        self._call_count += 1
        return True, None

    @property
    def call_count(self) -> int:
        return self._call_count
