"""ntfy notifier (self-hostable; free phone app). Docs: https://docs.ntfy.sh/publish/"""
from __future__ import annotations

import logging

import httpx

from app.notify.base import Notification

log = logging.getLogger(__name__)
PRIORITY = {"high": "5", "default": "3", "low": "2"}


class NtfyNotifier:
    name = "ntfy"

    def __init__(self, server: str, topic: str, token: str = ""):
        self.server, self.topic, self.token = server.rstrip("/"), topic, token

    def send(self, n: Notification) -> bool:
        if not self.topic:
            log.warning("ntfy topic not set; dropping notification %r", n.title)
            return False
        headers = {"Title": n.title.encode("ascii", "ignore").decode(), "Priority": PRIORITY.get(n.priority, "3")}
        if n.tags:
            headers["Tags"] = ",".join(n.tags)
        if n.url:
            headers["Click"] = n.url
        if n.actions:
            headers["Actions"] = "; ".join(f"view, {a['label']}, {a['url']}" for a in n.actions[:3])
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        for attempt in range(3):
            try:
                r = httpx.post(f"{self.server}/{self.topic}", content=n.body.encode("utf-8"), headers=headers, timeout=15)
                if r.status_code < 300:
                    return True
                log.warning("ntfy HTTP %s: %s", r.status_code, r.text[:100])
            except httpx.HTTPError as e:
                log.warning("ntfy send failed (attempt %s): %s", attempt + 1, e)
        return False
