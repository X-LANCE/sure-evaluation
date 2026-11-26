from pathlib import Path

from news_agent.git import git

AGENT = Path(__file__).resolve().parents[1]
ROOT = AGENT.parent
IDS = [
    "sd.any.der.conversion_sd_ear1_submission_v1.ear1_scorer_v1",
    "sa_asr.zh.cpcer.conversion_sa_asr_ear1_submission_v1.ear1_norm_v1.ear1_scorer_v1",
]


def commit(root: Path, message: str) -> str:
    git(root, "add", ".")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@localhost", "-c",
        "core.hooksPath=/dev/null", "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD").strip()
