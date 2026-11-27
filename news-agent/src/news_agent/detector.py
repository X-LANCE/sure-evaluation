"""Only newly registered, usable atomic pipelines qualify as support news."""

from __future__ import annotations

from .evidence import catalog, extract
from .git import CATALOG, Snapshot, git


def detect(base: Snapshot, head: Snapshot, include: set[str] | None = None) -> dict | None:
    # A rewritten branch must be examined explicitly, never silently rebased.
    if git(head.root, "merge-base", base.sha, head.sha).strip() != base.sha:
        raise ValueError("Cursor is not an ancestor of head; choose an explicit --since")
    previous, current = catalog(base), catalog(head)
    ids = sorted(key for key, row in current.items()
                 if key not in previous and row["pipeline_kind"] == "atomic"
                 and (include is None or key in include))
    if not ids:
        return None
    evidence = extract(head, ids)
    evidence["base_commit"] = base.sha
    evidence["changed_files"] = git(
        head.root, "diff", "--name-only", base.sha, head.sha
    ).splitlines()
    paths = sorted({"docs/pipeline_catalog.jsonl", *evidence["source_files"]})
    # Truncation is explicit; the authoritative manifests/catalog are frozen in full.
    diff = git(head.root, "diff", "--no-ext-diff", "--no-textconv", base.sha, head.sha,
               "--", *paths)
    evidence["diff"] = diff[:24000]
    evidence["diff_truncated"] = len(diff) > 24000
    evidence["commits"] = git(head.root, "log", "--format=%H %s",
                               f"{base.sha}..{head.sha}").splitlines()
    return evidence


def feature_changes(base: Snapshot, head: Snapshot, announced: set[str]):
    if git(head.root, "merge-base", base.sha, head.sha).strip() != base.sha:
        raise ValueError("Cursor is not an ancestor of head; choose an explicit --since")
    pending = set(catalog(head)) - set(catalog(base)) - announced
    if not pending:
        return
    commits = git(head.root, "log", "--first-parent", "--reverse", "--format=%H",
                  f"{base.sha}..{head.sha}", "--", CATALOG).splitlines()
    for sha in commits:
        feature = detect(Snapshot(head.root, sha + "^1"), Snapshot(head.root, sha), pending)
        if feature:
            pending.difference_update(c["pipeline_id"] for c in feature["chains"])
            yield feature
