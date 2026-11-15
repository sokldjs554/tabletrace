"""A verifier call that cannot take the caller down.

`resolve` runs tools. A tool can refuse its arguments (for example an answer too long to look up), and that refusal
used to escape as an exception: one such planner output ended a whole evaluation run on the owner's GPU session, and the
service would have answered with a server error. Here the refusal becomes what it means for the user: no answer goes out.

This wrapper is not part of the owner-written verifier (`verifier.py`); it only catches what leaves it.
"""
from __future__ import annotations

from tabletrace.schema import Check, Verdict
from tabletrace.tools.registry import ToolError
from tabletrace.verify.verifier import Resolution, resolve


def resolve_guarded(question, table, program, **options) -> Resolution:
    try:
        return resolve(question, table, program, **options)
    except ToolError as exc:
        check = Check(name="tool_call", passed=False, detail=str(exc)[:300])
        return Resolution("abstained", None, [], None, Verdict(status="abstained", reason="verification_failed", checks=[check]), [])
