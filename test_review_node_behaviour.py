r"""
Offline review-node behaviour tests for src/review_nodes.py
and src/code_reviewer.py.

Tests only behaviour that is directly observable from the current
implementation without making any Gemini or GitHub API calls.
_call_gemini is patched wherever a node function would invoke it.

Run:
    .venv\Scripts\python.exe test_review_node_behaviour.py
"""
import os
import sys

# ---------------------------------------------------------------------------
# Sentinel env-vars -- never sent to any external service.
# Must be set BEFORE importing any src module that imports Config.
# ---------------------------------------------------------------------------
os.environ.setdefault("GEMINI_API_KEY", "offline-test-sentinel")
os.environ.setdefault("GITHUB_TOKEN", "offline-test-sentinel")

from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import src.review_nodes as rn
from src.agent_state import AgentState
from src.code_reviewer import review_code_diff
from src.gemini_client import get_gemini_client
import src.config as cfg_mod

# ---------------------------------------------------------------------------
# Test helpers  (same style as test_retry_predicate.py)
# ---------------------------------------------------------------------------

failures: list[str] = []


def ok(description: str) -> None:
    print(f"  [OK  ] {description}")


def fail(description: str) -> None:
    print(f"  [FAIL] {description}")
    failures.append(description)


def _make_state(
    diff: str = "+x = 1",
    context: str | None = None,
    change_analysis: str | None = None,
    security_review: str | None = None,
    error_handling_review: str | None = None,
    quality_review: str | None = None,
    final_review: str | None = None,
) -> AgentState:
    """Convenience factory for AgentState dicts."""
    return {
        "diff": diff,
        "context": context,
        "change_analysis": change_analysis,
        "security_review": security_review,
        "error_handling_review": error_handling_review,
        "quality_review": quality_review,
        "final_review": final_review,
    }


_MOCK_PATCH = "src.review_nodes._call_gemini"

# ---------------------------------------------------------------------------
print("=" * 60)
print(" REVIEW NODE BEHAVIOUR TESTS (offline)")
print("=" * 60)
# ---------------------------------------------------------------------------


# ===========================================================================
# Section 1: Each node returns the correct single-key dict
# ===========================================================================
print()
print("=== 1. Node return-key contract ===")

_NODE_RETURN_KEYS: list[tuple] = [
    (rn.analyze_changes,       "change_analysis"),
    (rn.review_security,       "security_review"),
    (rn.review_error_handling, "error_handling_review"),
    (rn.review_code_quality,   "quality_review"),
    (rn.generate_final_review, "final_review"),
]

state = _make_state(
    diff="+x = 1",
    context="ctx",
    change_analysis="prior analysis",
    security_review="sec",
    error_handling_review="err",
    quality_review="qual",
)

for fn, expected_key in _NODE_RETURN_KEYS:
    with patch(_MOCK_PATCH, return_value="mocked output"):
        result = fn(state)
    # Must return exactly one key
    if list(result.keys()) == [expected_key]:
        ok(f"{fn.__name__}() returns dict with key '{expected_key}'")
    else:
        fail(
            f"{fn.__name__}() returned keys {list(result.keys())!r},"
            f" expected ['{expected_key}']"
        )
    # Value must be the mocked return value
    if result[expected_key] == "mocked output":
        ok(f"{fn.__name__}() value equals _call_gemini return value")
    else:
        fail(
            f"{fn.__name__}() value = {result[expected_key]!r},"
            f" expected 'mocked output'"
        )


# ===========================================================================
# Section 2: Each node calls _call_gemini exactly once
# ===========================================================================
print()
print("=== 2. Each node calls _call_gemini exactly once ===")

_ALL_NODE_FNS = [fn for fn, _ in _NODE_RETURN_KEYS]

for fn in _ALL_NODE_FNS:
    with patch(_MOCK_PATCH, return_value="x") as mock:
        fn(state)
    if mock.call_count == 1:
        ok(f"{fn.__name__}() calls _call_gemini exactly once")
    else:
        fail(
            f"{fn.__name__}() called _call_gemini {mock.call_count} times,"
            f" expected 1"
        )


# ===========================================================================
# Section 3: RuntimeError from _call_gemini propagates unchanged
# ===========================================================================
print()
print("=== 3. RuntimeError from _call_gemini propagates out of each node ===")

