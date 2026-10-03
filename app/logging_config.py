"""Logging setup. Never log credentials or seller personal data."""
import logging
import re
import sys

_SECRET_RE = re.compile(r"(api[_-]?key|token|secret|password|authorization)[=:]\s*\S+", re.I)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return _SECRET_RE.sub(lambda m: f"{m.group(1)}=***", msg)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    logging.getLogger("apscheduler").setLevel("WARNING")
    logging.getLogger("httpx").setLevel("WARNING")
    logging.getLogger("httpx2").setLevel("WARNING")
    logging.getLogger("httpcore").setLevel("WARNING")
