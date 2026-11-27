"""Independent Kimi Code client; fixed model and dedicated credential."""

from __future__ import annotations

import json
import os
import time
from importlib.resources import files
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import MODEL
from .config import Config
from .contract import Copy


def read_stream(response, deadline: float) -> dict:
    content = []
    model = None
    finish = None
    size = 0
    for raw in response:
        if time.monotonic() > deadline:
            raise TimeoutError("Kimi stream exceeded total deadline")
        size += len(raw)
        if size > 2_000_000:
            raise ValueError("Kimi response exceeds size limit")
        line = raw.decode("utf-8").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        payload = json.loads(data)
        model = payload.get("model", model)
        for choice in payload.get("choices", []):
            if choice.get("index", 0) != 0:
                continue
            delta = choice.get("delta", {}).get("content")
            if delta:
                content.append(delta)
            if choice.get("finish_reason") is not None:
                finish = choice["finish_reason"]
    if model != MODEL or finish != "stop":
        raise ValueError(f"Unexpected model or incomplete Kimi response: {model}, {finish}")
    return json.loads("".join(content))


class KimiClient:
    def __init__(self, config: Config):
        self.config = config

    def generate(self, frozen: dict) -> Copy:
        return Copy.model_validate(self.request(frozen))

    def request(self, frozen: dict) -> dict:
        key = os.environ.get("NEWS_AGENT_KIMI_API_KEY", "").strip()
        if not key or any(ord(c) < 32 or ord(c) == 127 for c in key):
            raise ValueError("Set a valid NEWS_AGENT_KIMI_API_KEY")
        endpoint = self.config.endpoint.rstrip("/")
        if not endpoint.startswith("https://"):
            raise ValueError("Kimi endpoint must use HTTPS")
        prompt = frozen.get("prompt") or files("news_agent").joinpath(
            "prompts/news_v1.md").read_text(encoding="utf-8")
        evidence = dict(frozen)
        # Keep the complete catalog in our frozen queue, but send only selected
        # rows to the model. Manifests and task docs remain available in full.
        evidence["files"] = {path: data for path, data in frozen.get("files", {}).items()
                             if path != "docs/pipeline_catalog.jsonl"}
        payload = {"model": MODEL, "temperature": 1, "reasoning_effort": "low",
                   "max_tokens": self.config.max_output_tokens, "stream": True,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": prompt},
                                {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)}]}
        request = Request(endpoint + "/chat/completions", data=json.dumps(payload).encode(),
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json", "Accept": "text/event-stream",
                                   "User-Agent": "sure-news-agent/0.1"}, method="POST")
        for attempt in range(self.config.attempts):
            try:
                started = time.monotonic()
                with urlopen(request, timeout=self.config.timeout_seconds) as response:
                    result = read_stream(response, started + self.config.timeout_seconds)
                return result
            except HTTPError as exc:
                # Do not persist response bodies, headers or keys in diagnostics.
                if exc.code not in {429, 500, 502, 503, 504} or attempt + 1 == self.config.attempts:
                    raise RuntimeError(f"Kimi HTTP {exc.code}") from None
            except (URLError, TimeoutError):
                if attempt + 1 == self.config.attempts:
                    raise RuntimeError("Kimi network request failed or timed out") from None
            time.sleep(min(2 ** attempt, 8))
        raise RuntimeError("Kimi retry limit reached")
