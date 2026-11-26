from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import Field, field_validator

from .contract import Strict


def default_pages_url(repository: str) -> str:
    owner, name = repository.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/"


class Config(Strict):
    repository: str = Field(default="PigeonDan1/sure-evaluation",
                            pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    site_repository: str | None = Field(default=None,
                                       pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    pages_url: str | None = None
    checkout: Path = Path("..")
    base_branch: str = Field(default="main", pattern=r"^[A-Za-z0-9_./-]+$")
    remote: str = Field(default="origin", pattern=r"^[A-Za-z0-9_-]+$")
    ref: str = "refs/remotes/origin/main"
    fetch: bool = False
    mode: Literal["dry-run", "pr", "docs-commit"] = "dry-run"
    preview_from_working_tree: bool = False
    state_dir: Path = Path("state")
    log_dir: Path = Path("logs")
    endpoint: str = "https://api.kimi.com/coding/v1"
    timeout_seconds: int = Field(default=300, ge=1, le=600)
    attempts: int = Field(default=3, ge=1, le=5)
    max_output_tokens: int = Field(default=4000, ge=512, le=16000)

    @field_validator("pages_url")
    @classmethod
    def validate_pages_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or any(c.isspace() for c in value)):
            raise ValueError("pages_url must be an HTTPS site URL without credentials, query or fragment")
        return value.rstrip("/") + "/"

    @property
    def site_url(self) -> str:
        return self.pages_url or default_pages_url(self.site_repository or self.repository)


def load_config(path: Path) -> Config:
    config = Config.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    parent = path.resolve().parent
    for key in ("checkout", "state_dir", "log_dir"):
        value = getattr(config, key)
        setattr(config, key, (parent / value).resolve())
    # No implicit .env loading, fallback key or shared runtime directories.
    for value in (config.state_dir, config.log_dir):
        if "sure-maintainer" in value.parts:
            raise ValueError("news-agent requires independent runtime directories")
    return config
