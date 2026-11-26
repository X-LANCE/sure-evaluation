"""Self-contained visual release notes from the same validated announcement facts."""

import re
from collections.abc import Mapping
from html import escape
from importlib.resources import files
from pathlib import Path

from .contract import Entry
from .git import git

TASK_NAMES = {"sd": "Speaker diarization", "sa_asr": "Speaker-attributed ASR"}
METRICS = {"der": "DER", "cpcer": "cpCER"}
PR_NUMBERS = {
    "3853dab1db5d7d44691b25a6620932742a1c0a50": 49,
    "c1bc96cf865baef07e37f702a8286d3a6c68a5a2": 47,
    "549eb711483e7c4e515479864bca8e0abd558572": 44,
    "137fbcc8b89b8c96ca10e641d409808c22165435": 38,
    "abfdd68801cce39e28a27ccfb9335deee091a27f": 40,
    "204ffe814fa7b0797e8471d80916339d1dfd0690": 39,
}
MERGE_PR = re.compile(r"^Merge pull request #(\d+) from ")
ZH_COPY = {
    "ear-1-scoring": {
        "title": "EAR-1 挑战赛评分支持",
        "summary": "支持使用 DER 评测说话人分离，以及使用 cpCER 评测中文说话人归属 ASR。",
        "brief": "SD → 提交转换 → DER\nSA-ASR → 转换 → EAR-1 规范化 → cpCER",
        "limitations": "使用组织方评分器，需要安装 SciPy，并提供包含 D1 或 R1 赛道的 sessions.json。",
    },
    "fd-bench": {
        "title": "FD-Bench 全双工对话时序",
        "summary": "测量系统开始说话、提前回复和打断用户的时间表现。",
        "brief": "语音区间 → 全双工时间线 → IRD、FSED、ERT、EIT",
        "limitations": "提供用户和系统语音区间，并使用一致的时间起点。",
    },
    "slu-judge": {
        "title": "SLU 答案质量评测",
        "summary": "依据自定义评分标准，在 0 到 100 分范围内评估口语语言理解答案。",
        "brief": "答案 + 评分标准 → LLM 评测 → 平均分",
        "limitations": "需要提供答案、提示、评分标准和已配置的评测模型，分数取决于评分标准。",
    },
    "etc-bench": {
        "title": "ETC-Bench 转写规范化",
        "summary": "在 ASR 对比前，对 12 种语言中的等价书写形式进行统一规范化。",
        "brief": "参考文本 + 识别结果 → ETC 规范化 → WeNet CER 或 WER",
        "limitations": "需要提供 ETC 模型。阿拉伯语、日语和中文使用 CER，其余语言使用 WER。",
    },
    "openbench-se": {
        "title": "OpenBench 语音增强评测",
        "summary": "使用可选指标评测增强语音的可懂度、频谱失真和预测质量。",
        "brief": "增强音频（必要时附参考音频） → 指标评分 → 语料库均值",
        "limitations": "参考音频指标需要对齐的干净音频，学习型质量估计取决于所选模型。",
    },
}
ZH_COPY["ear-1"] = ZH_COPY["ear-1-scoring"]


def task_label(task: str) -> str:
    return task.upper().replace("_", "-")


def node_label(node_id: str) -> str:
    stage, name = node_id.split("/", 1)
    if stage == "conversion":
        return "Submission conversion"
    if node_id == "normalization/ear1_norm":
        return "EAR-1 normalization"
    if node_id == "scoring/ear1_scorer":
        return "EAR-1 scorer"
    return name.replace("_", " ")


def source_link(entry: Entry, path: str) -> str:
    commit_url = entry.links.source_change
    repository_url = commit_url.rsplit("/commit/", 1)[0]
    return f"{repository_url}/blob/{entry.evidence.source_commit}/{path}"


def pr_url(entry: Entry, *, pr_numbers: Mapping[str, int] | None = None) -> str:
    repository = entry.links.source_change.rsplit("/commit/", 1)[0]
    numbers = PR_NUMBERS if pr_numbers is None else pr_numbers
    number = numbers.get(entry.evidence.source_commit)
    return f"{repository}/pull/{number}" if number else entry.links.source_change


