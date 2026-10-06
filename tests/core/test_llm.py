from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from core.llm import LLM, PRICES, CallLimitExceeded, Refused, Truncated


class Answer(BaseModel):
    value: str


class StubMessages:
    """Stands in for client.messages; returns a canned response and records calls."""

    def __init__(self, stop_reason: str = "end_turn", parsed: Answer | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response = SimpleNamespace(
            stop_reason=stop_reason,
            parsed_output=parsed if parsed is not None else Answer(value="ok"),
            usage=SimpleNamespace(input_tokens=1000, output_tokens=50),
        )

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return self._response


def _llm(messages: StubMessages, max_calls: int = 10) -> LLM:
    client: Any = SimpleNamespace(messages=messages)
    return LLM(client, model="claude-haiku-4-5", max_calls=max_calls)


def test_parse_returns_validated_output_and_tracks_usage() -> None:
    messages = StubMessages()
    llm = _llm(messages)

    result = llm.parse("system", "user", Answer)

    assert result == Answer(value="ok")
    assert messages.calls[0]["output_format"] is Answer
    assert llm.usage.calls == 1
    assert llm.usage.input_tokens == 1000
    expected = (1000 * 1.00 + 50 * 5.00) / 1_000_000
    assert llm.usd_spent == pytest.approx(expected)


def test_call_cap_stops_before_calling_the_api() -> None:
    messages = StubMessages()
    llm = _llm(messages, max_calls=2)
    llm.parse("s", "u", Answer)
    llm.parse("s", "u", Answer)

    with pytest.raises(CallLimitExceeded):
        llm.parse("s", "u", Answer)
    assert len(messages.calls) == 2


@pytest.mark.parametrize(
    ("stop_reason", "error"), [("refusal", Refused), ("max_tokens", Truncated)]
)
def test_bad_stop_reasons_raise(stop_reason: str, error: type[Exception]) -> None:
    llm = _llm(StubMessages(stop_reason=stop_reason))
    with pytest.raises(error):
        llm.parse("s", "u", Answer)


def test_unknown_model_is_rejected() -> None:
    client: Any = SimpleNamespace(messages=StubMessages())
    with pytest.raises(ValueError, match="no price"):
        LLM(client, model="claude-imaginary-1", max_calls=1)


def test_default_model_has_a_price() -> None:
    assert "claude-haiku-4-5" in PRICES
