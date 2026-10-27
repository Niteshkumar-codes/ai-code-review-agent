r"""
Offline regression tests verifying that both production Gemini call sites
pass explicit HTTP timeouts in their GenerateContentConfig.

Targets verified by reading the source directly (Step 1 of the task):
  - src/review_nodes.py  -- _call_gemini() uses _REVIEW_NODE_TIMEOUT_MS = 120_000
  - src/code_reviewer.py -- review_code_diff() uses _CODE_REVIEW_TIMEOUT_MS = 120_000

Mock boundaries chosen after inspecting the installed SDK:
  - For review_nodes._call_gemini: patch "src.review_nodes.get_gemini_client"
    so that client.models.generate_content is a MagicMock. The config object
    passed to generate_content is a real types.GenerateContentConfig (constructed
    by the production code), so we can inspect its .http_options.timeout directly.
  - For code_reviewer.review_code_diff: patch "src.code_reviewer.get_gemini_client"
    using the same technique.

No real genai.Client is constructed and no network requests are made.

Run:
    .venv\Scripts\python.exe test_production_gemini_timeouts.py
"""

import os
import sys

# ---------------------------------------------------------------------------
# Sentinel env-vars -- never sent to any external service.
# Must be set BEFORE any src module that imports Config is imported.
# ---------------------------------------------------------------------------
os.environ.setdefault("GEMINI_API_KEY", "offline-test-sentinel")
os.environ.setdefault("GITHUB_TOKEN", "offline-test-sentinel")

from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import the constants we are verifying against, so the test fails clearly
# if they are renamed or removed.
from src.review_nodes import _REVIEW_NODE_TIMEOUT_MS, _call_gemini
from src.code_reviewer import _CODE_REVIEW_TIMEOUT_MS, review_code_diff
import src.config as cfg_mod

# ---------------------------------------------------------------------------
# Helpers (same style as all other offline test suites in this repository)
# ---------------------------------------------------------------------------

failures: list[str] = []


def ok(description: str) -> None:
    print(f"  [OK  ] {description}")


def fail(description: str) -> None:
    print(f"  [FAIL] {description}")
    failures.append(description)


