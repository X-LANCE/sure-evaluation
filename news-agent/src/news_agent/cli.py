from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

import yaml

from . import MODEL, PROMPT_VERSION
from .config import default_pages_url, load_config
from .contract import Copy, Entry, load_entries, make_entry, validate_entry
from .detector import feature_changes
from .git import Snapshot, git
from .kimi_client import KimiClient
from .publisher import local_write, preview, publish, validate_output
from .renderer import render
from .state import State, job_key, locked


def dump_entry(entry: Entry) -> str:
    return yaml.safe_dump(entry.model_dump(mode="json"), allow_unicode=True, sort_keys=False)


def committed_entries(root: Path, snapshot: Snapshot, repository: str) -> list[Entry]:
    names = git(root, "ls-tree", "-r", "--name-only", snapshot.sha,
                "--", "docs/news/entries/").splitlines()
    entries = []
    for path in names:
        if not path.endswith(".yaml"):
            continue
        item = Entry.model_validate(yaml.safe_load(snapshot.read(path)))
        if Path(path).stem != item.id:
            raise ValueError("Entry filename must match its ID")
        validate_entry(item, root, repository)
        entries.append(item)
    return entries


def prepare(root: Path, repository: str, *, snapshot: Snapshot | None = None,
            entry: Entry | None = None,
            preview_from_working_tree: bool = False, site_repository: str | None = None,
            pages_url: str | None = None) -> tuple[dict, dict]:
    # Polling normally reads committed publication data. An explicit dry-run
    # setting also permits isolated local templates before those templates merge.
    if snapshot and not preview_from_working_tree:
        entries = committed_entries(root, snapshot, repository)
        read = snapshot.read
        exists = snapshot.exists
    else:
        entries = load_entries(root, repository)

        def read(path):
            local = root / path
            if local.is_file() or not snapshot:
                return local.read_text(encoding="utf-8")
            return snapshot.read(path)

        def exists(path):
            return (root / path).is_file() or bool(snapshot and snapshot.exists(path))
    if entry:
        validate_entry(entry, root, repository)
        prior = next((e for e in entries if e.id == entry.id), None)
        if prior and prior != entry:
            raise ValueError("Cannot overwrite a published entry; create a revision")
        if not prior:
            entries.append(entry)
    site_repository = site_repository or repository
    pages_url = pages_url or default_pages_url(site_repository)
    output = render(entries, read("README.md"), source_root=root,
                    site_repository=site_repository, pages_url=pages_url)
    if entry:
        output[f"docs/news/entries/{entry.id}.yaml"] = dump_entry(entry)
    before = {p: read(p) for p in output if exists(p)}
    validate_output(before, output, exists, pages_url=pages_url)
    return before, output


