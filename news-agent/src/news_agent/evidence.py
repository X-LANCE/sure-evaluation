"""Freeze catalog, route and manifest facts from a single commit."""

from __future__ import annotations

import hashlib
import json

import yaml

from .git import CATALOG, Snapshot


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def catalog(snapshot: Snapshot) -> dict[str, dict]:
    rows = [json.loads(line) for line in snapshot.read(CATALOG).splitlines() if line.strip()]
    result = {row["pipeline_id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError("Duplicate catalog pipeline_id")
    return result


def extract(snapshot: Snapshot, pipeline_ids: list[str]) -> dict:
    rows = catalog(snapshot)
    if not pipeline_ids or len(pipeline_ids) != len(set(pipeline_ids)):
        raise ValueError("Expected unique nonempty pipeline IDs")
    files = {CATALOG: snapshot.read(CATALOG)}

    def load(path: str) -> dict:
        if path not in files:
            files[path] = snapshot.read(path)
        return yaml.safe_load(files[path])

    chains = []
    docs = []
    selected = []
    for pipeline_id in pipeline_ids:
        if pipeline_id not in rows:
            raise ValueError(f"Unknown pipeline_id: {pipeline_id}")
        row = rows[pipeline_id]
        if row["pipeline_kind"] != "atomic":
            raise ValueError("Only atomic pipelines can establish new support")
        task = row["task_alias"]
        task_manifest = load(row["task_config_path"])
        routes = load(row["route_config_path"])
        matching = [r for r in routes["routes"] if r["pipeline_id"] == pipeline_id]
        if len(matching) != 1:
            raise ValueError(f"Missing or duplicate route: {pipeline_id}")
        route = matching[0]
        nodes = row["computation_node_ids"]
        conversion_ids = [n for n in nodes if n.startswith("conversion/")]
        expected = ["conversion/" + c for c in route.get("conversions", [])]
        # Older routes infer their conversion from the task adapter. Verify those
        # conversion manifests too, while keeping route computation order exact.
        if "conversions" in route and conversion_ids != expected:
            raise ValueError(f"Conversion order disagrees with route: {pipeline_id}")
        if nodes != conversion_ids + route["nodes"] or row["nodes"] != route["nodes"]:
            raise ValueError(f"Node order disagrees with route/catalog: {pipeline_id}")
        if (route["metric"] != row["metric"] or route["executor"] != row["executor"]
                or route.get("language", "n/a") != row["language"]
                or routes["task"] != row["task"] or task_manifest["task"] != row["task"]):
            raise ValueError(f"Task/metric/language/executor mismatch: {pipeline_id}")
        contract = task_manifest["input_contracts"][route["input_contract"]]
        if contract["required_roles"] != row["required_roles"]:
            raise ValueError(f"Required inputs disagree: {pipeline_id}")
        versions = []
        for node_id in nodes:
            prefix = "conversion" if node_id.startswith("conversion/") else "nodes"
            suffix = node_id.split("/", 1)[1] if prefix == "conversion" else node_id
            if node_id in {"scoring/wenet_cer", "scoring/wenet_mer"}:
                suffix = "scoring/wenet_wer"
            path = f"src/sure_eval/evaluation/{prefix}/{suffix}/manifest.yaml"
            manifest = load(path)
            expected_id = suffix if prefix == "conversion" else node_id
            if expected_id not in (manifest["id"], *manifest.get("aliases", [])) or not manifest.get("version"):
                raise ValueError(f"Invalid node identity: {node_id}")
            versions.append({"id": node_id, "version": str(manifest["version"])})
        doc = f"docs/tasks/{task}.md"
        files[doc] = snapshot.read(doc)
        docs.append(doc)
        chains.append({"task": task, "language": row["language"], "metric": row["metric"],
                       "pipeline_id": pipeline_id, "nodes": versions})
        selected.append(row)
    return {"source_commit": snapshot.sha, "catalog_digest": digest(rows),
            "chains": chains, "docs": sorted(set(docs)), "catalog_rows": selected,
            "source_files": sorted(files), "files": files,
            "file_digests": {path: hashlib.sha256(data.encode()).hexdigest()
                             for path, data in files.items()}}
