"""Typed schema and deterministic binding; the model supplies prose only."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import MODEL, PROMPT_VERSION
from .evidence import extract
from .git import CATALOG, Snapshot, git

Text = Annotated[str, Field(min_length=1, max_length=3000)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Copy(Strict):
    title: Text
    summary: Text
    limitations: Text

    @field_validator("title", "summary", "limitations")
    @classmethod
    def plain_text(cls, value: str) -> str:
        # Model prose is rendered as text; it cannot inject Markdown/HTML/links.
        if not value.strip() or any(c in value for c in "\r\n<>[]`\\"):
            raise ValueError("Expected one line of plain prose without links or HTML")
        return value

class Node(Strict):
    id: Text
    version: Text


class Chain(Strict):
    task: Text
    language: Text
    metric: Text
    pipeline_id: Text
    nodes: Annotated[list[Node], Field(min_length=1)]


class Support(Strict):
    tasks: Annotated[list[Text], Field(min_length=1)]
    metrics: Annotated[list[Text], Field(min_length=1)]
    pipeline_ids: Annotated[list[Text], Field(min_length=1)]


class Links(Strict):
    docs: Annotated[list[Text], Field(min_length=1)]
    catalog: Literal["docs/pipeline_catalog.jsonl"]
    source_change: Text
    related_changes: list[Text] = Field(default_factory=list)
    tests: list[Text] = Field(default_factory=list)


class Evidence(Strict):
    source_commit: Annotated[str, Field(pattern=r"^[a-f0-9]{40,64}$")]
    source_files: Annotated[list[Text], Field(min_length=1)]
    file_digests: dict[str, str]
    model: Literal["k3.1-pro"]
    prompt_version: Literal["news_v1"]
    copy_origin: Literal["model", "manual"]
    test_result: Text


class LocalizedCopy(Copy):
    brief: Text


class Entry(Copy):
    zh: LocalizedCopy | None = None
    pipeline_brief: Text | None = None
    id: Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    revision: Annotated[int, Field(ge=1)] = 1
    supersedes: str | None = None
    status: Literal["supported"] = "supported"
    published_at: date
    support: Support
    chain: Annotated[list[Chain], Field(min_length=1)]
    links: Links
    evidence: Evidence


def make_entry(frozen: dict, copy: Copy, *, repository: str, entry_id: str,
               published_at: date, manual: bool = False) -> Entry:
    chains = frozen["chains"]
    return Entry(
        **copy.model_dump(), id=entry_id, published_at=published_at,
        support={"tasks": sorted({c["task"] for c in chains}),
                 "metrics": sorted({c["metric"] for c in chains}),
                 "pipeline_ids": [c["pipeline_id"] for c in chains]},
        chain=chains,
        links={"docs": frozen["docs"], "catalog": CATALOG,
               "source_change": f"https://github.com/{repository}/commit/{frozen['source_commit']}"},
        evidence={"source_commit": frozen["source_commit"],
                  "source_files": frozen["source_files"], "file_digests": frozen["file_digests"],
                  "model": MODEL, "prompt_version": PROMPT_VERSION,
                  "copy_origin": "manual" if manual else "model",
                  "test_result": "Not run by news-agent; see source tests and commit checks."})


def validate_entry(entry: Entry, root: Path, repository: str) -> None:
    snapshot = Snapshot(root, entry.evidence.source_commit)
    facts = extract(snapshot, entry.support.pipeline_ids)
    if [c.model_dump() for c in entry.chain] != facts["chains"]:
        raise ValueError(f"Node chain or version differs from source: {entry.id}")
    if (entry.support.tasks != sorted({c["task"] for c in facts["chains"]})
            or entry.support.metrics != sorted({c["metric"] for c in facts["chains"]})
            or entry.links.docs != facts["docs"]
            or entry.evidence.source_files != facts["source_files"]
            or entry.evidence.file_digests != facts["file_digests"]):
        raise ValueError(f"Entry facts differ from frozen evidence: {entry.id}")
    if entry.links.source_change != f"https://github.com/{repository}/commit/{snapshot.sha}":
        raise ValueError("Source commit link disagrees with evidence")
    for link in entry.links.related_changes:
        prefix = f"https://github.com/{repository}/commit/"
        if not link.startswith(prefix) or not re.fullmatch(r"[0-9a-f]{40,64}", link[len(prefix):]):
            raise ValueError("Related changes must link to repository commits")
        related = Snapshot(root, link[len(prefix):])
        if git(root, "merge-base", related.sha, snapshot.sha).strip() != related.sha:
            raise ValueError("Related change is not part of the source history")
    for path in [*entry.links.docs, entry.links.catalog, *entry.links.tests]:
        snapshot.read(path)
    if "ear1" in " ".join(entry.support.pipeline_ids):
        if re.search(r"ear[- ]?v1", entry.model_dump_json(), re.IGNORECASE):
            raise ValueError("EAR-1 must not be called EAR-v1")


def load_entries(root: Path, repository: str) -> list[Entry]:
    entries = []
    for path in sorted((root / "docs/news/entries").glob("*.yaml")):
        if path.is_symlink():
            raise ValueError(f"Symlink entry is not allowed: {path}")
        entry = Entry.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if path.stem != entry.id:
            raise ValueError("Entry filename must match its ID")
        validate_entry(entry, root, repository)
        entries.append(entry)
    ids = {e.id for e in entries}
    if len(ids) != len(entries):
        raise ValueError("Duplicate entry IDs")
    for entry in entries:
        if ((entry.revision == 1 and entry.supersedes is not None)
                or (entry.revision > 1 and (entry.supersedes not in ids
                    or entry.supersedes == entry.id))):
            raise ValueError("Revisions must retain and supersede an existing entry")
    return sorted(entries, key=lambda e: (e.published_at, e.id), reverse=True)