def run_cycle(config, *, since: str | None = None, copy_file: Path | None = None) -> dict:
    if config.preview_from_working_tree and config.mode != "dry-run":
        raise ValueError("Working-tree announcement templates are only allowed in dry-run mode")
    if copy_file and config.mode != "dry-run":
        raise ValueError("Offline copy fixtures are only accepted in dry-run mode")
    with locked(config.state_dir):
        state = State(config.state_dir)
        try:
            if config.fetch:
                git(config.checkout, "fetch", "--no-tags", config.remote,
                    f"refs/heads/{config.base_branch}:refs/remotes/{config.remote}/{config.base_branch}")
            head = Snapshot(config.checkout, config.ref)
            scope = config.repository + ":" + config.base_branch
            cursor = since or state.cursor(scope)
            if cursor is None:
                state.advance(scope, head.sha)
                return {"status": "initialized", "cursor": head.sha,
                        "note": "No historical news generated; use --since for an explicit backfill."}
            if since and state.cursor(scope) is None:
                # Retain the explicit starting point if the first backfill fails,
                # so an ordinary next run retries rather than initializing ahead.
                state.advance(scope, Snapshot(config.checkout, since).sha)
            base = Snapshot(config.checkout, cursor)
            if base.sha != head.sha:
                entries = (load_entries(config.checkout, config.repository)
                           if config.preview_from_working_tree else
                           committed_entries(config.checkout, head, config.repository))
                announced = {p for entry in entries
                             for p in entry.support.pipeline_ids}
                announced.update(state.queued_pipeline_ids(scope))
                for frozen in feature_changes(base, head, announced):
                    from importlib.resources import files
                    frozen["prompt"] = files("news_agent").joinpath(
                        f"prompts/{PROMPT_VERSION}.md").read_text(encoding="utf-8")
                    key = job_key(config.repository, config.base_branch, frozen)
                    state.enqueue(key, scope, frozen)
            completed = []
            for job in state.pending(scope, config.mode):
                key = job["key"]
                try:
                    frozen = json.loads(job["evidence"])
                    manual = job["copy_origin"] == "manual" if job["copy"] else bool(copy_file)
                    if manual and config.mode != "dry-run":
                        raise ValueError("An offline prose fixture cannot be promoted to remote publication")
                    if job["copy"]:
                        copy = Copy.model_validate_json(job["copy"])
                    else:
                        copy = (Copy.model_validate_json(copy_file.read_text(encoding="utf-8"))
                                if copy_file else KimiClient(config).generate(frozen))
                        state.cache_copy(key, copy.model_dump(), manual=manual)
                    source = Snapshot(config.checkout, frozen["source_commit"])
                    published = date.fromisoformat(git(config.checkout, "show", "-s",
                                                      "--format=%cs", source.sha).strip())
                    entry = make_entry(frozen, copy, repository=config.repository,
                                       entry_id="support-" + key[:16], published_at=published,
                                       manual=manual)
                    # Rebase the presentation onto the current head so pending
                    # jobs include other announcements merged in the meantime.
                    before, output = prepare(config.checkout, config.repository,
                                             snapshot=head, entry=entry,
                                             preview_from_working_tree=config.preview_from_working_tree,
                                             site_repository=config.site_repository,
                                             pages_url=config.site_url)
                    if config.mode == "dry-run":
                        result = str(preview(config.state_dir / "previews" / key, before, output))
                        status = "preview"
                    else:
                        result = publish(config, head, key, output)
                        status = "published"
                    state.finish(key, status, result)
                    completed.append({"key": key, "status": status, "result": result})
                except Exception as exc:
                    state.fail(key, str(exc))
                    raise
            state.advance(scope, head.sha)
            return {"status": "ok", "cursor": head.sha, "completed": completed}
        finally:
            state.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Independent SURE evaluation news agent")
    parser.add_argument("--config", type=Path,
                        default=Path(__file__).resolve().parents[2] / "config.yaml.example")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run one polling cycle; dry-run by default")
    run.add_argument("--since", help="Explicit historical base commit (otherwise saved cursor)")
    run.add_argument("--mode", choices=["dry-run", "pr", "docs-commit"])
    run.add_argument("--copy-file", type=Path, help="Offline JSON prose fixture; dry-run only")
    draw = sub.add_parser("render", help="Validate existing entries and render working-tree pages")
    draw.add_argument("--write", action="store_true", help="Update local documentation")
    draw.add_argument("--output", type=Path, help="Preview directory (default under own state)")
    sub.add_parser("check", help="Validate facts, links and generated-page freshness")
    sub.add_parser("status", help="Show own cursors, queue and errors")
    sub.add_parser("poll-personal", help="Review upstream main with Kimi and publish to the personal fork")
    doctor = sub.add_parser("doctor", help="Read-only local diagnostics")
    doctor.add_argument("--smoke", action="store_true", help="Call real Kimi once; write no announcements")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        config.log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=config.log_dir / "news-agent.log", level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
        if args.command == "run":
            if args.mode:
                config.mode = args.mode
            result = run_cycle(config, since=args.since, copy_file=args.copy_file)
        elif args.command == "poll-personal":
            from .personal import poll
            result = poll(config)
        elif args.command == "status":
            with locked(config.state_dir):
                state = State(config.state_dir)
                try:
                    result = state.diagnostics()
                finally:
                    state.close()
        elif args.command == "doctor":
            import os
            head = Snapshot(config.checkout, config.ref)
            result = {"head": head.sha, "model": MODEL, "mode": config.mode,
                      "state_dir": str(config.state_dir), "log_dir": str(config.log_dir),
                      "credential_configured": bool(os.environ.get("NEWS_AGENT_KIMI_API_KEY"))}
            if args.smoke:
                from .evidence import extract
                entries = load_entries(config.checkout, config.repository)
                if not entries:
                    raise ValueError("A validated entry is required as the smoke evidence fixture")
                frozen = extract(Snapshot(config.checkout, entries[0].evidence.source_commit),
                                 entries[0].support.pipeline_ids)
                result["smoke"] = KimiClient(config).generate(frozen).model_dump()
        else:
            before, output = prepare(config.checkout, config.repository,
                                     site_repository=config.site_repository, pages_url=config.site_url)
            if args.command == "check":
                stale = [p for p, content in output.items() if before.get(p) != content]
                if stale:
                    raise ValueError("Generated files are stale: " + ", ".join(stale))
                result = {"status": "ok", "generated_files": len(output)}
            elif args.write:
                local_write(config.checkout, output)
                result = {"status": "written", "files": sorted(output)}
            else:
                result = {"status": "preview", "output": str(preview(
                    args.output or config.state_dir / "render-preview", before, output))}
        logging.info("%s %s", args.command, json.dumps(result, ensure_ascii=False))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        logging.error("%s failed: %s", args.command, exc)
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
