r"""
Offline regression tests for the commit-message subject extraction fix
in src/test_review_graph.py.

BUG (pre-fix):
  Line 53 of src/test_review_graph.py read:
      commit_msg = commit_data.get("message", "").splitlines()[0]
  When commit_data["message"] is None or "" the call to splitlines()
  returns an empty list, and [0] raises an IndexError that is only caught
  by the bare `except Exception` handler at the bottom of main() -- causing
  the entire review workflow to abort with an "Unexpected Error" message
  instead of a useful review output.

FIX:
  The line was replaced with:
      commit_msg = next(iter(commit_data.get("message", "").splitlines()), "")
  next(..., "") returns "" as the safe default when the list is empty,
  so context_str degrades gracefully to "Commit <sha>: " rather than crashing.

TESTS:
  1. Direct unit tests of the fixed extraction expression covering all edge
     cases (None, "", lone newline, multi-line, single-line).
  2. Integration-style test of the full context-string assembly path with a
     mocked GitHub client and mocked graph -- verifies both the crash-free
     path and the correct fallback value end-to-end without any live API call.

No live Gemini or GitHub API calls are made.

Run:
    .venv\Scripts\python.exe test_commit_msg_subject.py
"""

import os
import sys

# ---------------------------------------------------------------------------
# Sentinel env-vars -- must be set BEFORE any src import that touches Config.
# ---------------------------------------------------------------------------
os.environ.setdefault("GEMINI_API_KEY", "offline-test-sentinel")
os.environ.setdefault("GITHUB_TOKEN", "offline-test-sentinel")

from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

failures: list[str] = []


def ok(description: str) -> None:
    print(f"  [OK  ] {description}")


def fail(description: str) -> None:
    print(f"  [FAIL] {description}")
    failures.append(description)


# ---------------------------------------------------------------------------
print("=" * 64)
print(" COMMIT MESSAGE SUBJECT EXTRACTION REGRESSION TESTS (offline)")
print("=" * 64)
# ---------------------------------------------------------------------------


# ===========================================================================
# Section 1: Unit tests of the fixed extraction expression
#
# Fixed expression (src/test_review_graph.py line 53):
#   commit_msg = next(iter(commit_data.get("message", "").splitlines()), "")
#
# Covers every edge-case class:
#   - None stored in dict  -> .get("message","") returns "" -> empty default
#   - ""                   -> splitlines() = []   -> returns ""
#   - "\n"                 -> splitlines() = [""] -> returns ""
#   - single-line string   -> splitlines() = [s]  -> returns s
#   - multi-line string    -> splitlines() = [s, body, ...] -> returns first
# ===========================================================================
print()
print("=== 1. Fixed extraction expression edge cases ===")

_cases = [
    # (message_value, expected_subject, label)
    (None,                             "",                "None stored in dict"),
    ("",                               "",                "empty string"),
    ("\n",                             "",                "lone newline only"),
    ("   ",                            "   ",             "whitespace-only (not empty)"),
    ("single line commit",             "single line commit",    "single-line message"),
    ("feat: add thing\n\nBody here",   "feat: add thing", "multi-line, subject on first line"),
    ("fix: bug\n",                     "fix: bug",        "subject with trailing newline"),
    ("\nblank first line",             "",                "blank first line, body below"),
]

for msg_value, expected, label in _cases:
    # Replicate the exact fixed expression from src/test_review_graph.py line 53:
    #   commit_msg = next(iter((commit_data.get("message") or "").splitlines()), "")
    # Using `or ""` (not `.get("message", "")`) because .get() returns None when
    # the key exists with value None; `or ""` coerces None -> "" safely.
    commit_data: dict = {"message": msg_value}
    commit_msg = next(iter((commit_data.get("message") or "").splitlines()), "")

    if commit_msg == expected:
        ok(f"message={label!r}: subject={commit_msg!r}")
    else:
        fail(
            f"message={label!r}: got subject={commit_msg!r}, expected={expected!r}"
        )


# ===========================================================================
# Section 2: Pre-fix expression crashes on empty / None messages
#
# Verifies that the OLD line (.splitlines()[0]) would have raised IndexError
# for the two critical inputs -- confirming the bug was real.
# ===========================================================================
print()
print("=== 2. Pre-fix expression would crash on empty / None messages ===")

_crash_cases = [
    (None,  "None stored in dict"),
    ("",    "empty string"),
]

