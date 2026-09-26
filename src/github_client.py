from typing import Any
from github import Auth, Github, Repository
from src.config import Config


def get_github_client() -> Github:
    if not Config.GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN is missing or empty in configuration.")
    auth = Auth.Token(Config.GITHUB_TOKEN)
    return Github(auth=auth)


def get_repository(owner: str, repo_name: str) -> Repository.Repository:
    client = get_github_client()
    return client.get_repo(f"{owner}/{repo_name}")


def get_repository_metadata(owner: str, repo_name: str) -> dict[str, Any]:
    repo = get_repository(owner, repo_name)
    description = repo.description if repo.description is not None else "No description provided."
    visibility = "private" if repo.private else "public"

    return {
        "full_name": repo.full_name,
        "description": description,
        "default_branch": repo.default_branch,
        "visibility": visibility,
        "html_url": repo.html_url,
        "stars": repo.stargazers_count,
        "forks": repo.forks_count,
    }


def get_commit_changes(
    owner: str, repo_name: str, commit_sha: str | None = None
) -> dict[str, Any]:
    repo = get_repository(owner, repo_name)
    if commit_sha:
        commit = repo.get_commit(commit_sha)
    else:
        commit = repo.get_commits()[0]

    files_data = []
    if commit.files:
        for file in commit.files:
            files_data.append(
                {
                    "filename": file.filename,
                    "status": file.status,
                    "additions": file.additions,
                    "deletions": file.deletions,
                    "changes": file.changes,
                    "patch": file.patch if file.patch is not None else "Patch unavailable",
                }
            )

    return {
        "sha": commit.sha,
        "message": commit.commit.message,
        "files": files_data,
    }
