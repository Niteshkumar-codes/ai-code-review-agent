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

import httpx
from google.genai import errors as sdk_errors
from src.review_nodes import (
    _is_transient_error,
    _TRANSIENT_STATUS_CODES,
    _TRANSIENT_HTTPX_EXCEPTIONS,
)


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


def wrap_as_node_api_runtime_error(api_err: sdk_errors.APIError) -> RuntimeError:
    """
    Replicate exactly how _call_gemini wraps an APIError:
        raise RuntimeError(f"Gemini API error in review node: {err.message}") from err
    """
    rt = RuntimeError(f"Gemini API error in review node: {api_err.message}")
    rt.__cause__ = api_err
    return rt


def wrap_as_node_exc_runtime_error(exc: Exception) -> RuntimeError:
    """
    Replicate exactly how _call_gemini wraps a non-APIError exception:
        raise RuntimeError(f"Unexpected error in review node: {err}") from err
    """
    rt = RuntimeError(f"Unexpected error in review node: {exc}")
    rt.__cause__ = exc
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
# Section 1: APIError predicate tests -- real SDK instances
# ---------------------------------------------------------------------------

print()
print("=== 1. _is_transient_error -- real SDK APIError instances ===")

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
    wrapped = wrap_as_node_api_runtime_error(api_err)
    result = _is_transient_error(wrapped)
    ok = result == expected
    if not ok:
        failures.append((http_code, expected, result, description))
    marker = "OK  " if ok else "FAIL"
    decision = "retry    " if result else "no-retry "
    print(f"  [{marker}] HTTP {http_code}  =>  {decision}  ({description})")


# ---------------------------------------------------------------------------
# Section 2: Edge cases -- non-RuntimeError and permanent-cause errors
# ---------------------------------------------------------------------------

print()
print("=== 2. Edge cases -- non-RuntimeError and permanent causes ===")

# 2a. Plain RuntimeError with no __cause__ -- NOT transient (no evidence of
#     a known retriable failure; conservative default after the fix).
plain_rt = RuntimeError("connection reset by peer")
result = _is_transient_error(plain_rt)
if result is False:
    print("  [OK  ] Plain RuntimeError (no __cause__) => no-retry")
else:
    failures.append((None, False, result, "Plain RuntimeError (no __cause__) must not retry"))
    print("  [FAIL] Plain RuntimeError (no __cause__) => expected no-retry, got retry")

# 2b. Non-RuntimeError at top level -- must never retry.
for exc_type, name in [(ValueError, "ValueError"), (KeyError, "KeyError"), (OSError, "OSError")]:
    result = _is_transient_error(exc_type("some error"))
    if result is False:
        print(f"  [OK  ] {name} at top level => no-retry")
    else:
        failures.append((None, False, result, f"{name} at top level should not retry"))
        print(f"  [FAIL] {name} at top level => expected no-retry, got retry")

# 2c. RuntimeError with a ValueError __cause__ -- permanent; must NOT retry.
rt_val = RuntimeError("unexpected non-API error")
rt_val.__cause__ = ValueError("inner non-api problem")
result = _is_transient_error(rt_val)
if result is False:
    print("  [OK  ] RuntimeError with ValueError __cause__ => no-retry")
else:
    failures.append((None, False, result, "RuntimeError with ValueError __cause__ should not retry"))
    print("  [FAIL] RuntimeError with ValueError __cause__ => expected no-retry, got retry")

# 2d. RuntimeError with a TypeError __cause__ -- permanent; must NOT retry.
rt_type = RuntimeError("type error caused failure")
rt_type.__cause__ = TypeError("unexpected type")
result = _is_transient_error(rt_type)
if result is False:
    print("  [OK  ] RuntimeError with TypeError __cause__ => no-retry")
else:
    failures.append((None, False, result, "RuntimeError with TypeError __cause__ should not retry"))
    print("  [FAIL] RuntimeError with TypeError __cause__ => expected no-retry, got retry")

# 2e. _TRANSIENT_STATUS_CODES content.
assert _TRANSIENT_STATUS_CODES == frozenset({500, 502, 503, 504}), (
    f"Unexpected transient set: {_TRANSIENT_STATUS_CODES}"
)
print(f"  [OK  ] _TRANSIENT_STATUS_CODES = {sorted(_TRANSIENT_STATUS_CODES)}")

# 2f. ServerError re-export from review_nodes is the real SDK class.
from src.review_nodes import ServerError as imported_ServerError
assert imported_ServerError is sdk_errors.ServerError, (
    "ServerError in review_nodes must be the real SDK class"
)
print("  [OK  ] ServerError imported in review_nodes == sdk_errors.ServerError")


# ---------------------------------------------------------------------------
# Section 3: httpx timeout and connectivity exception tests
#
# When httpx raises TimeoutException (or a subclass) or ConnectError during
# generate_content(), _call_gemini catches it via `except Exception` and wraps
# it as RuntimeError(...) from httpx_exc.  _is_transient_error must recognise
# these as retriable because they are genuine transient network failures.
# ---------------------------------------------------------------------------

print()
print("=== 3. httpx timeout and connectivity exceptions ===")

