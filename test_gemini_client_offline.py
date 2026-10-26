r"""
Focused offline unit tests for src/gemini_client.py.

Covers (all derived directly from source, not from any report):

  1. _TEST_TIMEOUT_MS constant value  (30 * 1000 = 30_000 ms = 30 s).
  2. AutomaticFunctionCallingConfig(disable=True) is present in the
     GenerateContentConfig passed to client.models.generate_content.
  3. HttpOptions(timeout=_TEST_TIMEOUT_MS) is present in the same config.
  4. Successful response -- response.text is returned verbatim.
  5. Empty / whitespace-only response.text raises RuntimeError with the
     exact message "Gemini API returned an empty response."
  6. Missing GEMINI_API_KEY raises ValueError mentioning 'GEMINI_API_KEY'.
  7. get_gemini_client() constructs genai.Client with the key stored in
     Config.GEMINI_API_KEY (client construction itself is mocked so no
     real connection occurs).

No live Gemini or GitHub API calls are made.
No secrets or .env values are printed.
genai.Client and client.models.generate_content are fully mocked.

Run:
    .venv\Scripts\python.exe test_gemini_client_offline.py
"""

import os
import sys

# ---------------------------------------------------------------------------
# Sentinel env-vars -- never sent to any external service.
# Must be set BEFORE any src module that imports Config is imported.
# ---------------------------------------------------------------------------
os.environ.setdefault("GEMINI_API_KEY", "offline-test-sentinel")
os.environ.setdefault("GITHUB_TOKEN",   "offline-test-sentinel")

from pathlib import Path
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import src.config as cfg_mod
from src.gemini_client import _TEST_TIMEOUT_MS, generate_test_response, get_gemini_client

# ---------------------------------------------------------------------------
# Helpers (same style as existing test suites in this repository)
# ---------------------------------------------------------------------------

failures: list[str] = []


def ok(description: str) -> None:
    print(f"  [OK  ] {description}")


def fail(description: str) -> None:
    print(f"  [FAIL] {description}")
    failures.append(description)


# Patch target: genai.Client lives in src.gemini_client's namespace.
_PATCH_GENAI_CLIENT = "src.gemini_client.genai.Client"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(text: str | None) -> MagicMock:
    """Return a MagicMock response whose .text attribute equals *text*."""
    resp = MagicMock()
    resp.text = text
    return resp


