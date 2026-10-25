r"""
Focused offline regression tests for src/code_reviewer.py edge cases.

Covers:
  1. context=None, empty string, and whitespace-only context behaviour.
  2. Existing APIError wrapping behaviour.
  3. Existing generic Exception wrapping behaviour.
  4. Empty response text behaviour.

No Gemini or GitHub API calls are made.  get_gemini_client and
client.models.generate_content are patched for every test that
reaches the API call path.

Run:
    .venv\Scripts\python.exe test_code_reviewer_edge_cases.py
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
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from google.genai.errors import APIError
from src.code_reviewer import review_code_diff

# ---------------------------------------------------------------------------
# Test helpers  (same style as the other offline test suites)
# ---------------------------------------------------------------------------

failures: list[str] = []


def ok(description: str) -> None:
    print(f"  [OK  ] {description}")


def fail(description: str) -> None:
    print(f"  [FAIL] {description}")
    failures.append(description)


# Patch target: get_gemini_client lives in src.code_reviewer's namespace.
_PATCH_TARGET = "src.code_reviewer.get_gemini_client"

# A minimal valid diff used throughout.
_VALID_DIFF = "+x = 1"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_client(response_text: str | None) -> MagicMock:
    """Return a mock client whose generate_content returns a response with
    the given text attribute.  Pass None to simulate response.text == None."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_client.models.generate_content.return_value = mock_response
    return mock_client


def _make_api_error(http_code: int, message: str = "quota exceeded") -> APIError:
    """Construct a real SDK APIError instance without hitting the network."""
    from google.genai import errors as sdk_errors
    response_json = {
        "error": {
            "message": message,
            "status": "TEST_STATUS",
            "code": http_code,
        }
    }
    if 400 <= http_code < 500:
        return sdk_errors.ClientError(http_code, response_json)
    elif 500 <= http_code < 600:
        return sdk_errors.ServerError(http_code, response_json)
    else:
        return sdk_errors.APIError(http_code, response_json)


# ===========================================================================
print("=" * 60)
print(" CODE REVIEWER EDGE CASE TESTS (offline)")
print("=" * 60)
# ===========================================================================


# ===========================================================================
# Section 1: context parameter behaviour
#
# Implementation (src/code_reviewer.py line 34):
#   if context and context.strip():
#       prompt_parts.append(f"Context:\n{context.strip()}")
#
# Meaning:
#   - context=None  => falsy => omitted from prompt
#   - context=""    => falsy => omitted from prompt
#   - context="   " => truthy BUT context.strip()=="" => falsy => omitted
#   - context="real"=> truthy AND context.strip()!="" => included
# ===========================================================================
print()
print("=== 1. context parameter -- prompt assembly ===")

for ctx_value, ctx_label, should_include in [
    (None,  "None",           False),
    ("",    "empty string",   False),
    ("   ", "whitespace-only",False),
]:
    with patch(_PATCH_TARGET, return_value=_make_mock_client("review result")) as _:
        try:
            result = review_code_diff(_VALID_DIFF, context=ctx_value)
            # The function succeeded -- now verify what was passed to generate_content
        except Exception as exc:
            fail(f"review_code_diff with context={ctx_label!r} raised unexpectedly: {exc!r}")
            continue

    # To inspect the prompt we need to capture the call args
    with patch(_PATCH_TARGET) as mock_get_client:
        mock_client = _make_mock_client("review result")
        mock_get_client.return_value = mock_client
        try:
            review_code_diff(_VALID_DIFF, context=ctx_value)
        except Exception:
            pass

    call_kwargs = mock_client.models.generate_content.call_args
    if call_kwargs is None:
        fail(f"context={ctx_label!r}: generate_content was never called")
        continue

    # 'contents' is passed as a keyword argument
    contents = call_kwargs.kwargs.get("contents") or (
        call_kwargs.args[1] if len(call_kwargs.args) > 1 else None
    )
    if contents is None:
        fail(f"context={ctx_label!r}: could not retrieve 'contents' argument")
        continue

    has_context_label = "Context:" in contents
    if not should_include and not has_context_label:
        ok(f"context={ctx_label!r} omitted from prompt ('Context:' absent)")
    elif not should_include and has_context_label:
        fail(f"context={ctx_label!r} unexpectedly included 'Context:' in prompt")
    elif should_include and has_context_label:
        ok(f"context={ctx_label!r} included in prompt ('Context:' present)")
    else:
        fail(f"context={ctx_label!r} missing 'Context:' from prompt")