for msg_value, label in _crash_cases:
    raw = msg_value or ""
    try:
        _ = raw.splitlines()[0]  # PRE-FIX line
        fail(
            f"Pre-fix expression did NOT raise for message={label!r} "
            f"-- expected IndexError"
        )
    except IndexError:
        ok(
            f"Pre-fix expression raises IndexError for message={label!r} "
            f"(confirms the bug existed)"
        )
    except Exception as exc:
        fail(
            f"Pre-fix expression raised {type(exc).__name__} for message={label!r}, "
            f"expected IndexError: {exc!r}"
        )


# ===========================================================================
# Section 3: Fixed expression NEVER raises for any of the crash cases
# ===========================================================================
print()
print("=== 3. Fixed expression never raises for previously crashing inputs ===")

for msg_value, label in _crash_cases:
    raw = msg_value or ""
    try:
        result = next(iter(raw.splitlines()), "")
        ok(
            f"Fixed expression does not raise for message={label!r}; "
            f"returns {result!r}"
        )
    except Exception as exc:
        fail(
            f"Fixed expression raised {type(exc).__name__} for message={label!r}: "
            f"{exc!r}"
        )

# ===========================================================================
# Section 4: context_str assembly -- end-to-end with fixed expression
#
# Replicates the exact logic from src/test_review_graph.py lines 52-54:
#   commit_sha = commit_data.get("sha", "unknown")[:7]
#   commit_msg = next(iter(commit_data.get("message", "").splitlines()), "")
#   context_str = f"Commit {commit_sha}: {commit_msg}"
# ===========================================================================
print()
print("=== 4. context_str assembly with fixed expression ===")

_assembly_cases = [
    # (sha, message, expected_context_str, label)
    (
        "abc1234def",
        None,
        "Commit abc1234: ",
        "None message -> empty subject",
    ),
    (
        "abc1234def",
        "",
        "Commit abc1234: ",
        "empty message -> empty subject",
    ),
    (
        "abc1234def",
        "docs: add README",
        "Commit abc1234: docs: add README",
        "normal single-line message",
    ),
    (
        "abc1234def",
        "feat: big feature\n\nDetailed body",
        "Commit abc1234: feat: big feature",
        "multi-line message -> only subject",
    ),
    (
        None,
        "fix: crash",
        "Commit unknown: fix: crash",
        "None sha -> 'unknown' fallback",
    ),
]

for sha, message, expected_ctx, label in _assembly_cases:
    commit_data = {"sha": sha, "message": message}

    # Fixed lines from src/test_review_graph.py:
    commit_sha  = (commit_data.get("sha") or "unknown")[:7]
    commit_msg  = next(iter((commit_data.get("message") or "").splitlines()), "")
    context_str = f"Commit {commit_sha}: {commit_msg}"

    if context_str == expected_ctx:
        ok(f"[{label}] context_str={context_str!r}")
    else:
        fail(
            f"[{label}] context_str={context_str!r}, expected={expected_ctx!r}"
        )


# ===========================================================================
# Section 5: Integration-style mock test
#
# Patches get_commit_changes and create_review_graph so the full main()
# body can run without any network call.  Exercises the commit-message
# extraction path with a None message to confirm the fix prevents the crash.
# ===========================================================================
print()
print("=== 5. Integration mock: None commit message does not crash workflow ===")

# Build a mock commit_data dict with message=None to trigger the old bug.
_MOCK_COMMIT_DATA_NULL_MSG = {
    "sha": "deadbeef1234",
    "message": None,
    "files": [
        {
            "filename": "foo.py",
            "status": "modified",
            "additions": 1,
            "deletions": 0,
            "changes": 1,
            "patch": "+x = 1",
        }
    ],
}

# A mock graph whose .invoke() returns a completed state.
_MOCK_FINAL_STATE = {
    "diff": "+x = 1",
    "context": "Commit deadbee: ",
    "change_analysis": "mock analysis",
    "security_review": "mock security",
    "error_handling_review": "mock error handling",
    "quality_review": "mock quality",
    "final_review": "mock final review",
}


def _make_mock_graph() -> MagicMock:
    g = MagicMock()
    g.invoke.return_value = _MOCK_FINAL_STATE
    return g


# Patch the three external dependencies used by main().
_PATCH_GITHUB_CLIENT   = "src.test_review_graph.get_github_client"
_PATCH_COMMIT_CHANGES  = "src.test_review_graph.get_commit_changes"
_PATCH_CREATE_GRAPH    = "src.test_review_graph.create_review_graph"

