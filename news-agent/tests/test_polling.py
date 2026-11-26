from datetime import date

import pytest

from news_agent import polling
from news_agent.contract import make_entry
from news_agent.evidence import extract
from news_agent.git import Snapshot, git
from news_agent.publisher import allowed
from news_agent.renderer import outside_block
from news_agent.state import State
from news_test_helpers import IDS, commit


def test_polling_poll_add_revise_retry_and_deduplicate(repository, tmp_path, copy, monkeypatch):
    root, base, config = repository
    source = tmp_path / "upstream.git"
    target = tmp_path / "polling.git"
    git(root, "clone", "--bare", str(root), str(source))
    git(root, "clone", "--bare", str(root), str(target))
    config.source_repository = "source/example"
    config.target_repository = "target/example"
    config.poll_mode = "direct"
    git(root, "config", f"url.{source}.insteadOf", "https://github.com/source/example.git")
    git(root, "config", f"url.{target}.insteadOf", "https://github.com/target/example.git")
    state = State(config.state_dir)
    state.advance("source/example:main->target/example:main", base)
    state.close()

    def respond(self, payload):
        if "candidates" in payload:
            return {"publish": [item["id"] for item in payload["candidates"]]}
        en = dict(copy.model_dump(), brief="SD and SA-ASR scoring")
        return {"en": en, "zh": dict(en, title="评分支持")}

    monkeypatch.setattr(polling.KimiClient, "request", respond)
    first = polling.poll(config)
    assert first["source"] == Snapshot(source, "main").sha
    assert len(first["published"]) == 1
    page = Snapshot(target, "main").read("docs/news/index.html")
    assert "评分支持" in page and all(pid in page for pid in IDS)
    assert Snapshot(target, "main").sha != Snapshot(source, "main").sha
    assert outside_block(Snapshot(target, "main").read("README.md")) == outside_block(
        Snapshot(source, "main").read("README.md"))
    changed = git(root, "diff", "--name-only", first["source"], first["commit"]).splitlines()
    assert changed and all(allowed(path) for path in changed)
    doc = root / "docs/tasks/sd.md"
    doc.write_text(doc.read_text() + "\nChanged scoring requirements.\n")
    revised = commit(root, "Update scoring requirements")
    git(root, "push", str(source), "HEAD:main")
    second = polling.poll(config)
    assert second["source"] == revised and len(second["published"]) == 1
    page = Snapshot(target, "main").read("docs/news/index.html")
    assert all(key in page for key in first["published"] + second["published"])
    assert page.count('<article class="release"') == 1
    # Recover a remote push whose subsequent local cursor update was interrupted.
    state = State(config.state_dir)
    state.advance("source/example:main->target/example:main", base)
    state.close()
    assert polling.poll(config)["candidates"] == 0
    assert polling.poll(config)["published"] == []
    assert Snapshot(target, "main").sha == second["commit"]


@pytest.mark.parametrize("path", ["NEWS.md", "docs/news/deploy.yaml", "news-agent/src/news_agent/web.py"])
def test_polling_publisher_rejects_other_files_before_writes(repository, copy, monkeypatch, path):
    root, _, config = repository
    head = Snapshot(root, "HEAD")
    entry = make_entry(extract(head, IDS), copy, repository=config.repository,
                       entry_id="support-test", published_at=date(2026, 11, 18))
    original_render = polling.render

    def changed_render(*args, **kwargs):
        output = original_render(*args, **kwargs)
        output[path] = "Unrelated change\n"
        return output

    monkeypatch.setattr(polling, "render", changed_render)
    monkeypatch.setattr(polling, "git", lambda *a, **k: pytest.fail("Changed Git state"))
    monkeypatch.setattr(polling, "local_write", lambda *a, **k: pytest.fail("Wrote files"))
    with pytest.raises(ValueError, match="Publisher cannot write"):
        polling.publish_batch(config, head, [], [entry], config.repository, config.repository)
    assert git(root, "status", "--porcelain") == ""
