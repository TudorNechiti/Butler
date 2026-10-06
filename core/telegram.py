"""Send plain-text messages to one configured Telegram chat."""

from __future__ import annotations

import httpx
from pydantic import SecretStr

API_BASE = "https://api.telegram.org"
MAX_MESSAGE_CHARS = 4096  # Telegram's hard limit per message


class TelegramError(Exception):
    pass


class TelegramClient:
    def __init__(
        self, bot_token: SecretStr, chat_id: str, http: httpx.Client | None = None
    ) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._http = http or httpx.Client(timeout=10)

    def send_message(self, text: str) -> None:
        # No parse_mode: text is sent literally, so content from emails can't inject
        # formatting or disguised links. Link previews are off for the same reason.
        url = f"{API_BASE}/bot{self._token.get_secret_value()}/sendMessage"
        body = {
            "chat_id": self._chat_id,
            "text": text[:MAX_MESSAGE_CHARS],
            "link_preview_options": {"is_disabled": True},
        }
        try:
            response = self._http.post(url, json=body)
        except httpx.HTTPError as exc:
            # httpx errors can include the URL, which contains the bot token; drop the chain.
            raise TelegramError(f"request failed: {type(exc).__name__}") from None
        if response.is_error:
            raise TelegramError(f"Telegram API returned HTTP {response.status_code}")
