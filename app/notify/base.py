"""Notifier interface + message type."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Notification:
    title: str
    body: str
    priority: str = "default"       # high | default | low
    url: str = ""                   # click-through (dashboard deal page)
    actions: list[dict] = field(default_factory=list)   # [{"label": "Listing", "url": ...}]
    tags: list[str] = field(default_factory=list)


class Notifier(Protocol):
    name: str

    def send(self, n: Notification) -> bool: ...
