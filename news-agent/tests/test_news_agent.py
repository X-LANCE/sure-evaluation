from __future__ import annotations

import copy as copying
import io
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
import yaml
from pydantic import ValidationError

from news_agent import MODEL
from news_agent.cli import prepare, run_cycle
from news_agent.config import Config, load_config
from news_agent.contract import Copy, Entry, load_entries, make_entry, validate_entry
from news_agent.detector import detect, feature_changes
from news_agent.evidence import extract
from news_agent.git import Snapshot, git
from news_agent.kimi_client import KimiClient, read_stream
from news_agent.publisher import allowed, local_write, preview, publish, validate_output
from news_agent.renderer import END, START, outside_block, render, replace_block
from news_agent.state import State, job_key, locked
from news_agent.web import PR_NUMBERS, pr_url, render_page, resolve_pr_numbers

from news_test_helpers import AGENT, IDS, ROOT, commit


def entry_for(facts, copy):
    return make_entry(facts, copy, repository="PigeonDan1/sure-evaluation", entry_id="ear-1",
                      published_at=date(2026, 11, 18), manual=True)


def test_ear1_catalog_routes_and_node_versions(facts):
    assert [c["pipeline_id"] for c in facts["chains"]] == IDS
    assert [c["metric"] for c in facts["chains"]] == ["der", "cpcer"]
    assert facts["chains"][1]["nodes"] == [
        {"id": "conversion/sa_asr__ear1_submission", "version": "v1"},
        {"id": "normalization/ear1_norm", "version": "v1"},
        {"id": "scoring/ear1_scorer", "version": "v1"},
    ]
    assert {"docs/tasks/sd.md", "docs/tasks/sa_asr.md"} <= set(facts["source_files"])


def test_unknown_pipeline_prevents_publication():
    with pytest.raises(ValueError, match="Unknown pipeline"):
        extract(Snapshot(ROOT, "HEAD"), ["imaginary.pipeline"])


@pytest.mark.parametrize("mutation", ["order", "version", "digest", "metric", "link"])
def test_facts_cannot_be_changed_by_model_or_editor(facts, copy, mutation):
    entry = entry_for(facts, copy)
    if mutation == "order":
        entry.chain[1].nodes.reverse()
    elif mutation == "version":
        entry.chain[0].nodes[0].version = "v99"
    elif mutation == "digest":
        entry.evidence.file_digests["docs/pipeline_catalog.jsonl"] = "wrong"
    elif mutation == "metric":
        entry.support.metrics = ["wer"]
    else:
        entry.links.source_change = "https://github.com/other/project/commit/" + "a" * 40
    with pytest.raises(ValueError):
        validate_entry(entry, ROOT, "PigeonDan1/sure-evaluation")


def test_source_route_order_mismatch_blocks_detection(repository):
    root, base, _ = repository
    path = root / "src/sure_eval/evaluation/tasks/sa_asr/routes.yaml"
    data = yaml.safe_load(path.read_text())
    data["routes"][-1]["nodes"].reverse()
    path.write_text(yaml.safe_dump(data))
    commit(root, "bad route order")
    with pytest.raises(ValueError, match="Node order"):
        detect(Snapshot(root, base), Snapshot(root, "HEAD"))


def test_reads_committed_evidence_not_dirty_files(repository):
    root, _, _ = repository
    path = root / "docs/pipeline_catalog.jsonl"
    path.write_text("corrupt dirty catalog")
    assert extract(Snapshot(root, "HEAD"), IDS)["chains"]


def test_schema_is_generated_from_runtime_contract():
    assert json.loads((AGENT / "schemas/news-entry.v1.json").read_text()) == Entry.model_json_schema()


@pytest.mark.parametrize("bad", ["[fake](https://fake.test)", "<script>", "two\nlines", "`id`"])
def test_model_copy_cannot_supply_markup(copy, bad):
    data = copy.model_dump()
    data["summary"] = bad
    with pytest.raises(ValidationError):
        Copy.model_validate(data)


def test_model_cannot_choose_pipeline_fields(copy):
    with pytest.raises(ValidationError):
        Copy.model_validate({**copy.model_dump(), "pipeline_id": "fake"})


