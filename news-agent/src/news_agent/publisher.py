"""Validate all output before staging previews or isolated documentation commits."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from .config import Config
from .git import Snapshot, git, safe_path
from .renderer import END, START, diff, outside_block


def allowed(path: str) -> bool:
    safe_path(path)
    entry_id = r"[a-z0-9]+(?:-[a-z0-9]+)*"
    if re.fullmatch(rf"docs/news/(?:cards/{entry_id}\.svg|entries/{entry_id}\.yaml)", path):
        return True
    return path in {
        "README.md", "docs/news/index.md", "docs/news/latest.md",
        "docs/news/index.html", "docs/news/banner.svg",
    }


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets: list[str] = []
        self.ids: list[str] = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if value is not None and key in {"href", "src"}:
                self.targets.append(value)
            if value is not None and key == "id":
                self.ids.append(value)


def validate_output(before: dict[str, str], after: dict[str, str], exists, *, pages_url: str | None = None) -> None:
    for path, content in after.items():
        if not allowed(path):
            raise ValueError(f"Publisher cannot write {path}")
        if path.startswith("docs/news/entries/") and path in before and before[path] != content:
            raise ValueError("Published entries are immutable; create a revision")
        if path == "README.md":
            if outside_block(before[path]) != outside_block(content):
                raise ValueError("README changes escape the SURE-NEWS block")
            checked = content[content.index(START):content.index(END)]
        else:
            checked = content if path.endswith((".md", ".html", ".svg")) else ""
        if checked.count("```") % 2:
            raise ValueError(f"Unclosed Markdown fence: {path}")
        page = PageLinks()
        page.feed(checked)
        if len(page.ids) != len(set(page.ids)):
            raise ValueError(f"Duplicate page anchors: {path}")
        targets = page.targets + re.findall(r"\]\(([^\s)]+)\)", checked)
        for target in targets:
            parts = urlsplit(target)
            if pages_url and parts._replace(fragment="").geturl() == pages_url:
                if parts.fragment:
                    anchors = PageLinks()
                    anchors.feed(after["docs/news/index.html"])
                    if parts.fragment not in anchors.ids:
                        raise ValueError(f"Broken announcement anchor: {target}")
                continue
            if parts.scheme:
                if parts.scheme != "https" or parts.netloc != "github.com":
                    raise ValueError(f"Unexpected external announcement link: {target}")
                continue
            resolved = (os.path.normpath(str(PurePosixPath(path).parent / unquote(parts.path)))
                        if parts.path else path)
            safe_path(resolved)
            if resolved not in after and not exists(resolved):
                raise ValueError(f"Broken local link in {path}: {target}")
            if parts.fragment and resolved in after:
                anchors = PageLinks()
                anchors.feed(after[resolved])
                if parts.fragment not in anchors.ids:
                    raise ValueError(f"Broken announcement anchor: {target}")
    ids = re.findall(r'<a id="([^"]+)"', after["docs/news/index.md"])
    if len(set(ids)) != len(ids):
        raise ValueError("English history must contain unique IDs")


def local_write(root: Path, output: dict[str, str]) -> None:
    # Reject filesystem symlinks before making any mutation.
    for path in output:
        target = root / safe_path(path)
        if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Unsafe output path: {path}")
    for path, content in output.items():
        target = root / path
        if target.is_file() and target.read_text(encoding="utf-8") == content:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".news-agent-tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(target)


def preview(directory: Path, before: dict[str, str], output: dict[str, str]) -> Path:
    directory.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".news-preview-", dir=directory.parent))
    try:
        local_write(staged, output)
        (staged / "preview.diff").write_text(diff(before, output), encoding="utf-8")
        if directory.exists():
            # Reusing the same job must produce exactly the same complete preview.
            expected = {p.relative_to(staged): p.read_bytes() for p in staged.rglob("*") if p.is_file()}
            actual = {p.relative_to(directory): p.read_bytes()
                      for p in directory.rglob("*") if p.is_file()}
            if expected != actual:
                raise ValueError("Preview already exists with different content; use a new output directory")
        else:
            staged.rename(directory)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return directory


def gh(*args: str, root: Path) -> str:
    result = subprocess.run(["gh", *args], cwd=root, text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"gh {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def publish(config: Config, head: Snapshot, key: str, output: dict[str, str]) -> str:
    if config.mode == "dry-run":
        raise ValueError("dry-run cannot enter the remote publisher")
    before = {path: head.read(path) for path in output if head.exists(path)}
    validate_output(before, output, head.exists, pages_url=config.pages_url)
    branch = "news-agent/" + key[:20]
    # Recover a PR created before a state write failed.
    if config.mode == "pr":
        prs = json.loads(gh("pr", "list", "--repo", config.repository, "--head", branch,
                            "--state", "all", "--json", "url,baseRefName,state,mergedAt",
                            root=config.checkout))
        if prs:
            if len(prs) != 1 or prs[0]["baseRefName"] != config.base_branch:
                raise ValueError("Existing news PR has an unexpected base")
            if prs[0]["state"] == "CLOSED" and not prs[0]["mergedAt"]:
                raise ValueError("The news PR was closed without merging; maintainer review is required")
            return prs[0]["url"]
    worktrees = config.state_dir / "worktrees"
    worktrees.mkdir(parents=True, exist_ok=True)
    worktree = Path(tempfile.mkdtemp(prefix="news-", dir=worktrees))
    worktree.rmdir()
    git(config.checkout, "worktree", "add", "--detach", str(worktree), head.sha)
    try:
        local_write(worktree, output)
        git(worktree, "add", "--", *sorted(output))
        changed = git(worktree, "diff", "--cached", "--name-only").splitlines()
        if not changed:
            return "No documentation changes"
        if any(not allowed(path) for path in changed):
            raise ValueError("Commit includes files outside the documentation allowlist")
        git(worktree, "-c", "user.name=SURE News Agent", "-c", "user.email=news-agent@localhost",
            "-c", "core.hooksPath=/dev/null", "commit", "-m", "docs: announce evaluation support")
        commit = git(worktree, "rev-parse", "HEAD").strip()
        # A deterministic branch prevents duplicate publication. Never force push.
        remote_ref = git(worktree, "ls-remote", config.remote, "refs/heads/" + branch).split()
        if remote_ref:
            git(worktree, "fetch", "--no-tags", config.remote, "refs/heads/" + branch)
            if git(worktree, "rev-parse", "FETCH_HEAD^{tree}") != git(worktree, "rev-parse", "HEAD^{tree}"):
                raise ValueError("Remote news branch differs from this frozen publication")
        else:
            git(worktree, "push", config.remote, commit + ":refs/heads/" + branch)
        if config.mode == "docs-commit":
            return f"https://github.com/{config.repository}/tree/{branch}"
        body = config.state_dir / (key + ".pr-body.md")
        body.write_text(
            "Announces newly registered evaluation pipelines with catalog IDs, ordered nodes, "
            "task documentation and frozen source evidence.\n\n"
            f"Source commit: {head.sha}\n\n"
            "Validation: entry schema, source manifests, route/catalog consistency, English "
            "entry IDs, local links and README block boundaries. "
            "Evaluation tests are linked where available; news-agent does not claim a test run.\n",
            encoding="utf-8")
        return gh("pr", "create", "--repo", config.repository, "--base", config.base_branch,
                  "--head", branch, "--title", "docs: announce evaluation support",
                  "--body-file", str(body), root=worktree)
    finally:
        git(config.checkout, "worktree", "remove", "--force", str(worktree))
