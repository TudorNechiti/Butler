"""Thin wrapper around the Anthropic SDK: one structured call, a hard call cap, cost tracking.

Agents never get tools from here. The model returns a schema-validated object and plain agent
code decides what to do with it.
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic
from pydantic import BaseModel


@dataclass(frozen=True)
class ModelPrice:
    input_usd_per_mtok: float
    output_usd_per_mtok: float


# Standard first-party API prices. Update these when switching models; unknown models are
# rejected so the cost estimate can't silently be wrong.
PRICES: dict[str, ModelPrice] = {
    "claude-haiku-4-5": ModelPrice(1.00, 5.00),
    "claude-sonnet-5-5": ModelPrice(2.00, 10.00),
}


class LLMError(Exception):
    pass


class CallLimitExceeded(LLMError):
    pass


class Refused(LLMError):
    pass


class Truncated(LLMError):
    pass


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def usd(self, price: ModelPrice) -> float:
        return (
            self.input_tokens * price.input_usd_per_mtok
            + self.output_tokens * price.output_usd_per_mtok
        ) / 1_000_000


class LLM:
    def __init__(
        self, client: anthropic.Anthropic, model: str, max_calls: int, max_tokens: int = 256
    ) -> None:
        if model not in PRICES:
            raise ValueError(f"no price configured for model {model!r}; add it to core.llm.PRICES")
        self._client = client
        self.model = model
        self.price = PRICES[model]
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.usage = Usage()

    def check_model(self) -> None:
        """Fail fast if the configured model id has been retired or mistyped."""
        self._client.models.retrieve(self.model)

    def parse[T: BaseModel](self, system: str, user: str, schema: type[T]) -> T:
        if self.usage.calls >= self.max_calls:
            raise CallLimitExceeded(f"reached max_calls={self.max_calls}")
        self.usage.calls += 1

        response = self._client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        self.usage.input_tokens += response.usage.input_tokens
        self.usage.output_tokens += response.usage.output_tokens

        if response.stop_reason == "refusal":
            raise Refused("model declined the request")
        if response.stop_reason == "max_tokens":
            raise Truncated(f"output hit max_tokens={self.max_tokens}")
        if response.parsed_output is None:
            raise LLMError("response did not contain a parsed output")
        return response.parsed_output

    @property
    def usd_spent(self) -> float:
        return self.usage.usd(self.price)