def _make_mock_client(response_text: str | None) -> MagicMock:
    """Return a mock genai.Client whose models.generate_content returns a
    response with the given text.  No real client construction occurs."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response(response_text)
    return mock_client


# ===========================================================================
print("=" * 62)
print(" GEMINI CLIENT OFFLINE TESTS")
print("=" * 62)
# ===========================================================================


# ===========================================================================
# Section 1: _TEST_TIMEOUT_MS constant
#
# Source (gemini_client.py line 8):
#   _TEST_TIMEOUT_MS: int = 30 * 1000
# ===========================================================================
print()
print("=== 1. _TEST_TIMEOUT_MS constant value ===")

_EXPECTED_TIMEOUT_MS = 30 * 1000  # 30_000

if _TEST_TIMEOUT_MS == _EXPECTED_TIMEOUT_MS:
    ok(f"_TEST_TIMEOUT_MS == {_EXPECTED_TIMEOUT_MS} (30 s expressed in ms)")
else:
    fail(
        f"_TEST_TIMEOUT_MS is {_TEST_TIMEOUT_MS!r}, expected {_EXPECTED_TIMEOUT_MS!r}"
    )

if isinstance(_TEST_TIMEOUT_MS, int):
    ok("_TEST_TIMEOUT_MS is of type int")
else:
    fail(
        f"_TEST_TIMEOUT_MS is {type(_TEST_TIMEOUT_MS).__name__!r}, expected int"
    )


# ===========================================================================
# Section 2: automatic_function_calling is disabled in the request config
#
# Source (gemini_client.py lines 22-25):
#   config = types.GenerateContentConfig(
#       automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
#       ...
#   )
# We verify the concrete value passed to generate_content via call inspection.
# ===========================================================================
print()
print("=== 2. AutomaticFunctionCallingConfig(disable=True) in request config ===")

with patch(_PATCH_GENAI_CLIENT) as MockClient:
    mock_instance = _make_mock_client("ok response")
    MockClient.return_value = mock_instance

    generate_test_response(prompt="test", model_name="gemini-test-model")

call_args = mock_instance.models.generate_content.call_args
if call_args is None:
    fail("generate_content was never called")
else:
    config_arg = call_args.kwargs.get("config") or (
        call_args.args[2] if len(call_args.args) > 2 else None
    )
    if config_arg is None:
        fail("No 'config' argument found in generate_content call")
    else:
        afc = getattr(config_arg, "automatic_function_calling", None)
        if afc is None:
            fail(
                "GenerateContentConfig has no 'automatic_function_calling' attribute"
            )
        else:
            disable_val = getattr(afc, "disable", None)
            if disable_val is True:
                ok("automatic_function_calling.disable == True")
            else:
                fail(
                    f"automatic_function_calling.disable is {disable_val!r},"
                    " expected True"
                )


# ===========================================================================
# Section 3: HttpOptions(timeout=_TEST_TIMEOUT_MS) in request config
#
# Source (gemini_client.py line 28):
#   http_options=types.HttpOptions(timeout=_TEST_TIMEOUT_MS),
# ===========================================================================
print()
print("=== 3. HttpOptions(timeout=_TEST_TIMEOUT_MS) in request config ===")

with patch(_PATCH_GENAI_CLIENT) as MockClient:
    mock_instance = _make_mock_client("ok response")
    MockClient.return_value = mock_instance

    generate_test_response(prompt="test", model_name="gemini-test-model")

call_args = mock_instance.models.generate_content.call_args
if call_args is None:
    fail("generate_content was never called (section 3)")
else:
    config_arg = call_args.kwargs.get("config") or (
        call_args.args[2] if len(call_args.args) > 2 else None
    )
    if config_arg is None:
        fail("No 'config' argument in generate_content call (section 3)")
    else:
        http_opts = getattr(config_arg, "http_options", None)
        if http_opts is None:
            fail("GenerateContentConfig has no 'http_options' attribute")
        else:
            timeout_val = getattr(http_opts, "timeout", None)
            if timeout_val == _TEST_TIMEOUT_MS:
                ok(
                    f"http_options.timeout == {_TEST_TIMEOUT_MS}"
                    f" (matches _TEST_TIMEOUT_MS)"
                )
            else:
                fail(
                    f"http_options.timeout is {timeout_val!r},"
                    f" expected {_TEST_TIMEOUT_MS!r}"
                )


# ===========================================================================
# Section 4: Successful response text returned verbatim
#
# Source (gemini_client.py line 38):
#   return response.text
# ===========================================================================
print()
print("=== 4. Successful response: response.text returned verbatim ===")

_GOOD_RESPONSES = [
    "Gemini API connection verified successfully!",
    "hello",
    "  leading and trailing spaces  ",
]

for expected_text in _GOOD_RESPONSES:
    with patch(_PATCH_GENAI_CLIENT) as MockClient:
        MockClient.return_value = _make_mock_client(expected_text)
        try:
            result = generate_test_response(
                prompt="any prompt", model_name="gemini-test-model"
            )
            if result == expected_text:
                ok(f"response.text {expected_text!r} returned verbatim")
            else:
                fail(
                    f"generate_test_response returned {result!r},"
                    f" expected {expected_text!r}"
                )
        except Exception as exc:
            fail(
                f"generate_test_response raised unexpectedly for text"
                f" {expected_text!r}: {exc!r}"
            )


# ===========================================================================
# Section 5: Empty / whitespace-only response.text raises RuntimeError
#
# Source (gemini_client.py lines 36-37):
#   if not response.text or not response.text.strip():
#       raise RuntimeError("Gemini API returned an empty response.")
# ===========================================================================
print()
print("=== 5. Empty / whitespace-only response raises RuntimeError ===")

_EXPECTED_EMPTY_MSG = "Gemini API returned an empty response."

for response_text, label in [
    (None,  "None"),
    ("",    "empty string"),
    ("   ", "whitespace-only string"),
    ("\t\n","tab-and-newline only"),
]:
    with patch(_PATCH_GENAI_CLIENT) as MockClient:
        MockClient.return_value = _make_mock_client(response_text)
        try:
            generate_test_response(
                prompt="any prompt", model_name="gemini-test-model"
            )
            fail(
                f"response.text={label!r}: generate_test_response did not raise"
                " -- expected RuntimeError"
            )
        except RuntimeError as exc:
            if str(exc) == _EXPECTED_EMPTY_MSG:
                ok(
                    f"response.text={label!r}: raises RuntimeError"
                    f" '{_EXPECTED_EMPTY_MSG}'"
                )
            else:
                fail(
                    f"response.text={label!r}: wrong RuntimeError message:"
                    f" {str(exc)!r}"
                )
        except Exception as exc:
            fail(
                f"response.text={label!r}: raised {type(exc).__name__}"
                f" instead of RuntimeError: {exc!r}"
            )


# ===========================================================================
# Section 6: Missing GEMINI_API_KEY raises ValueError
#
# Source (gemini_client.py lines 12-13):
#   if not Config.GEMINI_API_KEY:
#       raise ValueError("GEMINI_API_KEY is missing or empty in configuration.")
# ===========================================================================
print()
print("=== 6. Missing GEMINI_API_KEY raises ValueError ===")

_EXPECTED_VALUEERROR_MSG = "GEMINI_API_KEY is missing or empty in configuration."

_original_key = cfg_mod.Config.GEMINI_API_KEY
try:
    for empty_val, label in [
        ("",   "empty string"),
        (None, "None"),
    ]:
        cfg_mod.Config.GEMINI_API_KEY = empty_val  # type: ignore[assignment]
        try:
            get_gemini_client()
            fail(
                f"get_gemini_client() with key={label!r} did not raise"
                " -- expected ValueError"
            )
        except ValueError as exc:
            if "GEMINI_API_KEY" in str(exc):
                ok(
                    f"get_gemini_client() with key={label!r} raises ValueError"
                    f" mentioning 'GEMINI_API_KEY': {exc!r}"
                )
            else:
                fail(
                    f"get_gemini_client() raised ValueError but message lacks"
                    f" 'GEMINI_API_KEY': {exc!r}"
                )
            if str(exc) == _EXPECTED_VALUEERROR_MSG:
                ok(
                    f"ValueError message matches expected verbatim:"
                    f" '{_EXPECTED_VALUEERROR_MSG}'"
                )
            else:
                fail(
                    f"ValueError message mismatch; got {str(exc)!r},"
                    f" expected {_EXPECTED_VALUEERROR_MSG!r}"
                )
        except Exception as exc:
            fail(
                f"get_gemini_client() with key={label!r} raised"
                f" {type(exc).__name__} instead of ValueError: {exc!r}"
            )
finally:
    cfg_mod.Config.GEMINI_API_KEY = _original_key  # always restore


# ===========================================================================
# Section 7: get_gemini_client() constructs genai.Client with Config.GEMINI_API_KEY
#
# Source (gemini_client.py line 14):
#   return genai.Client(api_key=Config.GEMINI_API_KEY)
#
# We temporarily set Config.GEMINI_API_KEY to a recognisable test value and
# verify that genai.Client is called with api_key=<that value>.
# genai.Client is patched so no real connection or network request occurs.
# The test value is a synthetic non-secret string.
# ===========================================================================
print()
print("=== 7. get_gemini_client() passes api_key to genai.Client ===")

_TEST_KEY = "test-api-key-offline-synthetic-value"  # synthetic, not a real key

_original_key = cfg_mod.Config.GEMINI_API_KEY
try:
    cfg_mod.Config.GEMINI_API_KEY = _TEST_KEY
    with patch(_PATCH_GENAI_CLIENT) as MockClientCls:
        MockClientCls.return_value = MagicMock()
        returned_client = get_gemini_client()

    if MockClientCls.call_count == 1:
        ok("genai.Client() constructed exactly once by get_gemini_client()")
    else:
        fail(
            f"genai.Client() constructed {MockClientCls.call_count} times,"
            " expected 1"
        )

    call_kwargs = MockClientCls.call_args
    if call_kwargs is not None:
        passed_key = call_kwargs.kwargs.get("api_key") or (
            call_kwargs.args[0] if call_kwargs.args else None
        )
        if passed_key == _TEST_KEY:
            ok("genai.Client() received api_key == Config.GEMINI_API_KEY")
        else:
            # Never print the actual key value in failure messages
            fail(
                "genai.Client() api_key does not match Config.GEMINI_API_KEY"
            )
    else:
        fail("genai.Client() was never called")

    # The returned value must be the mock instance (no extra wrapping)
    if returned_client is MockClientCls.return_value:
        ok("get_gemini_client() returns the genai.Client instance directly")
    else:
        fail(
            "get_gemini_client() returned a different object than genai.Client()"
        )
finally:
    cfg_mod.Config.GEMINI_API_KEY = _original_key  # always restore


# ===========================================================================
# Section 8: generate_test_response uses the model name it receives
#
# Source (gemini_client.py line 31):
#   response = client.models.generate_content(
#       model=model_name,
#       contents=prompt,
#       config=config,
#   )
# ===========================================================================
print()
print("=== 8. generate_test_response forwards model_name and prompt ===")

_TEST_MODEL   = "gemini-sentinel-model"
_TEST_PROMPT  = "test prompt sentinel"

with patch(_PATCH_GENAI_CLIENT) as MockClient:
    mock_instance = _make_mock_client("some response text")
    MockClient.return_value = mock_instance

    generate_test_response(prompt=_TEST_PROMPT, model_name=_TEST_MODEL)

gc_call = mock_instance.models.generate_content.call_args
if gc_call is None:
    fail("models.generate_content was not called")
else:
    passed_model = gc_call.kwargs.get("model") or (
        gc_call.args[0] if gc_call.args else None
    )
    passed_contents = gc_call.kwargs.get("contents") or (
        gc_call.args[1] if len(gc_call.args) > 1 else None
    )

    if passed_model == _TEST_MODEL:
        ok(f"model_name '{_TEST_MODEL}' forwarded as 'model' kwarg")
    else:
        fail(
            f"'model' kwarg is {passed_model!r}, expected {_TEST_MODEL!r}"
        )

    if passed_contents == _TEST_PROMPT:
        ok(f"prompt '{_TEST_PROMPT}' forwarded as 'contents' kwarg")
    else:
        fail(
            f"'contents' kwarg is {passed_contents!r}, expected {_TEST_PROMPT!r}"
        )


# ===========================================================================
# Section 9: Config.validate() returns the correct keys
#
# Source (config.py lines 18-24):
#   @classmethod
#   def validate(cls) -> dict[str, bool]:
#       return {
#           "GEMINI_API_KEY": bool(cls.GEMINI_API_KEY),
#           "GITHUB_TOKEN": bool(cls.GITHUB_TOKEN),
#           "MONGODB_URI": bool(cls.MONGODB_URI),
#       }
# ===========================================================================
print()
print("=== 9. Config.validate() returns expected dict keys ===")

validation_result = cfg_mod.Config.validate()

if isinstance(validation_result, dict):
    ok("Config.validate() returns a dict")
else:
    fail(
        f"Config.validate() returned {type(validation_result).__name__!r},"
        " expected dict"
    )

_EXPECTED_VALIDATE_KEYS = {"GEMINI_API_KEY", "GITHUB_TOKEN", "MONGODB_URI"}
actual_keys = set(validation_result.keys())

if actual_keys == _EXPECTED_VALIDATE_KEYS:
    ok(f"Config.validate() dict has exactly the expected keys: {sorted(actual_keys)}")
else:
    missing = _EXPECTED_VALIDATE_KEYS - actual_keys
    extra   = actual_keys - _EXPECTED_VALIDATE_KEYS
    if missing:
        fail(f"Config.validate() missing keys: {sorted(missing)}")
    if extra:
        fail(f"Config.validate() has unexpected extra keys: {sorted(extra)}")

for key in _EXPECTED_VALIDATE_KEYS:
    if isinstance(validation_result.get(key), bool):
        ok(f"Config.validate()['{key}'] is bool")
    else:
        fail(
            f"Config.validate()['{key}'] is"
            f" {type(validation_result.get(key)).__name__!r}, expected bool"
        )


# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------

print()
if failures:
    print("=" * 62)
    print(f"FAILED -- {len(failures)} assertion(s) failed:")
    for i, msg in enumerate(failures, 1):
        print(f"  {i}. {msg}")
    print("=" * 62)
    sys.exit(1)
else:
    print("=" * 62)
    print("All gemini-client offline tests passed.")
    print("=" * 62)
    sys.exit(0)
