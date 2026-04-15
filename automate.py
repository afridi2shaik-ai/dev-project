#!/usr/bin/env python3
"""
Sync a private source repository into a private target repository using git subtree.

Behavior:
- Clones the target repo
- Adds the source repo as a remote
- Fetches the source repo
- Adds the source repo under a prefix using git subtree --squash
- Pushes the result to the target repo

Recommended environment variables:
- SOURCE_GITHUB_TOKEN
- TARGET_GITHUB_TOKEN

Example local usage:
    export SOURCE_GITHUB_TOKEN=...
    export TARGET_GITHUB_TOKEN=...
    python sync_subtree.py
"""



from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

@dataclass
class Config:
    source_repo_https: str = "https://github.com/CloudBuildersOrg/Pipecat-Service.git"
    target_repo_https: str = "https://github.com/afridi2shaik-ai/dev-project.git"
    source_branch: str = "main"
    target_branch: str = "main"
    subtree_prefix: str = "pipecat"
    source_remote_name: str = "pipecat"


def run_cmd(cmd: list[str], cwd: str | None = None) -> None:
    """Run a shell command and raise if it fails."""
    print(f"\n>>> Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(cmd)}"
        )


def tokenized_url(repo_https_url: str, token: str) -> str:
    """
    Convert:
        https://github.com/owner/repo.git
    to:
        https://x-access-token:TOKEN@github.com/owner/repo.git
    """
    prefix = "https://"
    if not repo_https_url.startswith(prefix):
        raise ValueError(f"Expected https URL, got: {repo_https_url}")
    return f"https://x-access-token:{token}@{repo_https_url[len(prefix):]}"


def ensure_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    config = Config()

    try:
        source_token = ensure_env("SOURCE_GITHUB_TOKEN")
        target_token = ensure_env("TARGET_GITHUB_TOKEN")
    except EnvironmentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    target_url = tokenized_url(config.target_repo_https, target_token)
    source_url = tokenized_url(config.source_repo_https, source_token)

    workdir = tempfile.mkdtemp(prefix="repo-sync-")
    repo_dir = os.path.join(workdir, "target-repo")

    print(f"Temporary workdir: {workdir}")

    try:
        # Clone target repo
        run_cmd(["git", "clone", "--branch", config.target_branch, target_url, repo_dir])

        # Set identity in case a commit is created by subtree
        run_cmd(["git", "config", "user.name", "Repo Sync Bot"], cwd=repo_dir)
        run_cmd(["git", "config", "user.email", "repo-sync-bot@example.com"], cwd=repo_dir)

        # Add source remote
        run_cmd(
            ["git", "remote", "add", config.source_remote_name, source_url],
            cwd=repo_dir,
        )

        # Fetch source branch
        run_cmd(
            ["git", "fetch", config.source_remote_name, config.source_branch],
            cwd=repo_dir,
        )

        # Check if prefix already exists
        prefix_path = os.path.join(repo_dir, config.subtree_prefix)
        prefix_exists = os.path.exists(prefix_path)

        if prefix_exists:
            print(
                f"\nPrefix '{config.subtree_prefix}' already exists. "
                f"Using 'git subtree pull' instead of 'add'."
            )
            run_cmd(
                [
                    "git",
                    "subtree",
                    "pull",
                    "--prefix",
                    config.subtree_prefix,
                    config.source_remote_name,
                    config.source_branch,
                    "--squash",
                ],
                cwd=repo_dir,
            )
        else:
            print(
                f"\nPrefix '{config.subtree_prefix}' does not exist. "
                f"Using 'git subtree add'."
            )
            run_cmd(
                [
                    "git",
                    "subtree",
                    "add",
                    "--prefix",
                    config.subtree_prefix,
                    config.source_remote_name,
                    config.source_branch,
                    "--squash",
                ],
                cwd=repo_dir,
            )

        # Push to target
        run_cmd(["git", "push", "origin", config.target_branch], cwd=repo_dir)

        print("\nSuccess: source repo content synced into target repo.")
        return 0

    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    finally:
        # Comment this out if you want to inspect the cloned repo after running
        shutil.rmtree(workdir, ignore_errors=True)

if __name__ == "__main__":
    raise SystemExit(main())