for fn in _ALL_NODE_FNS:
    with patch(_MOCK_PATCH, side_effect=RuntimeError("simulated API failure")):
        try:
            fn(state)
            fail(f"{fn.__name__}() swallowed RuntimeError -- expected propagation")
        except RuntimeError as exc:
            if str(exc) == "simulated API failure":
                ok(f"{fn.__name__}() propagates RuntimeError unchanged")
            else:
                fail(
                    f"{fn.__name__}() re-raised RuntimeError with wrong message:"
                    f" {exc!r}"
                )
        except Exception as exc:
            fail(
                f"{fn.__name__}() raised {type(exc).__name__} instead of"
                f" RuntimeError: {exc!r}"
            )


# ===========================================================================
# Section 4: Prompt assembly -- context included vs. omitted
#
# Implementation detail (src/review_nodes.py):
#   All four analysis nodes use:  `if context:` (falsy check on str/None)
#   This means:
#     - None and "" are omitted from the prompt.
#     - Whitespace-only strings ("   ") ARE included (truthy).
# ===========================================================================
print()
print("=== 4. Context inclusion in prompt (analyze_changes) ===")

# 4a. With a real context string -- prompt must contain "Context:\n<value>"
with patch(_MOCK_PATCH, return_value="x") as mock:
    rn.analyze_changes(_make_state(diff="+a=1", context="my context"))
    _, prompt = mock.call_args[0][:2]

if "Context:\nmy context" in prompt:
    ok("Context string included in prompt as 'Context:\\n<value>'")
else:
    fail(f"Context string missing from prompt; prompt was: {prompt!r}")

if "Diff:\n```diff\n+a=1\n```" in prompt:
    ok("Diff block present in prompt when context is supplied")
else:
    fail(f"Diff block missing from prompt; prompt was: {prompt!r}")

# 4b. With context=None -- prompt must NOT contain "Context:"
with patch(_MOCK_PATCH, return_value="x") as mock:
    rn.analyze_changes(_make_state(diff="+a=1", context=None))
    _, prompt_none = mock.call_args[0][:2]

if "Context:" not in prompt_none:
    ok("context=None omitted from prompt ('Context:' not present)")
else:
    fail(f"context=None incorrectly included 'Context:' in prompt: {prompt_none!r}")

if "Diff:\n```diff\n+a=1\n```" in prompt_none:
    ok("Diff block present in prompt when context is None")
else:
    fail(f"Diff block missing from prompt when context=None: {prompt_none!r}")

# 4c. With context="" (empty string) -- same as None: must NOT appear
with patch(_MOCK_PATCH, return_value="x") as mock:
    rn.analyze_changes(_make_state(diff="+a=1", context=""))
    _, prompt_empty = mock.call_args[0][:2]

if "Context:" not in prompt_empty:
    ok("context='' omitted from prompt ('Context:' not present)")
else:
    fail(f"context='' incorrectly included 'Context:' in prompt: {prompt_empty!r}")

# 4d. Whitespace-only context IS truthy and IS included in the prompt
#     (actual behaviour of `if context:` with "   ").
with patch(_MOCK_PATCH, return_value="x") as mock:
    rn.analyze_changes(_make_state(diff="+a=1", context="   "))
    _, prompt_ws = mock.call_args[0][:2]

if "Context:" in prompt_ws:
    ok("context='   ' (whitespace-only) is included in prompt (truthy in Python)")
else:
    fail(
        "context='   ' was unexpectedly omitted from prompt"
        f"; prompt was: {prompt_ws!r}"
    )


# ===========================================================================
# Section 5: Prior-analysis inclusion in review_security prompt
#
# review_security uses: `if analysis:` to gate change_analysis into the prompt.
# ===========================================================================
print()
print("=== 5. Prior analysis inclusion in review_security prompt ===")

# 5a. With change_analysis present
with patch(_MOCK_PATCH, return_value="x") as mock:
    rn.review_security(_make_state(
        diff="+secret='abc'",
        context="ctx",
        change_analysis="some analysis",
    ))
    _, prompt_with_analysis = mock.call_args[0][:2]

