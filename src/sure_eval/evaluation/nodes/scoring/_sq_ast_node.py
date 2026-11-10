"""CLI and scoring helpers for the five SQ-AST component nodes."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
import sys
from pathlib import Path

from sure_eval.evaluation.core.types import PipelineNodeResult
from sure_eval.evaluation.nodes.scoring._audio_quality import MOSProvider, MOSRow, score_mos_backend
from sure_eval.evaluation.nodes.scoring._score_components import ScoreComponentProvider
from sure_eval.evaluation.nodes.scoring._sq_ast import SQASTProvider


def score_sq_ast(
    rows: list[MOSRow],
    *,
    provider: MOSProvider,
    dimension: str,
    node_id: str,
) -> PipelineNodeResult:
    return score_mos_backend(
        rows,
        metric_name=f"sq_ast_{dimension}",
        node_id=node_id,
        provider=ScoreComponentProvider(provider, field=f"sq_ast_{dimension}"),
        version="v1",
    )


def run_node(
    argv: list[str] | None,
    *,
    dimension: str,
    node_id: str,
) -> int:
    parser = argparse.ArgumentParser(description=f"Score SQ-AST {dimension}.")
    parser.add_argument("--prediction-audio")
    parser.add_argument("--input-jsonl")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    if bool(args.input_jsonl) == bool(args.prediction_audio):
        parser.error("exactly one of --input-jsonl or --prediction-audio is required")
    provider = SQASTProvider(dimensions=(dimension,), device=args.device)
    if args.input_jsonl:
        rows: list[MOSRow] = []
        for line in Path(args.input_jsonl).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows.append((str(row.get("key", "")), str(row["prediction_audio"])))
        if args.json_output:
            with redirect_stdout(sys.stderr):
                trace = score_sq_ast(rows, provider=provider, dimension=dimension, node_id=node_id)
        else:
            trace = score_sq_ast(rows, provider=provider, dimension=dimension, node_id=node_id)
        payload = {
            "node_id": node_id,
            "version": "v1",
            "result": trace.details["result"],
            "keys": trace.details["keys"],
        }
        if args.json_output:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        else:
            print(payload["result"].get("score", ""))
        return 0
    if args.json_output:
        with redirect_stdout(sys.stderr):
            result = provider(args.prediction_audio)
    else:
        result = provider(args.prediction_audio)
    payload = {"node_id": node_id, "version": "v1", "prediction_audio": args.prediction_audio, "result": result}
    if args.json_output:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    else:
        print(result.get(f"sq_ast_{dimension}", ""))
    return 0
