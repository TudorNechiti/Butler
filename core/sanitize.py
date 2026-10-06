"""Turn untrusted text (email, web pages) into plain, bounded text before it reaches a prompt.

This does not make the content safe to obey. Prompts still treat it as data. What it removes is
markup, hidden characters and unbounded length.
"""

from __future__ import annotations

import html
import re
import unicodedata
from html.parser import HTMLParser

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SPACES_RE = re.compile(r"[ \t\f\v]+")
TRUNCATION_MARKER = " [truncated]"


class _TextExtractor(HTMLParser):
    _SKIP = frozenset({"script", "style", "head", "title"})
    _BLOCK = frozenset({"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    return normalize_whitespace(html.unescape("".join(parser.parts)))


def strip_control_chars(text: str) -> str:
    """Remove control and invisible format characters (zero-width, bidi overrides).

    These can hide instructions from a human reader while the model still sees them.
    Newlines and tabs are kept.
    """
    return "".join(
        ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in {"Cc", "Cf"}
    )


def normalize_whitespace(text: str) -> str:
    lines = (_SPACES_RE.sub(" ", line).strip() for line in text.splitlines())
    return _BLANK_LINES_RE.sub("\n\n", "\n".join(lines)).strip()


def strip_urls(text: str) -> str:
    return _URL_RE.sub("[link]", text)


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - len(TRUNCATION_MARKER))] + TRUNCATION_MARKER


def clean_untrusted(text: str, max_chars: int) -> str:
    """Standard pipeline for untrusted plain text: hidden chars out, whitespace tidied, bounded."""
    return truncate(normalize_whitespace(strip_control_chars(text)), max_chars)