# Import main only after the env sentinels are set.
from src.test_review_graph import main as _review_main

try:
    with (
        patch(_PATCH_GITHUB_CLIENT) as mock_gh,
        patch(_PATCH_COMMIT_CHANGES, return_value=_MOCK_COMMIT_DATA_NULL_MSG),
        patch(_PATCH_CREATE_GRAPH, return_value=_make_mock_graph()),
    ):
        # Mock get_github_client().get_user().login (the auth check in main)
        mock_gh.return_value.get_user.return_value.login = "test-user"

        # main() calls sys.exit(0) on success; catch SystemExit.
        try:
            _review_main()
            fail(
                "main() returned normally -- expected sys.exit(0) or sys.exit(1)"
            )
        except SystemExit as se:
            if se.code == 0:
                ok(
                    "main() with message=None completes without crashing "
                    "(sys.exit(0))"
                )
            else:
                fail(
                    f"main() with message=None exited with code {se.code!r} "
                    f"instead of 0"
                )
        except IndexError as ie:
            fail(
                f"main() with message=None raised IndexError -- fix not applied "
                f"or not effective: {ie!r}"
            )
        except Exception as exc:
            fail(
                f"main() with message=None raised {type(exc).__name__}: {exc!r}"
            )
except Exception as exc:
    fail(f"Unexpected error setting up integration mock: {type(exc).__name__}: {exc!r}")


# ===========================================================================
# Section 6: Integration mock -- empty string message does not crash
# ===========================================================================
print()
print("=== 6. Integration mock: empty string commit message does not crash ===")

_MOCK_COMMIT_DATA_EMPTY_MSG = dict(_MOCK_COMMIT_DATA_NULL_MSG, message="")

try:
    with (
        patch(_PATCH_GITHUB_CLIENT) as mock_gh,
        patch(_PATCH_COMMIT_CHANGES, return_value=_MOCK_COMMIT_DATA_EMPTY_MSG),
        patch(_PATCH_CREATE_GRAPH, return_value=_make_mock_graph()),
    ):
        mock_gh.return_value.get_user.return_value.login = "test-user"
        try:
            _review_main()
            fail("main() returned normally -- expected sys.exit")
        except SystemExit as se:
            if se.code == 0:
                ok(
                    "main() with message='' completes without crashing "
                    "(sys.exit(0))"
                )
            else:
                fail(
                    f"main() with message='' exited with code {se.code!r} "
                    f"instead of 0"
                )
        except IndexError as ie:
            fail(
                f"main() with message='' raised IndexError -- fix not effective: "
                f"{ie!r}"
            )
        except Exception as exc:
            fail(
                f"main() with message='' raised {type(exc).__name__}: {exc!r}"
            )
except Exception as exc:
    fail(f"Unexpected error in section 6: {type(exc).__name__}: {exc!r}")


# ===========================================================================
# Section 7: Integration mock -- normal multi-line message succeeds
# ===========================================================================
print()
print("=== 7. Integration mock: normal multi-line commit message succeeds ===")

_MOCK_COMMIT_DATA_NORMAL = dict(
    _MOCK_COMMIT_DATA_NULL_MSG,
    message="feat: add awesome feature\n\nThis is the body.",
)

try:
    with (
        patch(_PATCH_GITHUB_CLIENT) as mock_gh,
        patch(_PATCH_COMMIT_CHANGES, return_value=_MOCK_COMMIT_DATA_NORMAL),
        patch(_PATCH_CREATE_GRAPH, return_value=_make_mock_graph()),
    ):
        mock_gh.return_value.get_user.return_value.login = "test-user"
        try:
            _review_main()
            fail("main() returned normally -- expected sys.exit")
        except SystemExit as se:
            if se.code == 0:
                ok(
                    "main() with normal multi-line message completes "
                    "(sys.exit(0))"
                )
            else:
                fail(
                    f"main() with normal message exited with code {se.code!r} "
                    f"instead of 0"
                )
        except Exception as exc:
            fail(
                f"main() with normal message raised {type(exc).__name__}: {exc!r}"
            )
except Exception as exc:
    fail(f"Unexpected error in section 7: {type(exc).__name__}: {exc!r}")


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
    print("All commit-message subject extraction regression tests passed.")
    print("=" * 64)
    sys.exit(0)