def test_copy_contract_is_english_only(copy):
    assert set(copy.model_dump()) == {"title", "summary", "limitations"}
    with pytest.raises(ValidationError):
        Copy.model_validate({**copy.model_dump(), "title_zh": "不应出现"})


def test_ear_v1_name_is_rejected(facts, copy):
    entry = entry_for(facts, copy)
    entry.title = "EAR-v1 support"
    with pytest.raises(ValueError, match="EAR-v1"):
        validate_entry(entry, ROOT, "PigeonDan1/sure-evaluation")


def test_english_page_and_readme_boundaries(facts, copy):
    entry = entry_for(facts, copy)
    readme = (ROOT / "README.md").read_text()
    output = render([entry], readme)
    validate_output({"README.md": readme}, output, lambda p: (ROOT / p).is_file())
    assert outside_block(readme) == outside_block(output["README.md"])
    assert "<pre>" in output["README.md"]
    assert 'width="760"' in output["README.md"]
    assert "Latest evaluation support" in output["README.md"]
    assert "docs/news/readme-cards" not in output["README.md"]
    assert "docs/news/readme-rail.svg" not in output["README.md"]
    assert "View announcement history" in output["README.md"]
    assert "latest-support" not in output["docs/news/index.html"]
    assert "Latest evaluation support" not in output["docs/news/index.html"]
    assert "docs/news/cards/ear-1.svg" in output
    assert "RECENT SUPPORT" in output["docs/news/cards/ear-1.svg"]
    assert "01 · NEW SUPPORT" not in output["docs/news/cards/ear-1.svg"]
    assert "METRICS" in output["docs/news/cards/ear-1.svg"]
    assert "PIPELINE" in output["docs/news/cards/ear-1.svg"]
    assert "https://github.com/PigeonDan1/sure-evaluation/pull/49" in output["README.md"]
    assert "Score EAR-1 submissions for speaker diarization" in output["docs/news/cards/ear-1.svg"]
    assert "#ffffff" in output["docs/news/cards/ear-1.svg"]
    assert all(pipeline_id in output["docs/news/index.md"] for pipeline_id in IDS)
    assert '<a id="ear-1">' in output["docs/news/index.md"]


def test_pr_number_is_discovered_from_merge_commit(facts, copy, monkeypatch):
    entry = entry_for(facts, copy)
    entry.evidence.source_commit = "a" * 40
    monkeypatch.setattr(
        "news_agent.web.git",
        lambda *args: "Merge pull request #123 from contributor/new-route\n",
    )
    before = dict(PR_NUMBERS)
    numbers = resolve_pr_numbers(ROOT, [entry])
    assert pr_url(entry, pr_numbers=numbers).endswith("/pull/123")
    assert PR_NUMBERS == before
    assert pr_url(entry) == entry.links.source_change


@pytest.mark.parametrize("site_repository", [
    "PigeonDan1/sure-evaluation", "bichengzhang09-crypto/sure-evaluation",
])
def test_prepare_preserves_new_pr_links_in_a_fresh_process(repository, copy, site_repository):
    root, _, config = repository
    doc = root / "docs/tasks/sd.md"
    doc.write_text(doc.read_text() + "\nUpdated scoring requirements.\n")
    commit(root, "Merge pull request #123 from contributor/new-route")
    entry = entry_for(extract(Snapshot(root, "HEAD"), IDS), copy)
    readme = (root / "README.md").read_text()
    _, output = prepare(root, config.repository, entry=entry, site_repository=site_repository)
    assert 'href="https://github.com/PigeonDan1/sure-evaluation/pull/123"' in output["README.md"]
    assert "PR #123" in output["docs/news/cards/ear-1.svg"]
    assert outside_block(readme) == outside_block(output["README.md"])
    local_write(root, output)
    # This new interpreter has no PR mappings left over from the publisher.
    script = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from news_agent.cli import prepare
before, output = prepare(Path(sys.argv[2]), "PigeonDan1/sure-evaluation",
                         site_repository=sys.argv[3])
