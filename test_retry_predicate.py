r"""
Focused offline retry-predicate tests for src/review_nodes.py.
Uses real installed google-genai SDK exception instances.
No network calls, no Gemini API calls, no GitHub API calls.

Run: .venv\Scripts\python.exe test_retry_predicate.py
"""
import os
import sys

# Prevent Config from complaining about missing keys.
# These sentinel values are never sent to any API.
os.environ.setdefault("GEMINI_API_KEY", "offline-test-sentinel")
os.environ.setdefault("GITHUB_TOKEN", "offline-test-sentinel")

from google.genai import errors as sdk_errors
from src.review_nodes import _is_transient_error, _TRANSIENT_STATUS_CODES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_sdk_error(http_code: int, message: str = "test error") -> sdk_errors.APIError:
    """
    Build a real SDK exception using the same constructor the SDK uses
    internally. Guarantees the instance has the exact same attributes as a
    live API error (i.e. .code, .status, .message -- NOT .status_code).
    """
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


def wrap_as_node_runtime_error(api_err: sdk_errors.APIError) -> RuntimeError:
    """
    Replicate exactly how _call_gemini wraps an APIError:
        raise RuntimeError(f"Gemini API error in review node: {err.message}") from err
    """
    rt = RuntimeError(f"Gemini API error in review node: {api_err.message}")
    rt.__cause__ = api_err
    return rt


# ---------------------------------------------------------------------------
# Sanity-check the real SDK attribute names before running predicate tests
# ---------------------------------------------------------------------------

print("=== SDK attribute verification ===")
client_err = make_sdk_error(429, "quota exceeded")
server_err = make_sdk_error(503, "model overloaded")

assert isinstance(client_err, sdk_errors.ClientError), "429 must produce ClientError"
assert isinstance(server_err, sdk_errors.ServerError), "503 must produce ServerError"
assert isinstance(client_err, sdk_errors.APIError),    "ClientError must subclass APIError"
assert isinstance(server_err, sdk_errors.APIError),    "ServerError must subclass APIError"

assert hasattr(client_err, "code"),           "APIError must have .code attribute"
assert not hasattr(client_err, "status_code"),"APIError must NOT have .status_code"
assert client_err.code == 429, f"Expected .code=429, got {client_err.code!r}"
assert server_err.code == 503, f"Expected .code=503, got {server_err.code!r}"

print(f"  ClientError(429).code = {client_err.code!r}  (ok)")
print(f"  ServerError(503).code = {server_err.code!r}  (ok)")
print(f"  .status_code exists   = {hasattr(client_err, 'status_code')}  (expected False) (ok)")


# ---------------------------------------------------------------------------
# Main predicate tests: real SDK instances wrapped as RuntimeError
# ---------------------------------------------------------------------------

print()
print("=== _is_transient_error -- real SDK instances ===")

test_cases = [
    # (http_code, expected_should_retry, description)
    (400, False, "Bad Request - invalid request body"),
    (401, False, "Unauthenticated - invalid API key"),
    (403, False, "Permission Denied - forbidden"),
    (404, False, "Not Found - model does not exist"),
    (429, False, "Resource Exhausted - quota / rate limit"),
    (500, True,  "Internal Server Error - transient"),
    (502, True,  "Bad Gateway - transient"),
    (503, True,  "Service Unavailable / model overloaded - transient"),
    (504, True,  "Gateway Timeout - transient"),
]

failures = []
for http_code, expected, description in test_cases:
    api_err = make_sdk_error(http_code)
    wrapped = wrap_as_node_runtime_error(api_err)
    result = _is_transient_error(wrapped)
    ok = result == expected
    if not ok:
        failures.append((http_code, expected, result, description))
    marker = "OK  " if ok else "FAIL"
    decision = "retry    " if result else "no-retry "
    print(f"  [{marker}] HTTP {http_code}  =>  {decision}  ({description})")


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------

print()
print("=== Edge cases ===")

# 1. Plain RuntimeError with no cause -- must retry (e.g. network connection reset)
plain_rt = RuntimeError("connection reset by peer")
result = _is_transient_error(plain_rt)
assert result is True, f"Plain RuntimeError should retry; got {result}"
print("  [OK  ] Plain RuntimeError (no __cause__) => retry")

# 2. Non-RuntimeError at top level -- must never retry
for exc_type, name in [(ValueError, "ValueError"), (KeyError, "KeyError"), (OSError, "OSError")]:
    result = _is_transient_error(exc_type("some error"))
    assert result is False, f"{name} should not retry; got {result}"
print("  [OK  ] ValueError / KeyError / OSError => no-retry")

# 3. RuntimeError whose cause is a non-APIError -- must retry
rt_with_other_cause = RuntimeError("unexpected non-API error")
rt_with_other_cause.__cause__ = ValueError("inner non-api problem")
result = _is_transient_error(rt_with_other_cause)
assert result is True, f"RuntimeError with non-APIError cause should retry; got {result}"
print("  [OK  ] RuntimeError with non-APIError __cause__ => retry")

# 4. _TRANSIENT_STATUS_CODES content
assert _TRANSIENT_STATUS_CODES == frozenset({500, 502, 503, 504}), (
    f"Unexpected transient set: {_TRANSIENT_STATUS_CODES}"
)
print(f"  [OK  ] _TRANSIENT_STATUS_CODES = {sorted(_TRANSIENT_STATUS_CODES)}")

# 5. ServerError re-export from review_nodes is the real SDK class
from src.review_nodes import ServerError as imported_ServerError
assert imported_ServerError is sdk_errors.ServerError, (
    "ServerError in review_nodes must be the real SDK class"
)
print("  [OK  ] ServerError imported in review_nodes == sdk_errors.ServerError")


# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------

print()
if failures:
    print("FAILURES:")
    for code, expected, actual, desc in failures:
        print(f"  HTTP {code}: expected retry={expected}, got {actual}  ({desc})")
    sys.exit(1)
else:
    print("=" * 54)
    print("All retry predicate tests passed.")
    print("=" * 54)
    sys.exit(0)
