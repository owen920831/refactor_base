"""Git manager for branch isolation and rollback.

Provides git operations for safe refactoring with rollback capability.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GitStatus:
    """Current git status."""

    branch: str
    is_clean: bool
    modified_files: list[str]
    has_stash: bool


class GitManager:
    """Manages git operations for safe refactoring.

    Provides branch creation, commits, stash, and rollback.
    """

    def __init__(self, repo_path: str | Path) -> None:
        """Initialize the git manager.

        Args:
            repo_path: Path to the git repository.
        """
        self.repo_path = Path(repo_path)
        self._ensure_git_repo()

    def _ensure_git_repo(self) -> None:
        """Ensure the path is a git repository."""
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            logger.info("Initializing git repository at %s", self.repo_path)
            self._run_git(["init"])

    def _run_git(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command.

        Args:
            args: Git command arguments.
            check: Whether to raise on non-zero return code.

        Returns:
            CompletedProcess result.
        """
        return subprocess.run(
            ["git"] + args,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
        )

    def get_status(self) -> GitStatus:
        """Get current git status.

        Returns:
            GitStatus with current branch and status.
        """
        # Get current branch
        branch_result = self._run_git(["branch", "--show-current"], check=False)
        branch = branch_result.stdout.strip() or "main"

        # Check if clean
        status_result = self._run_git(["status", "--porcelain"], check=False)
        modified_files = [
            line.split()[-1]
            for line in status_result.stdout.strip().split("\n")
            if line
        ]
        is_clean = len(modified_files) == 0

        # Check for stash
        stash_result = self._run_git(["stash", "list"], check=False)
        has_stash = bool(stash_result.stdout.strip())

        return GitStatus(
            branch=branch,
            is_clean=is_clean,
            modified_files=modified_files,
            has_stash=has_stash,
        )

    def create_branch(self, branch_name: str | None = None) -> str:
        """Create a new branch for refactoring.

        Args:
            branch_name: Optional branch name. Auto-generated if not provided.

        Returns:
            The created branch name.
        """
        if branch_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            branch_name = f"agent/refactor-session-{timestamp}"

        try:
            self._run_git(["checkout", "-b", branch_name])
            logger.info("Created and switched to branch: %s", branch_name)
            return branch_name
        except subprocess.CalledProcessError as e:
            logger.error("Failed to create branch: %s", e.stderr)
            raise

    def commit(self, message: str, files: list[str] | None = None) -> bool:
        """Create a commit.

        Args:
            message: Commit message.
            files: Optional list of files to add. Adds all if None.

        Returns:
            True if commit succeeded.
        """
        try:
            if files:
                for f in files:
                    self._run_git(["add", f])
            else:
                self._run_git(["add", "-A"])

            self._run_git(["commit", "-m", message])
            logger.info("Committed: %s", message)
            return True

        except subprocess.CalledProcessError as e:
            logger.warning("Commit failed: %s", e.stderr)
            return False

    def stash(self, message: str = "Auto-stash by agent") -> bool:
        """Stash current changes.

        Args:
            message: Stash message.

        Returns:
            True if stash succeeded.
        """
        try:
            self._run_git(["stash", "push", "-m", message])
            logger.info("Stashed changes: %s", message)
            return True
        except subprocess.CalledProcessError as e:
            logger.warning("Stash failed: %s", e.stderr)
            return False

    def stash_pop(self) -> bool:
        """Pop the latest stash.

        Returns:
            True if pop succeeded.
        """
        try:
            self._run_git(["stash", "pop"])
            logger.info("Popped stash")
            return True
        except subprocess.CalledProcessError as e:
            logger.warning("Stash pop failed: %s", e.stderr)
            return False

    def rollback(self) -> bool:
        """Rollback all uncommitted changes.

        Returns:
            True if rollback succeeded.
        """
        try:
            self._run_git(["checkout", "."])
            self._run_git(["clean", "-fd"])
            logger.info("Rolled back all changes")
            return True
        except subprocess.CalledProcessError as e:
            logger.warning("Rollback failed: %s", e.stderr)
            return False

    def rollback_last_commit(self) -> bool:
        """Rollback the last commit but keep changes staged.

        Returns:
            True if rollback succeeded.
        """
        try:
            self._run_git(["reset", "--soft", "HEAD~1"])
            logger.info("Rolled back last commit")
            return True
        except subprocess.CalledProcessError as e:
            logger.warning("Rollback last commit failed: %s", e.stderr)
            return False

    def create_checkpoint(self, label: str) -> bool:
        """Create a checkpoints (lightweight git tag)."""
        try:
             # Force overwrite tag if exists to act as a movable pointer if needed, 
             # but usually unique labels are better.
            self._run_git(["tag", "-f", label])
            logger.info(f"Created checkpoint: {label}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create checkpoint {label}: {e.stderr}")
            return False

    def rollback_to_checkpoint(self, label: str) -> bool:
        """Hard reset to a specific checkpoint."""
        try:
            self._run_git(["reset", "--hard", label])
            # Optional: Clean untracked files too
            self._run_git(["clean", "-fd"])
            logger.info(f"Rolled back to checkpoint: {label}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to rollback to {label}: {e.stderr}")
            return False
