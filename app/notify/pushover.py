"""Pushover notifier (alternative to ntfy)."""
from __future__ import annotations

import logging

import httpx

from app.notify.base import Notification

log = logging.getLogger(__name__)
PRIORITY = {"high": 1, "default": 0, "low": -1}


class PushoverNotifier:
    name = "pushover"

    def __init__(self, user_key: str, app_token: str):
        self.user_key, self.app_token = user_key, app_token

    def send(self, n: Notification) -> bool:
        if not (self.user_key and self.app_token):
            return False
        data = {"token": self.app_token, "user": self.user_key, "title": n.title[:250], "message": n.body[:1024],
                "priority": PRIORITY.get(n.priority, 0)}
        if n.url:
            data["url"] = n.url
            data["url_title"] = "Open deal"
        try:
            r = httpx.post("https://api.pushover.net/1/messages.json", data=data, timeout=15)
            return r.status_code == 200
        except httpx.HTTPError as e:
            log.warning("pushover failed: %s", e)
            return False
