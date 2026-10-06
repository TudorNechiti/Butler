import json

import httpx
import pytest
from pydantic import SecretStr

from core.telegram import MAX_MESSAGE_CHARS, TelegramClient, TelegramError

TOKEN = "123456:SECRET-BOT-TOKEN"


def _client(handler: httpx.MockTransport) -> TelegramClient:
    return TelegramClient(SecretStr(TOKEN), chat_id="42", http=httpx.Client(transport=handler))


def test_sends_plain_text_without_parse_mode() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    _client(httpx.MockTransport(handle)).send_message("<b>hi</b> " + "x" * 5000)

    body = json.loads(requests[0].content)
    assert body["chat_id"] == "42"
    assert "parse_mode" not in body
    assert body["link_preview_options"] == {"is_disabled": True}
    assert len(body["text"]) == MAX_MESSAGE_CHARS


def test_http_error_does_not_leak_token() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(401))
    with pytest.raises(TelegramError) as excinfo:
        _client(transport).send_message("hi")
    assert TOKEN not in str(excinfo.value)
    assert "401" in str(excinfo.value)


def test_network_error_does_not_leak_token() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}")

    with pytest.raises(TelegramError) as excinfo:
        _client(httpx.MockTransport(fail)).send_message("hi")
    assert TOKEN not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