def _make_mock_client(response_text: str) -> MagicMock:
    """Return a mock genai.Client whose models.generate_content returns
    a response with the given .text attribute. No real client is created."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_client.models.generate_content.return_value = mock_response
    return mock_client


# Patch targets (both point at the function used inside each module's
# namespace, not at the underlying genai.Client class).
_PATCH_REVIEW_NODES_CLIENT = "src.review_nodes.get_gemini_client"
_PATCH_CODE_REVIEWER_CLIENT = "src.code_reviewer.get_gemini_client"

# Minimum diff content for review_code_diff (it guards against empty diffs).
_VALID_DIFF = "+x = 1"

# ---------------------------------------------------------------------------
print("=" * 64)
print(" PRODUCTION GEMINI TIMEOUT REGRESSION TESTS (offline)")
print("=" * 64)
# ---------------------------------------------------------------------------


# ===========================================================================
# Section 1: _REVIEW_NODE_TIMEOUT_MS constant value
#
# Source (src/review_nodes.py):
#   _REVIEW_NODE_TIMEOUT_MS: int = 120_000
# ===========================================================================
print()
print("=== 1. _REVIEW_NODE_TIMEOUT_MS constant value ===")

_EXPECTED_REVIEW_NODE_TIMEOUT_MS = 120_000

if _REVIEW_NODE_TIMEOUT_MS == _EXPECTED_REVIEW_NODE_TIMEOUT_MS:
    ok(
        f"_REVIEW_NODE_TIMEOUT_MS == {_EXPECTED_REVIEW_NODE_TIMEOUT_MS}"
        " (120 seconds expressed in ms)"
    )
else:
    fail(
        f"_REVIEW_NODE_TIMEOUT_MS is {_REVIEW_NODE_TIMEOUT_MS!r},"
        f" expected {_EXPECTED_REVIEW_NODE_TIMEOUT_MS!r}"
    )

if isinstance(_REVIEW_NODE_TIMEOUT_MS, int):
    ok("_REVIEW_NODE_TIMEOUT_MS is of type int")
else:
    fail(
        f"_REVIEW_NODE_TIMEOUT_MS is"
        f" {type(_REVIEW_NODE_TIMEOUT_MS).__name__!r}, expected int"
    )


# ===========================================================================
# Section 2: _CODE_REVIEW_TIMEOUT_MS constant value
#
# Source (src/code_reviewer.py):
#   _CODE_REVIEW_TIMEOUT_MS: int = 120_000
# ===========================================================================
print()
print("=== 2. _CODE_REVIEW_TIMEOUT_MS constant value ===")

_EXPECTED_CODE_REVIEW_TIMEOUT_MS = 120_000

if _CODE_REVIEW_TIMEOUT_MS == _EXPECTED_CODE_REVIEW_TIMEOUT_MS:
    ok(
        f"_CODE_REVIEW_TIMEOUT_MS == {_EXPECTED_CODE_REVIEW_TIMEOUT_MS}"
        " (120 seconds expressed in ms)"
    )
else:
    fail(
        f"_CODE_REVIEW_TIMEOUT_MS is {_CODE_REVIEW_TIMEOUT_MS!r},"
        f" expected {_EXPECTED_CODE_REVIEW_TIMEOUT_MS!r}"
    )

if isinstance(_CODE_REVIEW_TIMEOUT_MS, int):
    ok("_CODE_REVIEW_TIMEOUT_MS is of type int")
else:
    fail(
        f"_CODE_REVIEW_TIMEOUT_MS is"
        f" {type(_CODE_REVIEW_TIMEOUT_MS).__name__!r}, expected int"
    )


# ===========================================================================
# Section 3: _call_gemini() passes http_options.timeout == 120_000
#
# The config arg received by generate_content is a real GenerateContentConfig
# (produced by production code); we inspect its .http_options.timeout directly.
# ===========================================================================
print()
print("=== 3. _call_gemini() passes HttpOptions(timeout=120_000) ===")

with patch(_PATCH_REVIEW_NODES_CLIENT) as mock_get_client:
    mock_client = _make_mock_client("review node response")
    mock_get_client.return_value = mock_client

    try:
        _call_gemini(
            system_instruction="sys instr sentinel",
            prompt="prompt sentinel",
            model_name="gemini-test-model",
        )
    except Exception as exc:
        fail(f"_call_gemini() raised unexpectedly: {exc!r}")

call_args = mock_client.models.generate_content.call_args
if call_args is None:
    fail("generate_content was never called by _call_gemini()")
else:
    config_arg = call_args.kwargs.get("config") or (
        call_args.args[2] if len(call_args.args) > 2 else None
    )
    if config_arg is None:
        fail("No 'config' argument found in _call_gemini -> generate_content call")
    else:
        http_opts = getattr(config_arg, "http_options", None)
        if http_opts is None:
            fail(
                "_call_gemini config has no 'http_options' attribute"
            )
        else:
            timeout_val = getattr(http_opts, "timeout", None)
            if timeout_val == _REVIEW_NODE_TIMEOUT_MS:
                ok(
                    f"_call_gemini http_options.timeout == {_REVIEW_NODE_TIMEOUT_MS}"
                    " (== _REVIEW_NODE_TIMEOUT_MS)"
                )
            else:
                fail(
                    f"_call_gemini http_options.timeout is {timeout_val!r},"
                    f" expected {_REVIEW_NODE_TIMEOUT_MS!r}"
                )


# ===========================================================================
# Section 4: _call_gemini() preserves existing model and prompt arguments
#
# Verify that adding http_options did not drop the model= or contents= args
# that were already being passed to generate_content.
# ===========================================================================
print()
print("=== 4. _call_gemini() preserves model and prompt (contents) arguments ===")

_SENTINEL_MODEL = "gemini-sentinel-model-review-nodes"
_SENTINEL_PROMPT = "sentinel prompt for review nodes timeout test"

with patch(_PATCH_REVIEW_NODES_CLIENT) as mock_get_client:
    mock_client = _make_mock_client("ok response")
    mock_get_client.return_value = mock_client

    try:
        _call_gemini(
            system_instruction="sys",
            prompt=_SENTINEL_PROMPT,
            model_name=_SENTINEL_MODEL,
        )
    except Exception as exc:
        fail(f"_call_gemini() raised unexpectedly: {exc!r}")

gc_call = mock_client.models.generate_content.call_args
if gc_call is None:
    fail("generate_content was not called (section 4)")
else:
    passed_model = gc_call.kwargs.get("model") or (
        gc_call.args[0] if gc_call.args else None
    )
    passed_contents = gc_call.kwargs.get("contents") or (
        gc_call.args[1] if len(gc_call.args) > 1 else None
    )

    if passed_model == _SENTINEL_MODEL:
        ok(f"_call_gemini forwards model_name='{_SENTINEL_MODEL}' as model kwarg")
    else:
        fail(
            f"_call_gemini model kwarg is {passed_model!r},"
            f" expected {_SENTINEL_MODEL!r}"
        )

    if passed_contents == _SENTINEL_PROMPT:
        ok(f"_call_gemini forwards prompt as contents kwarg ('{_SENTINEL_PROMPT}')")
    else:
        fail(
            f"_call_gemini contents kwarg is {passed_contents!r},"
            f" expected {_SENTINEL_PROMPT!r}"
        )


# ===========================================================================
# Section 5: review_code_diff() passes http_options.timeout == 120_000
# ===========================================================================
print()
print("=== 5. review_code_diff() passes HttpOptions(timeout=120_000) ===")

with patch(_PATCH_CODE_REVIEWER_CLIENT) as mock_get_client:
    mock_client = _make_mock_client("code review response")
    mock_get_client.return_value = mock_client

    try:
        review_code_diff(_VALID_DIFF)
    except Exception as exc:
        fail(f"review_code_diff() raised unexpectedly: {exc!r}")

call_args = mock_client.models.generate_content.call_args
if call_args is None:
    fail("generate_content was never called by review_code_diff()")
else:
    config_arg = call_args.kwargs.get("config") or (
        call_args.args[2] if len(call_args.args) > 2 else None
    )
    if config_arg is None:
        fail(
            "No 'config' argument found in review_code_diff -> generate_content call"
        )
    else:
        http_opts = getattr(config_arg, "http_options", None)
        if http_opts is None:
            fail(
                "review_code_diff config has no 'http_options' attribute"
            )
        else:
            timeout_val = getattr(http_opts, "timeout", None)
            if timeout_val == _CODE_REVIEW_TIMEOUT_MS:
                ok(
                    f"review_code_diff http_options.timeout == {_CODE_REVIEW_TIMEOUT_MS}"
                    " (== _CODE_REVIEW_TIMEOUT_MS)"
                )
            else:
                fail(
                    f"review_code_diff http_options.timeout is {timeout_val!r},"
                    f" expected {_CODE_REVIEW_TIMEOUT_MS!r}"
                )


# ===========================================================================
# Section 6: review_code_diff() preserves model and contents arguments
# ===========================================================================
print()
print("=== 6. review_code_diff() preserves model and contents arguments ===")

_SENTINEL_DIFF = "+sentinel = 'code reviewer timeout test'"
_SENTINEL_MODEL_CR = "gemini-sentinel-model-code-reviewer"

with patch(_PATCH_CODE_REVIEWER_CLIENT) as mock_get_client:
    mock_client = _make_mock_client("ok review")
    mock_get_client.return_value = mock_client

    try:
        review_code_diff(_SENTINEL_DIFF, model_name=_SENTINEL_MODEL_CR)
    except Exception as exc:
        fail(f"review_code_diff() raised unexpectedly: {exc!r}")

gc_call = mock_client.models.generate_content.call_args
if gc_call is None:
    fail("generate_content was not called (section 6)")
else:
    passed_model = gc_call.kwargs.get("model") or (
        gc_call.args[0] if gc_call.args else None
    )
    passed_contents = gc_call.kwargs.get("contents") or (
        gc_call.args[1] if len(gc_call.args) > 1 else None
    )

    if passed_model == _SENTINEL_MODEL_CR:
        ok(
            f"review_code_diff forwards model_name='{_SENTINEL_MODEL_CR}'"
            " as model kwarg"
        )
    else:
        fail(
            f"review_code_diff model kwarg is {passed_model!r},"
            f" expected {_SENTINEL_MODEL_CR!r}"
        )

    # The diff is embedded inside a ```diff ... ``` block by production code.
    expected_diff_block = f"Diff:\n```diff\n{_SENTINEL_DIFF.strip()}\n```"
    if passed_contents is not None and expected_diff_block in passed_contents:
        ok(
            "review_code_diff diff content embedded as diff block in contents kwarg"
        )
    else:
        fail(
            f"review_code_diff contents kwarg does not contain expected diff block;"
            f" got: {passed_contents!r}"
        )


# ===========================================================================
# Section 7: Both timeout values are equal to each other (both 120_000)
# ===========================================================================
print()
print("=== 7. Both timeout constants equal 120_000 ===")

if _REVIEW_NODE_TIMEOUT_MS == _CODE_REVIEW_TIMEOUT_MS == 120_000:
    ok(
        "_REVIEW_NODE_TIMEOUT_MS == _CODE_REVIEW_TIMEOUT_MS == 120_000"
        " (both sites use 120 s)"
    )
else:
    fail(
        f"Timeout mismatch: _REVIEW_NODE_TIMEOUT_MS={_REVIEW_NODE_TIMEOUT_MS!r},"
        f" _CODE_REVIEW_TIMEOUT_MS={_CODE_REVIEW_TIMEOUT_MS!r};"
        " both should be 120_000"
    )


# ===========================================================================
# Section 8: get_gemini_client is NOT called with live credentials
#            (confirms no real network request occurs in these tests)
# ===========================================================================
print()
print("=== 8. No real genai.Client constructed (mock boundary check) ===")

# Both sections 3 and 5 above used patched get_gemini_client.
# Repeat once more explicitly to document the guarantee.
with patch(_PATCH_REVIEW_NODES_CLIENT) as mock_get_rn, \
     patch(_PATCH_CODE_REVIEWER_CLIENT) as mock_get_cr:

    mock_client_rn = _make_mock_client("rn response")
    mock_client_cr = _make_mock_client("cr response")
    mock_get_rn.return_value = mock_client_rn
    mock_get_cr.return_value = mock_client_cr

    try:
        _call_gemini("sys", "prompt", model_name="gemini-test-model")
    except Exception:
        pass

    try:
        review_code_diff("+dummy = 1")
    except Exception:
        pass

    if mock_get_rn.called:
        ok(
            "src.review_nodes.get_gemini_client is patched -- no real"
            " genai.Client constructed"
        )
    else:
        fail(
            "src.review_nodes.get_gemini_client mock was never called"
            " -- unexpected code path"
        )

    if mock_get_cr.called:
        ok(
            "src.code_reviewer.get_gemini_client is patched -- no real"
            " genai.Client constructed"
        )
    else:
        fail(
            "src.code_reviewer.get_gemini_client mock was never called"
            " -- unexpected code path"
        )


# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------

print()
if failures:
    print("=" * 64)
    print(f"FAILED -- {len(failures)} assertion(s) failed:")
    for i, msg in enumerate(failures, 1):
        print(f"  {i}. {msg}")
    print("=" * 64)
    sys.exit(1)
else:
    print("=" * 64)
    print("All production-timeout regression tests passed.")
    print("=" * 64)
    sys.exit(0)
