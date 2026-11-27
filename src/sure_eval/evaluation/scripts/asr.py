"""ASR configured script route descriptors."""

from __future__ import annotations

import re

from sure_eval.evaluation.scripts.contracts import (
    call_route_executor,
    contract_from_manifest,
    describe_from_contracts,
    find_pipeline_route,
    find_task_route,
    load_task_manifest,
    load_task_routes,
    route_execution_metric,
    write_route_run_outputs,
)


def describe_pipeline(
    *, language: str | None = None, metric: str | None = None, pipeline_id: str | None = None
):
    manifest, manifest_path, routes_path, route, _executor_metric = _select_route(
        language=language, metric=metric, pipeline_id=pipeline_id
    )
    route_language = route.get("language") or language or "n/a"
    return describe_from_contracts(
        task="ASR",
        pipeline_id=route["pipeline_id"],
        metric=route["metric"],
        language=route_language,
        node_ids=tuple(route["nodes"]),
        contracts=(contract_from_manifest(manifest, route["input_contract"]),),
        task_config_path=manifest_path,
        route_config_path=routes_path,
        computation_node_ids=tuple(route["nodes"]),
        execution_metrics=(str(route["metric"]),),
        script_module=__name__,
        executor=str(route.get("executor") or ""),
    )


def run(
    *,
    output_dir: str,
    ref_file: str | None = None,
    hyp_file: str | None = None,
    timing_jsonl: str | None = None,
    language: str | None = None,
    metric: str | None = None,
    pipeline_id: str | None = None,
):
    """Execute the configured ASR task route.

    Two input shapes exist under the ASR task:

    - text routes (cer/wer/mer) consume ``ref_file`` + ``hyp_file``;
    - the performance route (rtf) consumes a ``timing_jsonl`` sidecar only.

    ``output_dir`` is required by the script contract even though the in-process
    pipeline returns its report directly.
    """

    if not output_dir:
        raise ValueError("output_dir is required")
    description = describe_pipeline(language=language, metric=metric, pipeline_id=pipeline_id)
    _, _, _, route, executor_metric = _select_route(
        language=language, metric=metric, pipeline_id=pipeline_id
    )
    route_nodes = tuple(route.get("nodes") or ())
    if "scoring/streaming_rtf" in route_nodes:
        if not timing_jsonl:
            raise ValueError(
                "the rtf route requires --timing-jsonl (a model-produced timing sidecar); "
                "ref_file/hyp_file are not inputs of this route"
            )
        report = call_route_executor(
            route,
            timing_jsonl=timing_jsonl,
            language=route.get("language") or language or "en",
            metric=executor_metric,
        )
    else:
        report = call_route_executor(
            route,
            ref_file=ref_file,
            hyp_file=hyp_file,
            language=route.get("language") or language or description.language,
            metric=executor_metric,
            **_executor_selectors_from_route(route),
        )
    return write_route_run_outputs(report=report, description=description, output_dir=output_dir)


def _select_route(
    *, language: str | None = None, metric: str | None = None, pipeline_id: str | None = None
):
    manifest, manifest_path = load_task_manifest("asr")
    routes, routes_path = load_task_routes("asr")
    if pipeline_id:
        route = find_pipeline_route(routes, pipeline_id=pipeline_id, language=language)
        return manifest, manifest_path, routes_path, route, route_execution_metric(route)
    route_language = language or "zh"
    normalized_metric = _normalize_metric(
        language=route_language, metric=metric or _default_metric(manifest, route_language)
    )
    route = find_task_route(routes, language=route_language, metric=normalized_metric)
    return manifest, manifest_path, routes_path, route, route_execution_metric(route) or normalized_metric


def _default_metric(manifest: dict, language: str) -> str:
    try:
        return manifest["default_metrics"][language]
    except KeyError as exc:
        raise ValueError(f"Unsupported ASR language: {language}") from exc


def _normalize_metric(*, language: str, metric: str) -> str:
    normalized = metric.lower()
    if language == "zh" and normalized == "wer":
        return "cer"
    if language == "cs" and normalized in {"wer", "cer"}:
        return "mer"
    return normalized


def _executor_selectors_from_route(route: dict) -> dict[str, str]:
    selectors: dict[str, str] = {}
    for node_id in route.get("nodes") or ():
        if node_id == "normalization/wetext_norm":
            selectors["normalizer"] = f"wetext:{_wetext_profile_from_pipeline_id(route['pipeline_id'])}"
        elif node_id == "normalization/giga_norm":
            selectors["normalizer"] = f"giga:{_giga_profile_from_pipeline_id(route['pipeline_id'])}"
        elif node_id == "normalization/whisper_norm":
            selectors["normalizer"] = "whisper"
        elif node_id == "normalization/aispeech_norm":
            if not _is_codeswitch_wenet_route(route):
                selectors["normalizer"] = "aispeech"
        elif node_id == "normalization/canonical_itn":
            selectors["normalizer"] = "canonical"
        elif node_id == "normalization/punctuation_strip_norm":
            selectors["normalizer"] = "punctuation_strip"
        elif node_id == "normalization/nemo_norm":
            selectors["normalizer"] = "nemo:ar_tn"
        elif node_id == "normalization/xnorm":
            selectors["normalizer"] = f"xnorm:{route.get('language')}"
        elif node_id == "normalization/etc_canonicalization":
            selectors["normalizer"] = f"etc:{route.get('language')}"
        elif node_id in {"scoring/wenet_cer", "scoring/wenet_wer", "scoring/wenet_mer"}:
            selectors["scorer"] = "wenet"
        elif node_id == "scoring/token_cer":
            selectors["scorer"] = "token"
        elif node_id == "scoring/token_mer":
            selectors["scorer"] = "token_mer"
        elif node_id == "scoring/sctk_sclite":
            selectors["scorer"] = "sctk_sclite"
    return selectors


def _is_codeswitch_wenet_route(route: dict) -> bool:
    return (
        route.get("language") == "cs"
        and route.get("metric") == "mer"
        and not route.get("internal_executor_metric")
    )


def _wetext_profile_from_pipeline_id(pipeline_id: str) -> str:
    for component in str(pipeline_id).split(".")[3:]:
        if component.startswith("wetext_norm_"):
            profile = re.sub(r"_v[0-9]+$", "", component.removeprefix("wetext_norm_"))
            if profile:
                return profile
    raise ValueError(f"Cannot infer wetext_norm profile from pipeline_id={pipeline_id!r}")


def _giga_profile_from_pipeline_id(pipeline_id: str) -> str:
    for component in str(pipeline_id).split(".")[3:]:
        if component.startswith("giga_norm_"):
            profile = re.sub(r"_v[0-9]+$", "", component.removeprefix("giga_norm_"))
            if profile:
                return profile.upper()
    raise ValueError(f"Cannot infer giga_norm profile from pipeline_id={pipeline_id!r}")
