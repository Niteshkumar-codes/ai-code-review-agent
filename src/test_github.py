from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from github import BadCredentialsException, GithubException, UnknownObjectException
from src.config import Config
from src.github_client import get_commit_changes, get_github_client, get_repository


def main() -> None:
    print("==================================================")
    print(" PHASE 4: COMMIT DIFF EXTRACTION TEST")
    print("==================================================")

    env_status = Config.validate()
    if not env_status.get("GITHUB_TOKEN"):
        print("[FAIL] GITHUB_TOKEN is missing or empty in .env file.")
        sys.exit(1)

    print("[OK] GITHUB_TOKEN detected")

    try:
        client = get_github_client()
        _ = client.get_user().login
        print("[OK] GitHub authentication successful")

        owner = "Niteshkumar-codes"
        repo_name = "ai-code-review-agent"

        _ = get_repository(owner, repo_name)
        print("[OK] Repository accessed")
        print()

        commit_data = get_commit_changes(owner, repo_name)
        short_sha = commit_data["sha"][:7]
        commit_message = commit_data["message"].splitlines()[0]

        print("Commit:")
        print(f"  SHA: {short_sha}")
        print(f"  Message: {commit_message}")
        print()

        print("Changed Files:")
        for idx, file_info in enumerate(commit_data["files"], start=1):
            print(f"  {idx}. {file_info['filename']}")
            print(f"     Status: {file_info['status']}")
            print(f"     Additions: {file_info['additions']}")
            print(f"     Deletions: {file_info['deletions']}")
            print(f"     Changes: {file_info['changes']}")
            print("     Patch:")
            patch_content = file_info["patch"]
            if patch_content and patch_content != "Patch unavailable":
                indented_patch = "\n".join(
                    f"       {line}" for line in patch_content.splitlines()
                )
                print(indented_patch)
            else:
                print(f"       {patch_content}")
            print()

        print("--------------------------------------------------")
        print("[SUCCESS] Commit Diff Extraction Verified!")
        print("==================================================")
        sys.exit(0)

    except ValueError as err:
        print(f"\n[FAIL] Configuration Error: {err}")
        sys.exit(1)
    except BadCredentialsException:
        print("\n[FAIL] GitHub Authentication Error: Invalid or expired GITHUB_TOKEN.")
        sys.exit(1)
    except UnknownObjectException:
        print(
            "\n[FAIL] GitHub Resource Error: Repository or commit not found, or access denied."
        )
        sys.exit(1)
    except GithubException as err:
        error_msg = err.data.get("message", str(err)) if isinstance(err.data, dict) else err.data
        print(f"\n[FAIL] GitHub API Error (Status Code {err.status}): {error_msg}")
        sys.exit(1)
    except Exception as err:
        print(f"\n[FAIL] Unexpected Error: {type(err).__name__} - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
