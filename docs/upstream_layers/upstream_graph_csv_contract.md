# Upstream IndustReal Graph CSV Reference

## Why these CSVs are here

The directory [`results/neo4j/raw_cad_dataset__all_test_clips/`](../../results/neo4j/raw_cad_dataset__all_test_clips/) is the portable boundary between the companion Layers 1–2 workflow and the Layers 3–4 implementation in this repository.

The name `neo4j` describes the files' bulk-import-style schema: node IDs, start/end IDs, labels, relationship types, and typed property suffixes. The current reasoning pipeline reads the CSVs directly; it does not require a Neo4j database for inference or validation.

For how the recordings and annotations became this export, first read [How the IndustReal Upstream Artifacts Were Produced](industreal_artifact_provenance.md).

## Graph structure

Conceptually, every exported batch has this hierarchy:

```text
Run
  -> Mode
    -> Clip result
      -> Assembly goal
        -> Phase
          -> Assembly event
            -> Component
```

Additional relationships order events and phases, connect a goal to its required target components, and record each clip's final component states.

The same physical clip appears once for each evidence mode. Consequently, `clip_result_id`, rather than the bare clip name, is the correct isolation key. Its shape is:

```text
<run_id>::<mode>::<archive_name>::<clip>
```

Example:

```text
raw_cad_dataset__all_test_clips::od_only::test_p1::03_assy_0_1
```

## Files used by the reasoning adapter

The current Layer 3 adapter is configured in [`config/reasoning_adapter.yaml`](../../config/reasoning_adapter.yaml) and consumes only the following four tables.

### `nodes_events.csv`

One row per candidate assembly event. The committed fixture contains 659 rows.

Important fields:

| Field | Meaning |
| --- | --- |
| `event_id:ID(AssemblyEvent)` | Globally unique event identifier |
| `clip_result_id` | Clip/mode result to which the event belongs |
| `local_event_id:int` | Event index local to the result |
| `frame:int`, `time_s:float` | Event instant in the recording |
| `event_type` | Normalized upstream action, such as `INSTALL`, `REMOVE`, or `ERROR` |
| `component` | Human-readable acted-on component |
| `action_desc` | Presentation label for the event |
| `conf:float` | Upstream event confidence |

The upstream export records event instants, not explicit duration windows. The adapter uses the current event as the start and the next distinct event time as the inferred end; the final timestamp group remains open-ended.

### `edges_event_component.csv`

Connects every assembly event to its acted-on component. Its `role` property records how the component participates in the event. The adapter uses these edges to generate object-interaction predicates.

### `edges_event_next.csv`

Orders events inside a single `clip_result_id`. The fixture has 621 links: 38 fewer than its 659 events, corresponding to one terminal event per clip/mode result.

### `nodes_components.csv`

Defines the 11 canonical component nodes and their display/normalized names. The adapter joins these rows to event-component edges and maps the source components to the domain model in [`config/domain_config.yaml`](../../config/domain_config.yaml).

## Context tables retained from Layers 1–2

These tables preserve the richer upstream assembly graph but are not read by the current adapter.

| File | Rows | Purpose |
| --- | ---: | --- |
| `nodes_runs.csv` | 1 | Batch identity and export metadata |
| `nodes_modes.csv` | 2 | Oracle evidence modes |
| `nodes_clips.csv` | 38 | Clip/mode metadata and upstream evaluation metrics |
| `nodes_goals.csv` | 38 | CAD-grounded target state per clip/mode result |
| `nodes_phases.csv` | 227 | Ordered, readable groups of events |
| `edges_run_mode.csv` | 2 | Run-to-mode membership |
| `edges_mode_clip.csv` | 38 | Mode-to-clip-result membership |
| `edges_clip_event.csv` | 659 | Clip-result-to-event membership |
| `edges_clip_goal.csv` | 38 | Clip result to assembly goal |
| `edges_goal_phase.csv` | 227 | Goal-to-phase hierarchy |
| `edges_phase_step.csv` | 659 | Phase-to-event membership |
| `edges_phase_next.csv` | 189 | Phase ordering within results |
| `edges_goal_target_component.csv` | 380 | Components required by the CAD target state |
| `edges_clip_final_component_state.csv` | 418 | Final known/unknown state of each component per result |

`nodes_clips.csv` contains upstream metrics such as state accuracy, legal-state rate, step precision/recall, delay, and error-window recall. They evaluate the oracle-first Layers 1–2 transformation and must not be presented as evaluation of the symbolic validation statuses produced by Layers 3–4.

## How CSV evidence becomes reasoning input

The adapter entry point included in this repository is [`scripts/14_build_layer3_reasoning_adapter.py`](../../scripts/14_build_layer3_reasoning_adapter.py). For each selected `clip_result_id`, it combines the four input tables with the domain and observation-contract configuration:

```text
upstream event row
  + event-to-component edge
  + component metadata
  + event ordering
  -> step_records.jsonl
  -> predicates.jsonl
```

Typical mappings include:

| Reasoning value | Upstream origin |
| --- | --- |
| Step identity and source metadata | `nodes_events.csv` |
| `hasAction(step, action)` | `event_type` / `action_desc` |
| `usesObject(step, component)` | event-component edge and component node |
| Start frame/time and confidence | event row |
| End frame/time | next distinct upstream event instant |
| Component type, expected target, tools, and conditions | downstream `domain_config.yaml`, materialized by the adapter |

That final row is intentionally different: domain-config predicates are declared knowledge, not observations recovered from the IndustReal recording. Predicate records retain source information so later constraints and validation outcomes can be traced to their actual origin.

## Optional observation fields

The adapter supports canonical fields for an independently observed installation target:

```text
observed_installation_target
observed_installation_target_confidence
observed_installation_target_source
```

They are defined by [`config/observation_contract.yaml`](../../config/observation_contract.yaml), but they are absent from the committed `nodes_events.csv`. Their absence is valid. The configured missing-observation policy determines whether the downstream rules may fall back to the expected domain target or must require an observation.

## Inspecting the fixture

No upstream exporter needs to be installed to inspect the boundary. For example, from the repository root:

```powershell
Import-Csv results\neo4j\raw_cad_dataset__all_test_clips\nodes_events.csv |
  Where-Object clip_result_id -eq 'raw_cad_dataset__all_test_clips::od_only::test_p1::03_assy_0_1' |
  Sort-Object {[int]$_.'local_event_id:int'} |
  Select-Object 'local_event_id:int', 'frame:int', event_type, component, 'conf:float'
```

To list the 38 available result identifiers:

```powershell
Import-Csv results\neo4j\raw_cad_dataset__all_test_clips\nodes_clips.csv |
  Select-Object -ExpandProperty 'clip_result_id:ID(IndustRealClip)'
```

To rebuild all reasoning outputs locally from this fixture, without connecting to Neo4j:

```powershell
.venv\Scripts\python.exe scripts\25_rebuild_all_reasoning_and_import_neo4j.py --skip-import
```

## Neo4j distinction

There are two different graph products:

1. **Upstream assembly graph CSVs** (this document): candidate events, components, goals, phases, ordering, and upstream metrics from Layers 1–2.
2. **Procedural reasoning graphs**: predicates, inferred constraints, rules, dependency support, missing requirements, validation statuses, and provenance produced by Layers 3–4.

Only the second graph has an importer in this public repository. [`scripts/18_import_procedural_reasoning_graph_neo4j.py`](../../scripts/18_import_procedural_reasoning_graph_neo4j.py) imports reasoning graphs generated here; it is not the missing Layers 1–2 CSV exporter or importer. Neo4j remains a downstream inspection mechanism and is never required to compute validation semantics.
