from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from github import BadCredentialsException, GithubException, UnknownObjectException
from src.code_reviewer import review_code_diff
from src.config import Config
from src.github_client import get_commit_changes, get_github_client


def main() -> None:
    print("==================================================")
    print(" PHASE 5: SINGLE AI CODE REVIEW TEST")
    print("==================================================")

    env_status = Config.validate()
    if not env_status.get("GEMINI_API_KEY"):
        print("[FAIL] GEMINI_API_KEY is missing or empty in .env file.")
        sys.exit(1)
    print("[OK] GEMINI_API_KEY detected")

    if not env_status.get("GITHUB_TOKEN"):
        print("[FAIL] GITHUB_TOKEN is missing or empty in .env file.")
        sys.exit(1)

    try:
        client = get_github_client()
        _ = client.get_user().login
        print("[OK] GitHub authentication successful")

        owner = "Niteshkumar-codes"
        repo_name = "ai-code-review-agent"

        commit_data = get_commit_changes(owner, repo_name)
        print("[OK] Commit diff retrieved")

        valid_patches = []
        for file_info in commit_data.get("files", []):
            patch = file_info.get("patch")
            if patch and patch != "Patch unavailable":
                file_patch = f"--- {file_info['filename']}\n+++ {file_info['filename']}\n{patch}"
                valid_patches.append(file_patch)

        if not valid_patches:
            print("[FAIL] No valid patch content available in the commit.")
            sys.exit(1)

        combined_diff = "\n\n".join(valid_patches)
        commit_sha = commit_data.get("sha", "unknown")[:7]
        commit_msg = commit_data.get("message", "").splitlines()[0]
        context_str = f"Commit {commit_sha}: {commit_msg}"

        print("[OK] Review input prepared")
        print("[OK] Sending diff to Gemini...")

        review_text = review_code_diff(diff=combined_diff, context=context_str)

        print("\n--------------------------------------------------")
        print("AI CODE REVIEW")
        print("--------------------------------------------------\n")
        print(review_text.strip())
        print("\n--------------------------------------------------")
        print("[SUCCESS] Single AI Code Review Verified!")
        print("==================================================")
        sys.exit(0)

    except ValueError as err:
        print(f"\n[FAIL] Configuration Error: {err}")
        sys.exit(1)
    except BadCredentialsException:
        print("\n[FAIL] GitHub Authentication Error: Invalid or expired GITHUB_TOKEN.")
        sys.exit(1)
    except UnknownObjectException:
        print("\n[FAIL] GitHub Resource Error: Repository or commit not found.")
        sys.exit(1)
    except GithubException as err:
        error_msg = err.data.get("message", str(err)) if isinstance(err.data, dict) else err.data
        print(f"\n[FAIL] GitHub API Error (Status Code {err.status}): {error_msg}")
        sys.exit(1)
    except RuntimeError as err:
        print(f"\n[FAIL] Code Review Error: {err}")
        sys.exit(1)
    except Exception as err:
        print(f"\n[FAIL] Unexpected Error: {type(err).__name__} - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