# 3a. _TRANSIENT_HTTPX_EXCEPTIONS covers the correct base classes.
assert httpx.TimeoutException in _TRANSIENT_HTTPX_EXCEPTIONS, (
    "httpx.TimeoutException must be in _TRANSIENT_HTTPX_EXCEPTIONS"
)
assert httpx.ConnectError in _TRANSIENT_HTTPX_EXCEPTIONS, (
    "httpx.ConnectError must be in _TRANSIENT_HTTPX_EXCEPTIONS"
)
print("  [OK  ] _TRANSIENT_HTTPX_EXCEPTIONS covers TimeoutException and ConnectError")

# 3b. httpx.ReadTimeout -- server slow to send response body.
read_timeout = httpx.ReadTimeout("timed out reading response")
result = _is_transient_error(wrap_as_node_exc_runtime_error(read_timeout))
if result is True:
    print("  [OK  ] httpx.ReadTimeout wrapped as RuntimeError => retry")
else:
    failures.append((None, True, result, "httpx.ReadTimeout should retry"))
    print("  [FAIL] httpx.ReadTimeout wrapped as RuntimeError => expected retry, got no-retry")

# 3c. httpx.ConnectTimeout -- timeout establishing TCP connection.
connect_timeout = httpx.ConnectTimeout("timed out connecting to host")
result = _is_transient_error(wrap_as_node_exc_runtime_error(connect_timeout))
if result is True:
    print("  [OK  ] httpx.ConnectTimeout wrapped as RuntimeError => retry")
else:
    failures.append((None, True, result, "httpx.ConnectTimeout should retry"))
    print("  [FAIL] httpx.ConnectTimeout wrapped as RuntimeError => expected retry, got no-retry")

# 3d. httpx.WriteTimeout -- timeout flushing request body.
write_timeout = httpx.WriteTimeout("timed out sending request body")
result = _is_transient_error(wrap_as_node_exc_runtime_error(write_timeout))
if result is True:
    print("  [OK  ] httpx.WriteTimeout wrapped as RuntimeError => retry")
else:
    failures.append((None, True, result, "httpx.WriteTimeout should retry"))
    print("  [FAIL] httpx.WriteTimeout wrapped as RuntimeError => expected retry, got no-retry")

# 3e. httpx.PoolTimeout -- no connection slot available.
pool_timeout = httpx.PoolTimeout("connection pool exhausted")
result = _is_transient_error(wrap_as_node_exc_runtime_error(pool_timeout))
if result is True:
    print("  [OK  ] httpx.PoolTimeout wrapped as RuntimeError => retry")
else:
    failures.append((None, True, result, "httpx.PoolTimeout should retry"))
    print("  [FAIL] httpx.PoolTimeout wrapped as RuntimeError => expected retry, got no-retry")

# 3f. httpx.ConnectError -- TCP refused or DNS failure.
connect_error = httpx.ConnectError("connection refused")
result = _is_transient_error(wrap_as_node_exc_runtime_error(connect_error))
if result is True:
    print("  [OK  ] httpx.ConnectError wrapped as RuntimeError => retry")
else:
    failures.append((None, True, result, "httpx.ConnectError should retry"))
    print("  [FAIL] httpx.ConnectError wrapped as RuntimeError => expected retry, got no-retry")

# 3g. httpx.TimeoutException base class -- must retry.
base_timeout = httpx.TimeoutException("generic timeout")
result = _is_transient_error(wrap_as_node_exc_runtime_error(base_timeout))
if result is True:
    print("  [OK  ] httpx.TimeoutException (base) wrapped as RuntimeError => retry")
else:
    failures.append((None, True, result, "httpx.TimeoutException base should retry"))
    print("  [FAIL] httpx.TimeoutException (base) => expected retry, got no-retry")

# 3h. httpx.InvalidURL -- a programming / permanent error, NOT transient.
#     InvalidURL is NOT a TimeoutException or ConnectError subclass.
invalid_url = httpx.InvalidURL("bad url scheme")
result = _is_transient_error(wrap_as_node_exc_runtime_error(invalid_url))
if result is False:
    print("  [OK  ] httpx.InvalidURL wrapped as RuntimeError => no-retry")
else:
    failures.append((None, False, result, "httpx.InvalidURL should not retry"))
    print("  [FAIL] httpx.InvalidURL wrapped as RuntimeError => expected no-retry, got retry")

# 3i. MRO sanity: all concrete timeout subclasses derive from TimeoutException.
for cls, label in [
    (httpx.ReadTimeout,    "ReadTimeout"),
    (httpx.WriteTimeout,   "WriteTimeout"),
    (httpx.ConnectTimeout, "ConnectTimeout"),
    (httpx.PoolTimeout,    "PoolTimeout"),
]:
    assert issubclass(cls, httpx.TimeoutException), (
        f"httpx.{label} must be a subclass of httpx.TimeoutException"
    )
print(
    "  [OK  ] ReadTimeout / WriteTimeout / ConnectTimeout / PoolTimeout are all "
    "subclasses of httpx.TimeoutException (isinstance check covers them all)"
)


# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------

print()
if failures:
    print("FAILURES:")
    for item in failures:
        code, expected, actual, desc = item
        if code is not None:
            print(f"  HTTP {code}: expected retry={expected}, got {actual}  ({desc})")
        else:
            print(f"  {desc}: expected={expected}, got={actual}")
    sys.exit(1)
else:
    print("=" * 62)
    print("All retry predicate tests passed.")
    print("=" * 62)
    sys.exit(0)
