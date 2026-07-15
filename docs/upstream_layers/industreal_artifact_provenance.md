# How the IndustReal Upstream Artifacts Were Produced

## Purpose and repository boundary

This document explains the provenance of the IndustReal artifacts that enter this thesis repository as Layers 1–2 output. It is deliberately limited to the data path that matters to the symbolic reasoning and validation work implemented here.

Layers 1–2 were developed in the companion [XR Event Grounding Graph repository](https://github.com/cedrickaneza/XR_Event_Grounding_Graph). Their implementation scripts, the raw videos, and the full intermediate results are **not included here**. This repository contains a public, static export of their layer boundary under:

```text
results/neo4j/raw_cad_dataset__all_test_clips/
```

The included scripts begin at the next boundary: they adapt those CSV files into symbolic records, infer procedural constraints, validate the inferred steps, and build a reasoning-enriched graph. See [Architecture](../architecture.md) for that downstream design.

## Source dataset

The upstream workflow used the public **IndustReal** dataset, an egocentric dataset for industrial-like assembly procedure-step recognition, including recordings with execution errors. A raw clip provides synchronized visual streams and recording metadata together with annotations such as:

- assembly/object-state labels (`OD_labels.json` in the upstream workflow);
- procedure-step labels, used for evaluation; and
- procedure-step labels containing execution errors, used by the error-hint experiment.

The public fixture in this repository was derived from the test archives `test_p1`, `test_p2`, and `test_p3`. It covers 19 physical clips. Each clip was processed under two evidence modes, yielding 38 clip/mode results.

The fixture is derived data, not a substitute for the original dataset. Dataset attribution and citation information are provided in the root [README](../../README.md#dataset--citation).

## What “CAD-grounded” means

The upstream workflow used CAD knowledge **symbolically**. It did not estimate metric 6D poses, register CAD meshes to video frames, or evaluate image-only part detection.

CAD-related assembly knowledge supplied:

- a canonical component vocabulary;
- legal assembly states;
- legal transitions between those states; and
- a final target state and its required components.

This knowledge acted as an assembly rulebook. It constrained how annotated states could become component-level events and supplied structure for the exported assembly goal. References such as `state22.fbx` in the CSV fixture are provenance fields from the upstream CAD catalog; the corresponding geometry files are not distributed in this repository.

## Oracle-first evidence modes

The word *oracle* means that trusted dataset annotations were used in place of predictions from an image detector. This isolates the procedural-interpretation problem from perception accuracy.

| Mode | Evidence used | Question addressed |
| --- | --- | --- |
| `od_only` | Assembly/object-state annotations | What procedural structure can be recovered from annotated state changes alone? |
| `od_plus_psr_error_hints` | The same state annotations plus labeled PSR error moments | What changes when known execution-error moments are also supplied? |

The second mode is not a deployable error detector: its error moments come from ground-truth annotations. Keeping both modes in the export makes that difference explicit and permits paired comparisons over the same 19 clips.

## Transformation from recordings to graph CSVs

The relevant upstream transformation was:

```text
IndustReal clip and annotations
  -> frame-indexed manifest
  -> oracle state evidence
  -> CAD-constrained state timeline
  -> component-level procedure events
  -> assembly graph JSON
  -> Neo4j-compatible node and edge CSVs
```

At a high level:

1. A clip loader aligned frames, timestamps, recording metadata, and annotations.
2. The selected oracle mode converted labels into frame-indexed assembly-state evidence.
3. CAD-informed legal states and transitions constrained the state timeline.
4. State changes were converted into semantic events such as `INSTALL`, `REMOVE`, and `ERROR`, with a component, frame, time, description, and confidence.
5. Events were ordered within each clip and grouped into readable phases beneath a CAD-grounded assembly goal.
6. The resulting graph was flattened into the node and relationship CSV files committed here.

The export uses 10 frames per second, which is visible in the fixture as `time_s = frame / 10` (for example, frame 709 is 70.9 seconds).

## Included artifact scope

The checked-in CSV fixture contains:

| Artifact | Count | Meaning |
| --- | ---: | --- |
| Run | 1 | The complete exported batch |
| Evidence modes | 2 | `od_only` and `od_plus_psr_error_hints` |
| Clip/mode results | 38 | 19 clips evaluated once per mode |
| Assembly events | 659 | Upstream candidate procedure steps |
| Canonical components | 11 | Components acted on by events or required by goals |
| Assembly goals | 38 | One goal per clip/mode result |
| Assembly phases | 227 | Human-readable event groupings |

These numbers describe the committed fixture, not the size of the complete IndustReal dataset.

## Boundary consumed by this thesis

The Layer 3 adapter reads four files:

```text
nodes_events.csv
edges_event_component.csv
edges_event_next.csv
nodes_components.csv
```

From them it obtains the candidate action, component, confidence, source frame/time, and event order. It writes normalized `step_records.jsonl` and provenance-bearing `predicates.jsonl`. Domain knowledge in [`config/domain_config.yaml`](../../config/domain_config.yaml) is then materialized as additional predicates by this repository's adapter; it should not be confused with an independent upstream observation.

The remaining upstream CSVs retain batch, clip, goal, phase, final-state, and metric context. They are useful for inspection, but they are not required by the current adapter. The complete file-level contract is documented in [Upstream Graph CSV Reference](upstream_graph_csv_contract.md).

## What can and cannot be reproduced here

From this repository alone, a reader can:

- inspect the exact Layers 1–2 CSV fixture used by the thesis;
- rebuild Layers 3–4 outputs from that fixture;
- trace a validation result back to an upstream CSV row and field; and
- import the reasoning-enriched downstream graph into Neo4j.

A reader cannot regenerate the fixture from raw IndustReal recordings here because the upstream loader, oracle-state reasoner, CAD catalog builder, graph exporter, raw dataset, and CAD assets are not included. Those belong to the companion repository/workflow linked above.

## Interpretation limits

The safe thesis claim is:

> Given oracle-derived IndustReal state evidence and symbolic CAD assembly knowledge, Layers 1–2 produced ordered component-level event graphs that serve as input to the reasoning and validation layers in this repository.

The artifacts do **not** establish:

- image-only component or error detection accuracy;
- metric depth reconstruction or CAD-to-camera alignment;
- expert-validated correctness of every generated event; or
- independent perception evidence for installation targets.

The last point matters downstream. The current fixture has no canonical `observed_installation_target*` fields. The behavior for a missing independently observed target is therefore controlled by [`config/observation_contract.yaml`](../../config/observation_contract.yaml), rather than silently being presented as a visual observation.
