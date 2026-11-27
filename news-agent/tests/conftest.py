from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

AGENT = Path(__file__).resolve().parents[1]
ROOT = AGENT.parent
sys.path.insert(0, str(AGENT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from news_agent.config import Config  # noqa: E402
from news_agent.contract import Copy  # noqa: E402
from news_agent.evidence import extract  # noqa: E402
from news_agent.git import Snapshot, git  # noqa: E402
from news_test_helpers import IDS, commit  # noqa: E402


@pytest.fixture(scope="session")
def facts():
    return extract(Snapshot(ROOT, "3853dab1db5d7d44691b25a6620932742a1c0a50"), IDS)


@pytest.fixture
def copy():
    return Copy.model_validate_json((AGENT / "tests/fixtures/copy.json").read_text())


@pytest.fixture
def repository(tmp_path, facts):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    for path, data in facts["files"].items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data, encoding="utf-8")
    (root / "README.md").write_text("# Project\n\n<!-- SURE-NEWS:START -->\n"
                                    "<!-- SURE-NEWS:END -->\n\nPreserved content.\n")
    catalog = root / "docs/pipeline_catalog.jsonl"
    catalog.write_text("\n".join(json.dumps(row) for row in [
        json.loads(line) for line in facts["files"]["docs/pipeline_catalog.jsonl"].splitlines()
    ] if row["pipeline_id"] not in IDS) + "\n")
    base = commit(root, "baseline")
    catalog.write_text(facts["files"]["docs/pipeline_catalog.jsonl"])
    commit(root, "add EAR-1 routes")
    config = Config(checkout=root, state_dir=tmp_path / "state", log_dir=tmp_path / "logs",
                    ref="HEAD")
    return root, base, config
