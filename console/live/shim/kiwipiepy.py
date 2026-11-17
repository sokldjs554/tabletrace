"""Stand-in for the Korean tokenizer (kiwipiepy) inside the browser.

The real tokenizer is a compiled extension with a 109 MB model; it cannot be loaded on a static page. The verifier and
the heuristic planner ask it for the tokens of two kinds of text only: the question and the table's column headers.
For the questions and tables the demo stores, those tokens were recorded with the real tokenizer when the demo was
recorded (console/data/recorded/kiwi_tokens.json). This module hands them back, so the code that runs in the browser
sees exactly the tokens it would see on a server. A text that was not recorded cannot be tokenized here: that raises
`MissingTokens`, and the page says so instead of guessing.
"""
from __future__ import annotations

_TOKENS: dict[str, list[list[str]]] = {}


class MissingTokens(LookupError):
    """The text has no recorded tokens (a Korean question the visitor typed, or a table outside the demo)."""


class Token:
    __slots__ = ("form", "tag")

    def __init__(self, form: str, tag: str) -> None:
        self.form, self.tag = form, tag


class Kiwi:
    def tokenize(self, text: str) -> list[Token]:
        text = text or ""
        if not text.strip():
            return []
        if text not in _TOKENS:
            raise MissingTokens(text)
        return [Token(form, tag) for form, tag in _TOKENS[text]]


def load(tokens: dict[str, list[list[str]]]) -> None:
    _TOKENS.update(tokens)