if "Change Analysis Summary:\nsome analysis" in prompt_with_analysis:
    ok("review_security includes change_analysis under 'Change Analysis Summary:'")
else:
    fail(
        "review_security missing change_analysis in prompt;"
        f" prompt: {prompt_with_analysis!r}"
    )

if "Diff:\n```diff" in prompt_with_analysis:
    ok("review_security diff block present alongside analysis")
else:
    fail(f"review_security diff block missing; prompt: {prompt_with_analysis!r}")

# 5b. With change_analysis=None -- label must be absent
with patch(_MOCK_PATCH, return_value="x") as mock:
    rn.review_security(_make_state(diff="+secret='abc'", change_analysis=None))
    _, prompt_no_analysis = mock.call_args[0][:2]

if "Change Analysis Summary:" not in prompt_no_analysis:
    ok("review_security omits 'Change Analysis Summary:' when change_analysis=None")
else:
    fail(
        "review_security incorrectly included 'Change Analysis Summary:' when None;"
        f" prompt: {prompt_no_analysis!r}"
    )


# ===========================================================================
# Section 6: generate_final_review prompt assembles all four prior reviews
#
# generate_final_review uses:
#   `if context:`                 -- optional
#   always appends Change Analysis, Security Review, Error Handling, Code Quality
# ===========================================================================
print()
print("=== 6. generate_final_review prompt structure ===")

_FINAL_STATE = _make_state(
    diff="+pass",
    context="release context",
    change_analysis="analysis text",
    security_review="security text",
    error_handling_review="error handling text",
    quality_review="quality text",
)

with patch(_MOCK_PATCH, return_value="x") as mock:
    rn.generate_final_review(_FINAL_STATE)
    _, final_prompt = mock.call_args[0][:2]

for label, substring in [
    ("Context",              "Context:\nrelease context"),
    ("Change Analysis",      "Change Analysis:\nanalysis text"),
    ("Security Review",      "Security Review:\nsecurity text"),
    ("Error Handling Review","Error Handling Review:\nerror handling text"),
    ("Code Quality Review",  "Code Quality Review:\nquality text"),
]:
    if substring in final_prompt:
        ok(f"generate_final_review prompt contains '{label}' section")
    else:
        fail(
            f"generate_final_review prompt missing '{label}' section;"
            f" prompt: {final_prompt!r}"
        )

# 6b. generate_final_review does NOT include a raw diff block
if "```diff" not in final_prompt:
    ok("generate_final_review prompt does not contain a raw diff block")
else:
    fail(
        "generate_final_review unexpectedly includes a raw '```diff' block"
        f"; prompt: {final_prompt!r}"
    )


# ===========================================================================
# Section 7: review_error_handling and review_code_quality include analysis
# ===========================================================================
print()
print("=== 7. review_error_handling and review_code_quality include change_analysis ===")

for fn, label in [
    (rn.review_error_handling, "review_error_handling"),
    (rn.review_code_quality,   "review_code_quality"),
]:
    # With analysis
    with patch(_MOCK_PATCH, return_value="x") as mock:
        fn(_make_state(diff="+x=1", change_analysis="detailed analysis"))
        _, p = mock.call_args[0][:2]
    if "Change Analysis Summary:\ndetailed analysis" in p:
        ok(f"{label} includes change_analysis in prompt")
    else:
        fail(f"{label} missing change_analysis in prompt; prompt: {p!r}")

    # Without analysis
    with patch(_MOCK_PATCH, return_value="x") as mock:
        fn(_make_state(diff="+x=1", change_analysis=None))
        _, p_none = mock.call_args[0][:2]
    if "Change Analysis Summary:" not in p_none:
        ok(f"{label} omits 'Change Analysis Summary:' when change_analysis=None")
    else:
        fail(
            f"{label} incorrectly includes 'Change Analysis Summary:' when None;"
            f" prompt: {p_none!r}"
        )


# ===========================================================================
# Section 8: code_reviewer.review_code_diff -- empty / whitespace-only diff guard
#
# review_code_diff() has an explicit guard:
#   if not diff or not diff.strip():
#       raise ValueError("Code diff cannot be empty or contain only whitespace.")
# ===========================================================================
print()
print("=== 8. code_reviewer.review_code_diff empty-diff guard ===")

