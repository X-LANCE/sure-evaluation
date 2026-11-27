"""MER configured script route descriptors."""

from __future__ import annotations

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


def describe_pipeline(*, metric: str = "rmse", pipeline_id: str | None = None):
    manifest, manifest_path, routes_path, route, normalized_metric = _select_route(
        metric=metric, pipeline_id=pipeline_id
    )
    return describe_from_contracts(
        task="MER",
        pipeline_id=route["pipeline_id"],
        metric=normalized_metric,
        language="n/a",
        node_ids=tuple(route["nodes"]),
        contracts=(contract_from_manifest(manifest, route["input_contract"]),),
        task_config_path=manifest_path,
        route_config_path=routes_path,
        computation_node_ids=tuple(route.get("computation_nodes") or route["nodes"]),
        execution_metrics=(normalized_metric,),
        script_module=__name__,
        executor=str(route.get("executor") or ""),
    )


def run(*, output_dir: str, **kwargs):
    if not output_dir:
        raise ValueError("output_dir is required")
    metric = kwargs.pop("metric", "rmse")
    pipeline_id = kwargs.pop("pipeline_id", None)
    description = describe_pipeline(metric=metric, pipeline_id=pipeline_id)
    _, _, _, route, normalized_metric = _select_route(metric=metric, pipeline_id=pipeline_id)
    granularity = kwargs.pop("granularity", route.get("granularity", "static"))
    aggregation = kwargs.pop("aggregation", route.get("aggregation", "micro"))
    timestamp_tolerance_sec = kwargs.pop(
        "timestamp_tolerance_sec", route.get("timestamp_tolerance_sec", 1e-6)
    )
    report = call_route_executor(
        route,
        metric=normalized_metric,
        granularity=str(granularity),
        aggregation=str(aggregation),
        timestamp_tolerance_sec=float(timestamp_tolerance_sec),
        **kwargs,
    )
    return write_route_run_outputs(report=report, description=description, output_dir=output_dir)


def _select_route(*, metric: str, pipeline_id: str | None):
    manifest, manifest_path = load_task_manifest("mer")
    routes, routes_path = load_task_routes("mer")
    if pipeline_id:
        route = find_pipeline_route(routes, pipeline_id=pipeline_id)
        return manifest, manifest_path, routes_path, route, route_execution_metric(route)
    route = find_task_route(routes, metric=metric.lower().replace("-", "_"))
    return manifest, manifest_path, routes_path, route, route_execution_metric(route)