def resolve_pr_numbers(root: Path, entries: list[Entry]) -> dict[str, int]:
    """Resolve PR links for this render without mutating historical defaults."""
    numbers = dict(PR_NUMBERS)
    for entry in entries:
        commit = entry.evidence.source_commit
        if commit in numbers:
            continue
        try:
            subject = git(root, "show", "-s", "--format=%s", commit).strip()
        except RuntimeError:
            continue
        match = MERGE_PR.match(subject)
        if match:
            numbers[commit] = int(match.group(1))
    return numbers


def link(label: str, url: str, css: str = "") -> str:
    return f'<a class="{css}" href="{escape(url, quote=True)}">{escape(label)} ↗</a>'


def route_anchor(entry: Entry, number: int) -> str:
    return f"{entry.id}-route-{number}"


def pipeline_brief(entry: Entry) -> str:
    if entry.pipeline_brief:
        return entry.pipeline_brief
    paths = dict.fromkeys(" → ".join(node_label(n.id) for n in chain.nodes)
                          for chain in entry.chain)
    return "\n".join(paths)


def localized_copy(entry: Entry) -> dict[str, str]:
    return {
        "title": entry.title,
        "summary": entry.summary,
        "brief": pipeline_brief(entry),
        "limitations": entry.limitations,
        **ZH_COPY.get(entry.id, {}),
        **(entry.zh.model_dump() if entry.zh else {}),
    }


def article(entry: Entry, previous: list[Entry]) -> str:
    copy = localized_copy(entry)
    aliases = "".join(f'<span id="{e.id}"></span>' for e in previous)
    rows = []
    for number, chain in enumerate(entry.chain, 1):
        old_anchors = "".join(f'<span id="{route_anchor(e, i)}"></span>' for e in previous
                              for i, c in enumerate(e.chain, 1) if c.pipeline_id == chain.pipeline_id)
        steps = " → ".join(f"{escape(n.id)} ({escape(n.version)})" for n in chain.nodes)
        pid = escape(chain.pipeline_id)
        rows.append(f'<li id="{route_anchor(entry, number)}">{old_anchors}'
                    f'<div><code>{pid}</code><small>{steps}</small></div>'
                    f'<button class="copy-button" data-copy="{pid}" aria-label="Copy pipeline ID">Copy</button></li>')
    docs = " ".join(link(task_label(p.rsplit("/", 1)[-1][:-3]), source_link(entry, p))
                    for p in entry.links.docs)
    tests = " ".join(link(p.rsplit("/", 1)[-1], source_link(entry, p)) for p in entry.links.tests)
    search = escape(" ".join([entry.title, entry.summary, pipeline_brief(entry), *entry.support.tasks,
                              *entry.support.metrics, *entry.support.pipeline_ids]))
    label = escape(" · ".join(task_label(t) for t in entry.support.tasks))
    count = len(rows)
    commit = entry.links.source_change
    return f'''<article class="release" id="{entry.id}" data-search="{search}"
      data-tasks="{escape(' '.join(entry.support.tasks))}">{aliases}
      <div class="release-date"><span class="timeline-dot"></span>
      <time datetime="{entry.published_at}"><a href="{escape(commit, quote=True)}"
      title="Open the source commit"><strong>{entry.published_at:%d %b}</strong><span>{entry.published_at.year}</span></a></time>
      <a class="release-type" href="{escape(commit, quote=True)}">Commit {entry.evidence.source_commit[:7]} ↗</a></div>
      <div class="release-content"><div class="release-kicker"><span class="status"><i></i> <span data-i18n="supported">Supported</span></span>
      <span class="release-ref">{label} · {count:02d} {'pipeline' if count == 1 else 'pipelines'}</span></div>
      <h2 class="entry-title" data-entry-i18n="title" data-en="{escape(entry.title, quote=True)}" data-zh="{escape(copy['title'], quote=True)}">{escape(entry.title)}</h2><p class="release-summary entry-summary" data-entry-i18n="summary" data-en="{escape(entry.summary, quote=True)}" data-zh="{escape(copy['summary'], quote=True)}">{escape(entry.summary)}</p>
      <p class="flow entry-brief" data-entry-i18n="brief" data-en="{escape(pipeline_brief(entry), quote=True)}" data-zh="{escape(copy['brief'], quote=True)}">{escape(pipeline_brief(entry))}</p>
      <details><summary>{count} <span class="pipeline-word" data-en="{'pipeline' if count == 1 else 'pipelines'}" data-zh="{'条流水线' if count != 1 else '条流水线'}">{'pipeline' if count == 1 else 'pipelines'}</span></summary>
      <p class="release-summary"><strong data-i18n="beforeRun">Before you run</strong><br><span class="entry-limitation" data-entry-i18n="limitations" data-en="{escape(entry.limitations, quote=True)}" data-zh="{escape(copy['limitations'], quote=True)}">{escape(entry.limitations)}</span></p><ul>{''.join(rows)}</ul>
      <p class="sources"><span data-i18n="taskDocumentation">Task documentation</span> &nbsp; {docs}</p>
      {f'<p class="sources"><span data-i18n="tests">Tests</span> &nbsp; {tests}</p>' if tests else ''}</details>
      </div></article>'''


