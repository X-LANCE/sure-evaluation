# EAR-1 Evaluation

EAR-1 challenge scoring. All routes use `scoring/ear1_openbench` (`v1`, scorer
`openbench-integration-0.1`).

| Pipeline ID | Task / track | Metric |
|:--|:--|:--|
| `ear1.esd.d1.der.ear1_openbench_v1` | ESD-ON / D1 | `der` |
| `ear1.esd.r1.der.ear1_openbench_v1` | ESD-ON / R1 | `der` |
| `ear1.esr.d1.cpcer.ear1_openbench_v1` | ESR-ON / D1 | `cpcer` |
| `ear1.esr.r1.cpcer.ear1_openbench_v1` | ESR-ON / R1 | `cpcer` |

Without `--track`, the D1 route of the selected metric is used.

Input roles: `submission` and `reference_dir`. The executor is
`pipeline.evaluate_ear1_files`.

See [docs/tasks/ear1.md](../../../../../docs/tasks/ear1.md) for formats and
examples.
