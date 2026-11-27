from datetime import date

import pytest
from pydantic import ValidationError

from news_agent.cli import prepare
from news_agent.config import Config, default_pages_url
from news_agent.contract import make_entry
from news_agent.publisher import validate_output
from news_test_helpers import ROOT


def test_fork_site_links_are_separate_from_source_evidence(facts, copy):
    entry = make_entry(facts, copy, repository="PigeonDan1/sure-evaluation",
                       entry_id="fork-site-test", published_at=date(2026, 11, 26))
    config = Config(site_repository="example/sure-evaluation",
                    pages_url="https://releases.example.org/sure")
    assert config.site_url == "https://releases.example.org/sure/"
    before, output = prepare(ROOT, config.repository, entry=entry,
                             site_repository=config.site_repository, pages_url=config.site_url)
    assert config.site_url in output["README.md"]
    assert 'href="https://github.com/example/sure-evaluation"' in output["docs/news/index.html"]
    assert entry.links.source_change in output["docs/news/index.html"]
    assert "https://github.com/PigeonDan1/sure-evaluation/pull/49" in output["README.md"]
    validate_output(before, output, lambda p: (ROOT / p).is_file(), pages_url=config.site_url)
    with pytest.raises(ValueError, match="Unexpected external announcement link"):
        validate_output(before, output, lambda p: (ROOT / p).is_file())


def test_site_url_defaults_follow_configured_repository():
    assert Config().site_url == default_pages_url("PigeonDan1/sure-evaluation")
    assert Config(repository="AnotherOwner/project").site_url == "https://anotherowner.github.io/project/"


@pytest.mark.parametrize("url", [
    "http://example.org/", "https://user:password@example.org/", "https://example.org/?x=1",
    "https://example.org/#updates", "https://bad host/",
])
def test_site_url_rejects_unsupported_forms(url):
    with pytest.raises(ValidationError):
        Config(pages_url=url)