assert all(before[path] == content for path, content in output.items())
assert "/pull/123" in output["README.md"]
assert "PR #123" in output["docs/news/cards/ear-1.svg"]
'''
    result = subprocess.run(
        [sys.executable, "-c", script, str(AGENT / "src"), str(root), site_repository],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_direct_commit_keeps_source_link(repository, copy):
    root, _, config = repository
    entry = entry_for(extract(Snapshot(root, "HEAD"), IDS), copy)
    _, output = prepare(root, config.repository, entry=entry)
    assert f'href="{entry.links.source_change}"' in output["README.md"]
    assert "SOURCE ↗" in output["docs/news/cards/ear-1.svg"]


def test_visual_page_escapes_source_labels_and_links(facts, copy):
    entry = entry_for(facts, copy)
    entry.chain[0].nodes[0].id = 'conversion/unsafe"><script>alert(1)</script>'
    entry.chain[0].nodes[0].version = '<img src="https://unsafe.test">'
    output = render_page([entry])
    assert '<script>alert(1)</script>' not in output
    assert '<img src="https://unsafe.test">' not in output
    assert '&lt;img src=' in output
    assert all(pid in output for pid in IDS)


def test_visual_page_keeps_hero_timeline_and_language_switch(facts, copy):
    entry = entry_for(facts, copy)
    output = render_page([entry])
    assert '<header class="hero">' in output
    assert '<div class="release-date">' in output
    assert entry.links.source_change in output
    assert '<div class="language-switch"' in output
    assert 'data-language="en"' in output and 'data-language="zh"' in output
    assert 'data-zh="EAR-1 挑战赛评分支持"' in output
    assert ".release>span[id]{display:none}" in output
    assert 'id="latest-support"' not in output
    assert 'Latest evaluation support' not in output


def test_visual_publication_only_allows_named_assets_and_checks_html_links(facts, copy):
    assert allowed("docs/news/index.html") and allowed("docs/news/banner.svg")
    assert allowed("docs/news/cards/ear-1.svg")
    assert not allowed("docs/news/readme-cards/ear-1.svg")
    assert not allowed("docs/news/readme-rail.svg")
    assert not allowed("docs/news/arbitrary.html")
    assert not allowed("docs/news/arbitrary.svg")
    assert not allowed("docs/news/tracking.js")
    readme = (ROOT / "README.md").read_text()
    output = render([entry_for(facts, copy)], readme)
    output["docs/news/index.html"] = output["docs/news/index.html"].replace(
        'href="#updates"', 'href="https://unsafe.test/tracking"', 1,
    )
    with pytest.raises(ValueError, match="Unexpected external announcement link"):
        validate_output({"README.md": readme}, output, lambda p: (ROOT / p).is_file())


def test_chinese_readme_has_no_news_block():
    assert "SURE-NEWS:" not in (ROOT / "README_ZH.md").read_text()


@pytest.mark.parametrize("readme", ["no markers", START + START + END, END + START])
def test_missing_duplicated_reversed_markers_fail(readme):
    with pytest.raises(ValueError):
        replace_block(readme, "news")


@pytest.mark.parametrize("mutation", ["outside", "code", "link", "ids", "entry"])
def test_output_checks_fail_before_any_write(facts, copy, mutation):
    readme = (ROOT / "README.md").read_text()
    output = render([entry_for(facts, copy)], readme)
    before = {"README.md": readme}
    if mutation == "outside":
        output["README.md"] += "changed outside markers"
    elif mutation == "code":
        output["src/sure_eval/cli.py"] = "malicious"
    elif mutation == "link":
        output["docs/news/index.md"] += "\n[broken](../../missing.md)\n"
    elif mutation == "ids":
        output["docs/news/index.md"] = output["docs/news/index.md"].replace('id="ear-1"', 'id="wrong"')
    else:
        path = "docs/news/entries/ear-1.yaml"
        before[path], output[path] = "old facts", "changed facts"
    with pytest.raises(ValueError):
        validate_output(before, output, lambda p: (ROOT / p).is_file())


def test_preview_is_idempotent_and_leaves_checkout_untouched(tmp_path, facts, copy):
    readme = (ROOT / "README.md").read_text()
    output = render([entry_for(facts, copy)], readme)
    dest = tmp_path / "preview"
    assert preview(dest, {"README.md": readme}, output) == dest
    assert preview(dest, {"README.md": readme}, output) == dest
    assert (dest / "preview.diff").is_file()
    assert (ROOT / "README.md").read_text() == readme


def test_dry_run_can_use_unmerged_templates_with_committed_pipeline_facts(
    repository, copy, monkeypatch,
):
    root, base, config = repository
    readme = root / "README.md"
    template = readme.read_text()
    readme.write_text("# Project before announcement templates\n")
    commit(root, "historical PR without news templates")
    readme.write_text(template)
    config.preview_from_working_tree = True
    calls = []
    monkeypatch.setattr(KimiClient, "generate", lambda self, evidence: calls.append(evidence) or copy)
    original_head = git(root, "rev-parse", "HEAD")
    result = run_cycle(config, since=base)
    assert result["completed"][0]["status"] == "preview"
    assert len(calls) == 1
    assert calls[0]["source_commit"] == git(root, "rev-parse", "HEAD^1").strip()
    assert readme.read_text() == template
    assert git(root, "rev-parse", "HEAD") == original_head
    run_cycle(config)
    assert len(calls) == 1


def test_unmerged_templates_cannot_enter_remote_publication(repository, monkeypatch):
    _, _, config = repository
    config.preview_from_working_tree = True
    config.mode = "pr"
    monkeypatch.setattr(KimiClient, "generate", lambda *args: pytest.fail("No model request allowed"))
    with pytest.raises(ValueError, match="only allowed in dry-run"):
        run_cycle(config)
    assert not config.state_dir.exists()


def test_symlink_output_and_source_are_rejected(tmp_path, repository):
    (tmp_path / "docs").symlink_to("/tmp")
    with pytest.raises(ValueError, match="Unsafe output"):
        local_write(tmp_path, {"docs/news/index.md": "not allowed"})
    root, _, _ = repository
    path = root / "docs/tasks/sd.md"
    path.unlink()
    path.symlink_to("/etc/passwd")
    commit(root, "unsafe evidence")
    with pytest.raises(ValueError, match="unsafe source"):
        extract(Snapshot(root, "HEAD"), IDS)


def test_manual_entries_and_generated_pages_are_current():
    config = load_config(AGENT / "config.yaml.example")
    entries = load_entries(ROOT, config.repository)
    assert {"ear-1", "ear-1-scoring", "etc-bench", "fd-bench", "slu-judge", "openbench-se"} <= {e.id for e in entries}
    before, output = prepare(ROOT, config.repository, site_repository=config.site_repository,
                             pages_url=config.pages_url)
    assert all(before[p] == content for p, content in output.items())


def test_only_five_recent_entries_are_in_readme(facts, copy):
    entries = [entry_for(facts, copy) for _ in range(7)]
    for i, entry in enumerate(entries):
        entry.id = f"entry-{i}"
    output = render(entries, START + "\n" + END)
    assert output["README.md"].count("<pre>") == 1
    assert output["README.md"].count('width="760"') == 5
    assert sum(path.startswith("docs/news/cards/entry-") for path in output) == 5
    assert output["docs/news/index.md"].count('<a id="') == 7


def test_one_poll_attributes_distinct_features_to_their_own_merges():
    changes = list(feature_changes(Snapshot(ROOT, "abfdd68"), Snapshot(ROOT, "549eb71"), set()))
    assert [item["source_commit"][:7] for item in changes] == ["137fbcc", "549eb71"]
    assert [len(item["chains"]) for item in changes] == [1, 4]


def test_discovery_ignores_docs_only_commits_and_does_not_call_kimi(repository, monkeypatch):
    root, _, config = repository
    initial = run_cycle(config)
    (root / "docs/tasks/sd.md").write_text("Documentation-only change\n")
    head = commit(root, "docs only")
    monkeypatch.setattr(KimiClient, "generate", lambda *a: pytest.fail("Unexpected Kimi call"))
    result = run_cycle(config)
    assert initial["status"] == "initialized"
    assert result["cursor"] == head and not result["completed"]


def test_same_commit_calls_model_once_and_dry_run_never_publishes(repository, copy, monkeypatch):
    root, base, config = repository
    calls = []
    monkeypatch.setattr(KimiClient, "generate", lambda *a: calls.append(1) or copy)
    monkeypatch.setattr("news_agent.cli.publish", lambda *a: pytest.fail("Remote write during dry-run"))
    old_readme = (root / "README.md").read_text()
    first = run_cycle(config, since=base)
    assert first["completed"][0]["status"] == "preview"
    assert not run_cycle(config)["completed"]
    assert not run_cycle(config, since=base)["completed"]
    assert len(calls) == 1
    assert (root / "README.md").read_text() == old_readme
    assert git(root, "status", "--porcelain") == ""


def test_failure_preserves_cursor_and_queued_evidence_then_recovers(repository, copy, monkeypatch):
    root, base, config = repository
    state = State(config.state_dir)
    scope = config.repository + ":main"
    state.advance(scope, base)
    state.close()
    monkeypatch.setattr(KimiClient, "generate", lambda *a: (_ for _ in ()).throw(TimeoutError("timeout")))
    with pytest.raises(TimeoutError):
        run_cycle(config)
    state = State(config.state_dir)
    assert state.cursor(scope) == base
    job = state.pending(scope, "dry-run")[0]
    assert job["status"] == "failed" and "timeout" in job["error"]
    assert json.loads(job["evidence"])["file_digests"]
    state.close()
    assert git(root, "status", "--porcelain") == ""
    monkeypatch.setattr(KimiClient, "generate", lambda *a: copy)
    assert run_cycle(config)["completed"][0]["status"] == "preview"


def test_publish_failure_uses_cached_model_copy_on_retry(repository, copy, monkeypatch):
    _, base, config = repository
    config.mode = "pr"
    calls = []
    monkeypatch.setattr(KimiClient, "generate", lambda *a: calls.append(1) or copy)
    monkeypatch.setattr("news_agent.cli.publish", lambda *a: (_ for _ in ()).throw(RuntimeError("gh failed")))
    with pytest.raises(RuntimeError, match="gh failed"):
        run_cycle(config, since=base)
    monkeypatch.setattr("news_agent.cli.publish", lambda *a: "https://github.com/test/pr/1")
    assert run_cycle(config, since=base)["completed"][0]["status"] == "published"
    assert len(calls) == 1


def test_offline_fixture_cannot_publish_even_via_cached_preview(repository):
    _, base, config = repository
    fixture = AGENT / "tests/fixtures/copy.json"
    assert run_cycle(config, since=base, copy_file=fixture)["completed"]
    config.mode = "pr"
    with pytest.raises(ValueError, match="cannot be promoted"):
        run_cycle(config)
    with pytest.raises(ValueError, match="only accepted"):
        run_cycle(config, copy_file=fixture)


def test_independent_paths_and_lock(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("state_dir: ../sure-maintainer/state\n")
    with pytest.raises(ValueError, match="independent"):
        load_config(path)
    with locked(tmp_path / "news-state"):
        with pytest.raises(RuntimeError, match="holds the lock"):
            with locked(tmp_path / "news-state"):
                pytest.fail("Concurrent cycle acquired the lock")
    service = (AGENT / "deploy/sure-news-agent.service").read_text()
    assert "sure-news-agent" in service and "sure-maintainer" not in service
    assert "credentials.env" in service


def stream(copy, *, model=MODEL, finish="stop", content=None):
    result = copy.model_dump_json() if content is None else content
    chunks = [{"model": model, "choices": [{"index": 0, "delta": {"content": result}}]},
              {"model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}]
    return io.BytesIO(("\n".join("data: " + json.dumps(chunk) for chunk in chunks)
                       + "\ndata: [DONE]\n").encode())


@pytest.mark.parametrize("kind", ["truncated", "wrong-model", "invalid-json", "deadline"])
def test_bad_kimi_stream_is_rejected(copy, kind):
    response = stream(copy, model="other" if kind == "wrong-model" else MODEL,
                      finish="length" if kind == "truncated" else "stop",
                      content="{" if kind == "invalid-json" else None)
    with pytest.raises((ValueError, TimeoutError)):
        read_stream(response, time.monotonic() + (-1 if kind == "deadline" else 10))


def test_client_uses_dedicated_key_fixed_model_and_selected_catalog(copy, facts, monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "must-not-use")
    monkeypatch.delenv("NEWS_AGENT_KIMI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="NEWS_AGENT_KIMI_API_KEY"):
        KimiClient(Config()).generate(facts)
    monkeypatch.setenv("NEWS_AGENT_KIMI_API_KEY", "news-only")
    requests = []

    def open_request(request, timeout):
        requests.append(request)
        return stream(copy)

    monkeypatch.setattr("news_agent.kimi_client.urlopen", open_request)
    assert KimiClient(Config()).generate(facts) == copy
    request = requests[0]
    assert request.get_header("Authorization") == "Bearer news-only"
    data = json.loads(request.data)
    assert data["model"] == MODEL
    evidence = json.loads(data["messages"][1]["content"])
    assert "docs/pipeline_catalog.jsonl" not in evidence["files"]
    assert len(evidence["catalog_rows"]) == 2


@pytest.mark.parametrize("error", [URLError("unavailable"),
                                    HTTPError("https://api.kimi.com", 429, "busy", {}, None)])
def test_kimi_transient_errors_retry(copy, facts, monkeypatch, error):
    monkeypatch.setenv("NEWS_AGENT_KIMI_API_KEY", "test-key")
    monkeypatch.setattr("news_agent.kimi_client.time.sleep", lambda *a: None)
    attempts = []

    def open_request(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise error
        return stream(copy)

    monkeypatch.setattr("news_agent.kimi_client.urlopen", open_request)
    assert KimiClient(Config()).generate(facts) == copy
    assert len(attempts) == 2


def test_publisher_rejects_dry_run_before_git_or_network(repository):
    root, _, config = repository
    with pytest.raises(ValueError, match="dry-run"):
        publish(config, Snapshot(root, "HEAD"), "key", {})


def test_idempotency_key_includes_repository_branch_commit_catalog(facts):
    key = job_key("owner/repo", "main", facts)
    changed = copying.deepcopy(facts)
    changed["catalog_digest"] = "different"
    assert len({key, job_key("another/repo", "main", facts),
                job_key("owner/repo", "dev", facts), job_key("owner/repo", "main", changed)}) == 4


def test_failed_first_backfill_retries_without_since(repository, copy, monkeypatch):
    _, base, config = repository
    monkeypatch.setattr(KimiClient, "generate", lambda *a: (_ for _ in ()).throw(TimeoutError("timeout")))
    with pytest.raises(TimeoutError):
        run_cycle(config, since=base)
    monkeypatch.setattr(KimiClient, "generate", lambda *a: copy)
    assert run_cycle(config)["completed"][0]["status"] == "preview"


def test_published_pipeline_is_not_announced_again(repository, copy, monkeypatch):
    root, base, config = repository
    entry = entry_for(extract(Snapshot(root, "HEAD"), IDS), copy)
    before, output = prepare(root, config.repository, entry=entry)
    local_write(root, output)
    commit(root, "publish manual announcement")
    monkeypatch.setattr(KimiClient, "generate", lambda *a: pytest.fail("Duplicate announcement"))
    assert not run_cycle(config, since=base)["completed"]


def test_revision_keeps_history_and_hides_old_entry_from_readme(facts, copy):
    original = entry_for(facts, copy)
    revision = original.model_copy(deep=True)
    revision.id, revision.revision, revision.supersedes = "ear-1-revision-2", 2, "ear-1"
    output = render([original, revision], START + "\n" + END)
    assert "#ear-1\"" not in output["README.md"]
    assert "pull/49\"" in output["README.md"]
    assert output["docs/news/index.html"].count('<article class="release"') == 1
    assert 'id="ear-1-route-1"' in output["docs/news/index.html"]
    assert 'id="ear-1"' in output["docs/news/index.md"]


def test_local_remote_publisher_recovers_after_push_without_duplicate_model_call(
    repository, copy, monkeypatch, tmp_path
):
    root, base, config = repository
    remote = tmp_path / "remote.git"
    git(root, "init", "--bare", str(remote))
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "origin", "HEAD:refs/heads/main")
    source = Snapshot(root, "HEAD")
    config.mode = "pr"
    calls, creations = [], []
    monkeypatch.setattr(KimiClient, "generate", lambda *a: calls.append(1) or copy)

    def fake_gh(*args, root):
        if args[:2] == ("pr", "list"):
            return "[]"
        assert args[:2] == ("pr", "create")
        creations.append(args)
        if len(creations) == 1:
            raise RuntimeError("PR API unavailable after push")
        body = Path(args[args.index("--body-file") + 1]).read_text()
        assert source.sha in body and "Validation:" in body
        return "https://github.com/example/repo/pull/1"

    monkeypatch.setattr("news_agent.publisher.gh", fake_gh)
    with pytest.raises(RuntimeError, match="after push"):
        run_cycle(config, since=base)
    assert not list((config.state_dir / "worktrees").iterdir())
    assert run_cycle(config)["completed"][0]["status"] == "published"
    assert len(calls) == 1 and len(creations) == 2
    refs = git(root, "ls-remote", "origin", "refs/heads/news-agent/*").splitlines()
    assert len(refs) == 1
    remote_commit = refs[0].split()[0]
    changed = git(root, "diff", "--name-only", source.sha, remote_commit).splitlines()
    assert changed and all(p.startswith("docs/news/") or p == "README.md"
                           for p in changed)
    assert git(root, "rev-parse", "HEAD").strip() == source.sha
    assert git(root, "status", "--porcelain") == ""
    assert not list((config.state_dir / "worktrees").iterdir())


def test_publisher_rejects_readme_escape_before_remote_calls(repository, copy, monkeypatch):
    root, _, config = repository
    source = Snapshot(root, "HEAD")
    entry = entry_for(extract(source, IDS), copy)
    _, output = prepare(root, config.repository, snapshot=source, entry=entry)
    output["README.md"] += "outside edit"
    config.mode = "pr"
    monkeypatch.setattr("news_agent.publisher.gh", lambda *a, **k: pytest.fail("Contacted GitHub"))
    with pytest.raises(ValueError, match="escape"):
        publish(config, source, "key", output)


@pytest.mark.parametrize("path", [
    "NEWS.md", "docs/news/architecture.md", "docs/news/deploy.yaml",
    "docs/news/entries/nested/entry.yaml", "docs/news/cards/nested/card.svg",
    "news-agent/config.yaml", "news-agent/src/news_agent/web.py",
    ".github/workflows/announcement-pages.yml", "src/sure_eval/cli.py",
])
def test_publisher_rejects_other_files_before_writes(repository, copy, monkeypatch, path):
    root, _, config = repository
    source = Snapshot(root, "HEAD")
    entry = entry_for(extract(source, IDS), copy)
    _, output = prepare(root, config.repository, snapshot=source, entry=entry)
    output[path] = "Unrelated change\n"
    config.mode = "pr"
    monkeypatch.setattr("news_agent.publisher.gh", lambda *a, **k: pytest.fail("Contacted GitHub"))
    monkeypatch.setattr("news_agent.publisher.git", lambda *a, **k: pytest.fail("Changed Git state"))
    monkeypatch.setattr("news_agent.publisher.local_write", lambda *a, **k: pytest.fail("Wrote files"))
    assert not allowed(path)
    with pytest.raises(ValueError, match="Publisher cannot write"):
        publish(config, source, "key", output)
    assert git(root, "status", "--porcelain") == ""


def test_new_commits_during_model_failure_do_not_duplicate_queued_capabilities(repository, copy, monkeypatch):
    root, base, config = repository
    monkeypatch.setattr(KimiClient, "generate", lambda *a: (_ for _ in ()).throw(TimeoutError("timeout")))
    with pytest.raises(TimeoutError):
        run_cycle(config, since=base)
    (root / "README.md").write_text((root / "README.md").read_text() + "\nMore docs.\n")
    commit(root, "new commit while previous candidate is pending")
    calls = []
    monkeypatch.setattr(KimiClient, "generate", lambda *a: calls.append(1) or copy)
    assert len(run_cycle(config)["completed"]) == 1
    state = State(config.state_dir)
    try:
        assert len(state.diagnostics()["jobs"]) == 1
    finally:
        state.close()
    assert len(calls) == 1
