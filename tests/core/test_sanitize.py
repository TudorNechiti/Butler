from core.sanitize import (
    TRUNCATION_MARKER,
    clean_untrusted,
    html_to_text,
    strip_control_chars,
    strip_urls,
    truncate,
)


def test_html_to_text_drops_markup_scripts_and_styles() -> None:
    markup = (
        "<html><head><style>p{color:red}</style></head><body>"
        "<p>Invoice due</p><script>alert(1)</script><div>Amount: &euro;40</div>"
        "</body></html>"
    )
    assert html_to_text(markup) == "Invoice due\n\nAmount: €40"


def test_strip_control_chars_removes_invisible_characters_but_keeps_newlines() -> None:
    hidden = "pay​now‮\x07\nnext\tline"
    assert strip_control_chars(hidden) == "paynow\nnext\tline"


def test_strip_urls_replaces_links() -> None:
    assert strip_urls("see https://evil.example/x?a=1 or www.foo.com now") == (
        "see [link] or [link] now"
    )


def test_truncate_respects_limit_and_marks_cut() -> None:
    result = truncate("a" * 100, 50)
    assert len(result) == 50
    assert result.endswith(TRUNCATION_MARKER)
    assert truncate("short", 50) == "short"


def test_clean_untrusted_combines_steps() -> None:
    text = "Hello​   world\n\n\n\n\nbye"
    assert clean_untrusted(text, 1000) == "Hello world\n\nbye"
