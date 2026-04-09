import datetime


class SessionLogAccumulator:
    """Accumulates plain-text, timestamped log entries for a session."""

    def __init__(self) -> None:
        self._logs: list[str] = []

    def add_log_entry(self, message: str):
        timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        self._logs.append(f"{timestamp} | {message}")

    def get_log_contents(self) -> str:
        return "\n".join(self._logs)
