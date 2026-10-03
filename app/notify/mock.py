"""In-memory notifier for tests and MOCK_MODE (also logs to stdout)."""
from __future__ import annotations

import logging

from app.notify.base import Notification

log = logging.getLogger(__name__)


class MockNotifier:
    name = "mock"

    def __init__(self):
        self.sent: list[Notification] = []

    def send(self, n: Notification) -> bool:
        self.sent.append(n)
        log.info("[MOCK PUSH %s] %s | %s", n.priority.upper(), n.title, n.body.replace("\n", " / ")[:200])
        return True