# With a real context string -- should be included
with patch(_PATCH_TARGET) as mock_get_client:
    mock_client = _make_mock_client("review result")
    mock_get_client.return_value = mock_client
    try:
        review_code_diff(_VALID_DIFF, context="PR #42: fix login bug")
    except Exception:
        pass

call_kwargs = mock_client.models.generate_content.call_args
if call_kwargs is not None:
    contents = call_kwargs.kwargs.get("contents") or (
        call_kwargs.args[1] if len(call_kwargs.args) > 1 else None
    )
    if contents and "Context:\nPR #42: fix login bug" in contents:
        ok("context='PR #42: fix login bug' embedded verbatim under 'Context:\\n' label")
    else:
        fail(
            f"context='PR #42: fix login bug' not found in prompt; contents={contents!r}"
        )
else:
    fail("context='real string': generate_content was never called")

# Diff must always be embedded in the prompt regardless of context
with patch(_PATCH_TARGET) as mock_get_client:
    mock_client = _make_mock_client("review result")
    mock_get_client.return_value = mock_client
    try:
        review_code_diff(_VALID_DIFF, context=None)
    except Exception:
        pass

call_kwargs = mock_client.models.generate_content.call_args
if call_kwargs is not None:
    contents = call_kwargs.kwargs.get("contents") or (
        call_kwargs.args[1] if len(call_kwargs.args) > 1 else None
    )
    expected_diff_block = f"Diff:\n```diff\n{_VALID_DIFF.strip()}\n```"
    if contents and expected_diff_block in contents:
        ok("Diff block embedded in prompt even when context=None")
    else:
        fail(
            f"Diff block missing from prompt when context=None; contents={contents!r}"
        )
else:
    fail("context=None: generate_content was never called")


# ===========================================================================
# Section 2: APIError wrapping
#
# Implementation (src/code_reviewer.py lines 50-51):
#   except APIError as err:
#       raise RuntimeError(f"Gemini API error during code review: {err.message}") from err
# ===========================================================================
print()
print("=== 2. APIError wrapping ===")

for http_code, description in [
    (429, "ClientError 429 (quota)"),
    (503, "ServerError 503 (overloaded)"),
    (500, "ServerError 500 (internal)"),
]:
    api_err = _make_api_error(http_code, message="test error message")

    with patch(_PATCH_TARGET) as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = api_err
        mock_get_client.return_value = mock_client
        try:
            review_code_diff(_VALID_DIFF)
            fail(f"{description}: review_code_diff did not raise -- expected RuntimeError")
        except RuntimeError as exc:
            expected_msg = f"Gemini API error during code review: {api_err.message}"
            if str(exc) == expected_msg:
                ok(
                    f"{description}: wrapped as RuntimeError with correct message"
                )
            else:
                fail(
                    f"{description}: RuntimeError message mismatch;"
                    f" got {str(exc)!r}, expected {expected_msg!r}"
                )
            # Verify __cause__ chain is preserved
            if exc.__cause__ is api_err:
                ok(f"{description}: RuntimeError.__cause__ is the original APIError")
            else:
                fail(
                    f"{description}: RuntimeError.__cause__ is"
                    f" {type(exc.__cause__).__name__!r},"
                    f" expected the original APIError instance"
                )
        except Exception as exc:
            fail(
                f"{description}: raised {type(exc).__name__} instead of RuntimeError:"
                f" {exc!r}"
            )


# ===========================================================================
# Section 3: Generic Exception wrapping
#
# Implementation (src/code_reviewer.py lines 52-53):
#   except Exception as err:
#       raise RuntimeError(f"Unexpected error calling Gemini API: {err}") from err
# ===========================================================================
print()
print("=== 3. Generic Exception wrapping ===")

