"""Read immutable Git objects without changing the user's checkout."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

CATALOG = "docs/pipeline_catalog.jsonl"


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=120
    )
    if result.returncode:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def safe_path(path: str) -> str:
    parts = PurePosixPath(path)
    if parts.is_absolute() or ".." in parts.parts or "\\" in path or not path:
        raise ValueError(f"Invalid repository path: {path}")
    return path


class Snapshot:
    def __init__(self, root: Path, ref: str):
        self.root = root.resolve()
        self.sha = git(self.root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", self.sha):
            raise ValueError("Expected a full commit SHA")

    def read(self, path: str) -> str:
        path = safe_path(path)
        # Reject symlinks and submodules in evidence, including intermediate directories.
        for index in range(1, len(PurePosixPath(path).parts) + 1):
            prefix = "/".join(PurePosixPath(path).parts[:index])
            info = git(self.root, "ls-tree", self.sha, "--", prefix)
            if not info or info.split()[0] not in {"100644", "100755", "040000"}:
                raise ValueError(f"Missing or unsafe source path: {path}")
        return git(self.root, "show", f"{self.sha}:{path}")

    def exists(self, path: str) -> bool:
        try:
            self.read(path)
            return True
        except (ValueError, RuntimeError):
            return False