def render_page(entries: list[Entry], *, site_repository: str | None = None) -> str:
    superseded = {e.supersedes for e in entries if e.supersedes}
    active = [e for e in entries if e.id not in superseded]
    by_id = {e.id: e for e in entries}
    tasks = sorted({task for entry in active for task in entry.support.tasks})
    chips = "".join(f'<button type="button" class="filter" data-task="{escape(t)}">{escape(task_label(t))}</button>'
                    for t in tasks)
    articles = []
    for entry in active:
        previous = []
        old = by_id.get(entry.supersedes)
        while old and old not in previous:
            previous.append(old)
            old = by_id.get(old.supersedes)
        articles.append(article(entry, previous))
    template = files("news_agent").joinpath("templates/news.html").read_text(encoding="utf-8")
    latest = active[0] if active else None
    if site_repository is None:
        site_repository = (entries[0].links.source_change.rsplit("/commit/", 1)[0]
                           .removeprefix("https://github.com/")) if entries else ""
    repository = "https://github.com/" + escape(site_repository, quote=True)
    replacements = {
        "{{REPOSITORY}}": repository,
        "{{DATE}}": latest.published_at.strftime("%d %b %Y") if latest else "No updates yet",
        "{{COUNT}}": str(len(active)),
        "{{ROUTES}}": str(len({p for e in active for p in e.support.pipeline_ids})),
        "{{TASKS}}": str(len({t for e in active for t in e.support.tasks})),
        "{{FILTERS}}": chips,
        "{{CONTENT}}": "".join(articles),
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def render_banner(entries: list[Entry]) -> str:
    count = len({p for entry in entries for p in entry.support.pipeline_ids})
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="184" viewBox="0 0 1120 184" role="img" aria-labelledby="title desc">
    <title id="title">SURE evaluation release notes</title>
    <desc id="desc">New evaluation capabilities with explicit pipelines and source evidence.</desc>
    <rect width="1120" height="184" rx="16" fill="#153f35"/>
    <g font-family="Arial, Helvetica, sans-serif">
      <text x="38" y="42" fill="#b6d5c7" font-size="12" font-weight="700" letter-spacing="3">SURE / RELEASE NOTES</text>
      <text x="36" y="98" fill="#f6f8ef" font-size="39" font-weight="700" letter-spacing="-1">New capabilities. Every step, explained.</text>
      <text x="38" y="140" fill="#c0d3c8" font-size="15">Exact pipelines · Reproducible evaluation · Source evidence</text>
      <rect x="946" y="34" width="136" height="116" rx="12" fill="#244d41"/>
      <text x="1014" y="88" text-anchor="middle" fill="#ddf1ac" font-size="40" font-weight="700">{count:02d}</text>
      <text x="1014" y="119" text-anchor="middle" fill="#c0d3c8" font-size="12">evaluation routes</text>
    </g></svg>'''