for exc_factory, exc_label in [
    (lambda: ConnectionError("network unreachable"),  "ConnectionError"),
    (lambda: TimeoutError("request timed out"),        "TimeoutError"),
    (lambda: OSError("socket error"),                  "OSError"),
]:
    original_exc = exc_factory()

    with patch(_PATCH_TARGET) as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = original_exc
        mock_get_client.return_value = mock_client
        try:
            review_code_diff(_VALID_DIFF)
            fail(
                f"{exc_label}: review_code_diff did not raise -- expected RuntimeError"
            )
        except RuntimeError as exc:
            expected_msg = f"Unexpected error calling Gemini API: {original_exc}"
            if str(exc) == expected_msg:
                ok(
                    f"{exc_label}: wrapped as RuntimeError with correct message"
                )
            else:
                fail(
                    f"{exc_label}: RuntimeError message mismatch;"
                    f" got {str(exc)!r}, expected {expected_msg!r}"
                )
            if exc.__cause__ is original_exc:
                ok(f"{exc_label}: RuntimeError.__cause__ is the original exception")
            else:
                fail(
                    f"{exc_label}: __cause__ is {type(exc.__cause__).__name__!r},"
                    f" expected original {exc_label}"
                )
        except Exception as exc:
            fail(
                f"{exc_label}: raised {type(exc).__name__} instead of RuntimeError:"
                f" {exc!r}"
            )


# ===========================================================================
# Section 4: Empty response text guard
#
# Implementation (src/code_reviewer.py lines 55-56):
#   if not response.text or not response.text.strip():
#       raise RuntimeError("Gemini API returned an empty response.")
# ===========================================================================
print()
print("=== 4. Empty response text guard ===")

_EXPECTED_EMPTY_RESP_MSG = "Gemini API returned an empty response."

for response_text, text_label in [
    (None,  "None"),
    ("",    "empty string"),
    ("   ", "whitespace-only string"),
]:
    with patch(_PATCH_TARGET, return_value=_make_mock_client(response_text)):
        try:
            review_code_diff(_VALID_DIFF)
            fail(
                f"response.text={text_label!r}: review_code_diff did not raise"
                f" -- expected RuntimeError"
            )
        except RuntimeError as exc:
            if str(exc) == _EXPECTED_EMPTY_RESP_MSG:
                ok(
                    f"response.text={text_label!r}: raises RuntimeError"
                    f" '{_EXPECTED_EMPTY_RESP_MSG}'"
                )
            else:
                fail(
                    f"response.text={text_label!r}: wrong RuntimeError message:"
                    f" {str(exc)!r}"
                )
        except Exception as exc:
            fail(
                f"response.text={text_label!r}: raised {type(exc).__name__}"
                f" instead of RuntimeError: {exc!r}"
            )

# A non-empty, non-whitespace response must be returned verbatim.
with patch(_PATCH_TARGET, return_value=_make_mock_client("Looks good!")):
    try:
        result = review_code_diff(_VALID_DIFF)
        if result == "Looks good!":
            ok("Non-empty response text returned verbatim by review_code_diff")
        else:
            fail(
                f"review_code_diff returned unexpected value: {result!r};"
                f" expected 'Looks good!'"
            )
    except Exception as exc:
        fail(f"Non-empty response raised unexpectedly: {exc!r}")


# ===========================================================================
# Section 5: get_gemini_client is called exactly once per review_code_diff call
# ===========================================================================
print()
print("=== 5. get_gemini_client called exactly once per review ===")

with patch(_PATCH_TARGET) as mock_get_client:
    mock_client = _make_mock_client("result")
    mock_get_client.return_value = mock_client
    try:
        review_code_diff(_VALID_DIFF)
    except Exception:
        pass

if mock_get_client.call_count == 1:
    ok("get_gemini_client() called exactly once per review_code_diff invocation")
else:
    fail(
        f"get_gemini_client() called {mock_get_client.call_count} times,"
        f" expected exactly 1"
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
    print("All code-reviewer edge-case tests passed.")
    print("=" * 60)
    sys.exit(0)