_EXPECTED_VALUEERROR_MSG = "Code diff cannot be empty or contain only whitespace."

for bad_diff, label in [
    ("",       "empty string"),
    ("   ",    "spaces-only"),
    ("\n\t\n", "newlines and tabs only"),
]:
    try:
        review_code_diff(bad_diff)
        fail(f"review_code_diff({label!r}) did not raise ValueError")
    except ValueError as exc:
        if str(exc) == _EXPECTED_VALUEERROR_MSG:
            ok(f"review_code_diff({label!r}) raises ValueError with correct message")
        else:
            fail(
                f"review_code_diff({label!r}) raised ValueError but wrong message:"
                f" {exc!r}"
            )
    except Exception as exc:
        fail(
            f"review_code_diff({label!r}) raised {type(exc).__name__} instead of"
            f" ValueError: {exc!r}"
        )

# A non-empty diff must NOT raise before the API call
with patch("src.code_reviewer.get_gemini_client") as mock_client:
    mock_response = MagicMock()
    mock_response.text = "review output"
    mock_client.return_value.models.generate_content.return_value = mock_response
    try:
        result = review_code_diff("+x = 1")
        if result == "review output":
            ok("review_code_diff(valid diff) returns the API response text")
        else:
            fail(f"review_code_diff returned unexpected value: {result!r}")
    except Exception as exc:
        fail(f"review_code_diff(valid diff) unexpectedly raised: {exc!r}")


# ===========================================================================
# Section 9: get_gemini_client raises ValueError for a missing API key
#
# Implementation: if not Config.GEMINI_API_KEY: raise ValueError(...)
# ===========================================================================
print()
print("=== 9. get_gemini_client raises ValueError when API key is empty ===")

_original_key = cfg_mod.Config.GEMINI_API_KEY
try:
    cfg_mod.Config.GEMINI_API_KEY = ""
    try:
        get_gemini_client()
        fail("get_gemini_client() did not raise ValueError for empty API key")
    except ValueError as exc:
        if "GEMINI_API_KEY" in str(exc):
            ok(
                "get_gemini_client() raises ValueError mentioning 'GEMINI_API_KEY'"
                f" when key is empty: {exc!r}"
            )
        else:
            fail(
                f"get_gemini_client() raised ValueError but message lacks"
                f" 'GEMINI_API_KEY': {exc!r}"
            )
    except Exception as exc:
        fail(
            f"get_gemini_client() raised {type(exc).__name__} instead of"
            f" ValueError: {exc!r}"
        )
finally:
    cfg_mod.Config.GEMINI_API_KEY = _original_key  # always restore


# ===========================================================================
# Section 10: Diff is always embedded in the prompt for analysis nodes
#
# Even when diff is an empty string after `state.get("diff") or ""`, the
# node still calls _call_gemini (no guard) and embeds the diff in a
# ```diff ... ``` block.
# ===========================================================================
print()
print("=== 10. Diff is always embedded in analysis-node prompts ===")

_ANALYSIS_NODES = [
    (rn.analyze_changes,       "analyze_changes"),
    (rn.review_security,       "review_security"),
    (rn.review_error_handling, "review_error_handling"),
    (rn.review_code_quality,   "review_code_quality"),
]

for fn, name in _ANALYSIS_NODES:
    for diff_val, diff_label in [
        ("+real change", "real diff"),
        ("",             "empty diff"),
    ]:
        with patch(_MOCK_PATCH, return_value="x") as mock:
            fn(_make_state(diff=diff_val))
            _, p = mock.call_args[0][:2]
        if "Diff:\n```diff\n" in p:
            ok(f"{name} embeds diff block in prompt ({diff_label})")
        else:
            fail(
                f"{name} missing diff block in prompt ({diff_label});"
                f" prompt: {p!r}"
            )


# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------

print()
if failures:
    print("=" * 60)
    print(f"FAILED -- {len(failures)} assertion(s) failed:")
    for i, msg in enumerate(failures, 1):
        print(f"  {i}. {msg}")
    print("=" * 60)
    sys.exit(1)
else:
    print("=" * 60)
    print("All review-node behaviour tests passed.")
    print("=" * 60)
    sys.exit(0)
