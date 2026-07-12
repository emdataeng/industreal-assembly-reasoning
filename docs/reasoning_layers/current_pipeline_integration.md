# Current Reasoning Layer Integration Notes

This document describes how the current reasoning-layer implementation connects to the existing IndustReal pipeline. It is meant as a practical implementation note that can later be folded into a full pipeline README.

## Current Data Flow

The existing pipeline first builds an assembly graph and exports Neo4j-style CSV files under:

```text
results/neo4j/<run_id>/
```

The current reasoning-layer bridge starts from those exported CSV files. It does not replace the existing graph generation, Neo4j export, or Neo4j import path.

The flow is:

```text
existing graph CSVs
  -> optional UI graph-data export
  -> platform/data/graph-data.js

existing graph CSVs + config/domain_config.yaml + config/observation_contract.yaml + config/thesis_rules.yaml
  -> Layer 2-to-3 reasoning adapter
  -> step_records.jsonl + predicates.jsonl (Layer 3 inputs)

step_records.jsonl + predicates.jsonl + config/thesis_rules.yaml
  -> Layer 3 rule inference
  -> inferred_constraints.csv
  -> Layer 4 validation
  -> validation_records.jsonl + step_validations.csv + explanation_traces.json + effect_history_diagnostics.csv
  -> procedural_reasoning_graph
  -> procedural_reasoning_graph.json + procedural_reasoning_graph_nodes.csv + procedural_reasoning_graph_edges.csv
  -> Neo4j procedural graph import
```

Current scripts:

```text
scripts/14_build_layer3_reasoning_adapter.py
scripts/15_run_layer3_inference.py
scripts/16_run_layer4_validation.py
scripts/17_build_procedural_reasoning_graph.py
scripts/18_import_procedural_reasoning_graph_neo4j.py
scripts/19_build_graph_data_js.py
scripts/25_rebuild_all_reasoning_and_import_neo4j.py
```

`scripts/19_build_graph_data_js.py` is a downstream UI export helper. It reads the regular per-clip result JSON files under `results/` together with the Neo4j CSV export under `results/neo4j/<run_id>/`, then writes `platform/data/graph-data.js` as `window.INDUSTREAL_DATA = {...}` for the browser UI. It does not feed the Layer 3 or Layer 4 reasoning artifacts.

`scripts/25_rebuild_all_reasoning_and_import_neo4j.py` is the batch rebuild and import wrapper. It discovers every `clip_result_id` in `results/neo4j/<run_id>/nodes_events.csv`, rebuilds the reasoning-layer outputs and procedural graph for each clip/mode, and then imports the rebuilt procedural graphs into Neo4j. Each imported procedural graph uses a per-clip graph name such as `procedural_reasoning_graph::<clip_result_id>`, so rebuilding one clip replaces only that clip's imported procedural graph.

Current implementation modules:

```text
src/layer3_reasoning_adapter.py
src/layer3_inference.py
src/layer4_validation.py
src/procedural_reasoning_graph.py
src/procedural_neo4j_import.py
```

Adapter runtime defaults are configured in:

```text
config/reasoning_adapter.yaml
```

That file defines the default run id, input CSV directory, output root, predicate/rule config path, domain config path, and the expected Neo4j CSV filenames consumed by the adapter. `scripts/14_build_layer3_reasoning_adapter.py` accepts `--adapter-config` to load a different adapter config.

## Adapter Role

The adapter bridges Layer 2 output to Layer 3. For IndustReal, it turns the
existing graph CSV records into `step_records.jsonl` and `predicates.jsonl`,
which are inputs to Layer 3 inference, not outputs from Layer 3.

It reads:

```text
nodes_events.csv
edges_event_component.csv
edges_event_next.csv
nodes_components.csv
config/domain_config.yaml
config/observation_contract.yaml
config/thesis_rules.yaml (adapter predicate definitions)
```

It writes:

```text
step_records.jsonl
predicates.jsonl
```

`step_records.jsonl` contains one normalized step record per source assembly event.

`predicates.jsonl` contains symbolic facts derived from each step, such as the step action, time window, object use, and component metadata.

`config/domain_config.yaml` is consumed here by the adapter to materialize
component-specific domain knowledge into predicates. Layer 3 inference does
not read that file directly. `config/thesis_rules.yaml` is used at both stages:
the adapter reads its predicate definitions, and Layer 3 inference reads its
aliases, defaults, and rules.

`config/observation_contract.yaml` defines optional canonical fields for
independently observed installation targets and the policy used when those
fields are absent. It is referenced by `config/reasoning_adapter.yaml` and is
shared across upstream sources rather than tied to a particular VLM, parser, or
dataset.

The current canonical event fields are:

```text
observed_installation_target
observed_installation_target_confidence
observed_installation_target_source
```

They are optional. Existing IndustReal `nodes_events.csv` files do not need to
add empty columns.

The upstream graph stores event instants. The adapter fills `time_window.start_s` and `start_frame` from the event row, and currently infers `end_s` and `end_frame` from the next distinct event timestamp in the same clip when one exists. The final timestamp group remains open-ended with null end values. This is a downstream fallback until upper-layer step segmentation provides explicit step windows.

## Predicate Configuration

Predicate names are configured in:

```text
config/thesis_rules.yaml
```

under:

```text
adapter.predicates
```

The current categories are:

```text
event
object_interaction
entity_metadata
```

Each configured predicate has a stable adapter key, an output name, an argument description, and an enabled flag.

Example:

```json
"has_action": {
  "name": "hasAction",
  "description": "Associates a step with its normalized action label.",
  "args": ["step_id", "action_name"],
  "enabled": true
}
```

The stable adapter key is used by Python code to decide which extraction path to run. The configured `name` is what appears in `predicates.jsonl` and what Layer 3 rules match against.

Predicate aliases are configured under `predicate_aliases`. Layer 3 normalizes predicate names before rule matching, so equivalent names such as `stepHasAction`, `actsOn`, and `typeOf` can be mapped to canonical names such as `hasAction`, `usesObject`, and `isA`.

Disabling a current predicate is also a config change:

```json
"enabled": false
```

## Upstream Boundary

The config controls the vocabulary for predicates that the adapter already knows how to generate.

The adapter still needs Python logic for each kind of predicate because each predicate depends on specific upstream data. For example:

```text
has_action
  reads event_type/action_desc from nodes_events.csv

uses_object
  reads event-component edges from edges_event_component.csv

is_a
  reads component metadata from nodes_components.csv

observed_install_target
  reads optional canonical observation fields from nodes_events.csv
```

This is expected. A config file can say what a predicate is called, but it cannot invent source evidence that does not exist upstream.

So the extension rule is:

```text
Rename, recategorize, or disable an existing predicate:
  update config/thesis_rules.yaml

Add a new predicate using data the adapter does not currently read or derive:
  add a small generator path in src/layer3_reasoning_adapter.py
  add the predicate definition to config/thesis_rules.yaml
  add or update Layer 3 rules that consume the new predicate
```

For example, a future `isAfter(step_a, step_b)` predicate could be derived from `edges_event_next.csv`, but the adapter would need explicit code that converts those event-next edges into that predicate shape.

## Layer 3 Rule Inference

Layer 3 inference reads:

```text
step_records.jsonl
predicates.jsonl
config/thesis_rules.yaml
```

These are the direct Layer 3 inputs. In particular,
`config/domain_config.yaml` is not a direct Layer 3 input; its relevant domain
knowledge has already been encoded into `predicates.jsonl` by the adapter.

It writes:

```text
inferred_constraints.csv
rule_coverage_diagnostics.csv
```

Layer 4 validation reads:

```text
step_records.jsonl
predicates.jsonl
inferred_constraints.csv
rule_coverage_diagnostics.csv
```

It writes:

```text
validation_records.jsonl
step_validations.csv
explanation_traces.json
effect_history_diagnostics.csv
```

Rules are also stored in `config/thesis_rules.yaml`, under:

```text
rules
```

Each rule matches predicate names and argument patterns. Rule outputs are defined under the `constraints` field. When the antecedents match and confidence passes the threshold, the rule emits one or more constraints.

Rules may also define two-argument guards:

```json
{"operator": "equal", "args": ["?left", "?right"]}
{"operator": "not_equal", "args": ["?left", "?right"]}
```

Guards run after antecedent matching and operate on bound variables.

The current rule categories follow the methodology draft:

```text
inferred_precondition
expected_effect
safety_constraint
required_tool
implicit_assembly_condition
compatibility
```

These categories use the rule evaluation structure from `Methodology_Design.tex`, Listing `lst:alg_rule_evaluation`. Non-compatibility rules are evaluated first: find bindings, collect supporting predicates, aggregate confidence, compare with the rule threshold, and instantiate configured constraints. Compatibility rules are evaluated in a separate pass and emit incompatibility constraints with provenance; these are interpreted as hard validity conditions during later validation.

Current examples use domain individual ids and generic class predicates:

```text
hasAction(step1, install) + usesObject(step1, base) + isA(base, Component)
  + allowsDomainAssumedInstallTarget(step1, base)
  -> produces(step1, installed, base, workspace)

hasAction(step2, install) + usesObject(step2, rear_chassis) + isA(rear_chassis, Component)
  -> requires(step2, installed, base, workspace)
  -> produces(step2, installed, rear_chassis, base)

hasAction(step3, install) + usesObject(step3, front_rear_chassis_pin) + isA(front_rear_chassis_pin, ChassisPin)
  -> requires(step3, installed, rear_chassis, base)
  -> requires(step3, aligned, front_rear_chassis_pin, rear_chassis)
  -> produces(step3, installed, front_rear_chassis_pin, rear_chassis)

usesObject(step7, front_bracket_screw) + isA(front_bracket_screw, Screw)
  -> requiresTool(step, screwdriver)

hasAction(step, error) + usesObject(step, object)
  -> incompatibleAction(step, object, error)
```

Because rules match by predicate name after alias normalization, changing a predicate output name in `adapter.predicates` should either use a canonical vocabulary name or add an explicit alias to `predicate_aliases`.

### Observed versus expected installation targets

Expected domain knowledge and observed upstream claims are intentionally
separate:

```text
hasInstallTarget(component, expected_target)
observedInstallTarget(step, component, observed_target)
```

The adapter never rewrites the observed target to match the expected one.

The three target-grounding outcomes are:

```text
observed == expected
  -> produces installed(component, observed_target)

observed != expected
  -> incompatibleInstallationTarget(component, observed_target, expected_target)
  -> Layer 4 rejects the step

no observed target + domain_assumed policy
  -> allowsDomainAssumedInstallTarget(step, component)
  -> preserves the expected domain-derived installed effect
```

The default policy lives in `config/observation_contract.yaml`:

```json
"missing_observation_policy": "domain_assumed"
```

Set it to `require_observed` to disable fallback. In that mode, a target-less
installation does not receive a confirmed installed effect from the domain
target alone.

An upstream source can participate without changing the reasoning rules. It
only needs to populate the canonical optional event fields. For example:

```text
event_type: INSTALL
component: front rear chassis pin
observed_installation_target: industreal_component::front_bracket
observed_installation_target_confidence: 0.83
observed_installation_target_source: vlm
```

The resulting mismatch remains traceable to both the upstream observation and
the expected target materialized from `domain_config.yaml`.

## Layer 4 Validation

Layer 3 only infers requirements and expected effects. It does not decide whether a requirement is satisfied.

Layer 3 also writes `rule_coverage_diagnostics.csv`, one row per step. This diagnostic records the action name, object/tool arguments, predicate count, matched rule count, produced constraint count, and coverage booleans such as `has_expected_effect`, `has_requirement`, `has_incompatibility`, and `has_rule_coverage`. If a step has meaningful predicate evidence, such as `hasAction(...)` plus `usesObject(...)` or `usesTool(...)`, but no Layer 3 rule produces constraints, the diagnostic row uses:

```text
warning_code: no_applicable_rule
warning_message: Step has predicate evidence but no Layer 3 rule produced constraints.
```

This is intentionally diagnostic rather than a fabricated semantic rule. For example, if a future action has predicate evidence but no matching Layer 3 rule, the step is marked as unsupported by the current rule coverage instead of being assigned invented dependencies or effects.

The current rule set does define remove-action semantics. A `remove` action over a configured component can produce a precondition requiring the component to be installed and an expected `removed(component, target)` effect. Layer 4 then uses that removed effect to invalidate the matching active installed effect.

Layer 4 walks the ordered steps and maintains two views of previous `produces(...)` effects:

```text
historical produced effects  all produced effects retained for traceability
active produced effects      non-rejected effects still available to support later requirements
```

For each step, it checks requirement constraints such as `requires(...)`, `requiresSafety(...)`, and `requiresTool(...)` against:

```text
same-step predicates
active previous produced effects
```

If a requirement is supported by a previous effect, the validation record links it to the earlier producing constraint. Domain requirement predicates such as `hasRequiredCondition(...)`, `hasSafetyRequirement(...)`, and `hasRequiredTool(...)` state that a condition is required; they are not treated as evidence that the condition was satisfied.

When an accepted or uncertain step produces `removed(component, target)`, Layer 4 invalidates the matching active `installed(component, target)` effect. The installed effect remains in the historical record, but it is removed from active support so later requirements cannot use it. Rejected steps do not contribute active effects, so their produced effects are marked inactive and cannot support later requirements.

Layer 4 exposes this lifecycle explicitly through `produced_effect_lifecycle` records. Each produced effect receives:

```text
effect_lifecycle_status: active | invalidated | inactive_rejected
invalidated_by_constraint_id
```

`active` means the produced effect is still available after the complete validation pass. `invalidated` means a later produced effect removed it from the active support set. `inactive_rejected` means the producing step was rejected, so the effect is preserved historically but never entered the active support set.

If no support is found, the requirement is recorded as missing. A step is `accepted` only when no requirements are missing and its confidence meets `validation.tau_acc` from `config/thesis_rules.yaml`. A step with partial support and confidence above `validation.tau_unc` is marked `uncertain`. Compatibility constraints still act as hard violations and mark a step `rejected`.

Layer 4 propagates rule coverage warnings and effect lifecycle provenance into `validation_records.jsonl`, `step_validations.csv`, and `explanation_traces.json`. A step with meaningful evidence but no applicable Layer 3 rule is marked `uncertain` rather than silently accepted, unless a separate hard incompatibility rejects it. Validation records expose this through `warnings`, `diagnostics.rule_coverage`, `has_rule_coverage`, `matched_rule_count`, `produced_constraint_count`, `has_expected_effect`, `unsupported_action`, `unsupported_action_name`, `invalidated_effects`, and `produced_effect_lifecycle`.

## Procedural Reasoning Graph

The `procedural_reasoning_graph` is the reasoning-enriched procedural representation produced after Layer 3 inference and Layer 4 validation. It is separate from the upstream assembly/Neo4j graph: the upstream graph represents exported source events and component relations, while `procedural_reasoning_graph` represents validated steps, predicate evidence, inferred constraints, rule provenance, dependency support, missing requirements, and explanation traces.

The primary graph-builder input is:

```text
validation_records.jsonl
```

Optional inputs such as `step_records.jsonl`, `predicates.jsonl`, and `inferred_constraints.csv` are accepted by the script. The current builder uses `step_records.jsonl` for Step metadata enrichment and relies on `validation_records.jsonl` for validation status, predicate evidence, constraint evidence, produced effects, produced-effect lifecycle, dependency support, missing requirements, incompatibilities, and trace information. When `--step-records` is provided, Step nodes are enriched with source metadata from the adapter step records, including `clip_result_id`, `run_id`, `mode`, `archive_name`, and `clip`.

The builder also accepts config provenance inputs:

```text
--domain-config config/domain_config.yaml
--rules config/thesis_rules.yaml
--validation-config config/thesis_rules.yaml
```

These files are not prompt context and are not copied into every node. They are summarized in graph-level provenance so later evaluations and experiment reports can verify which domain and rule versions produced a graph.

The graph JSON has this shape:

```json
{
  "schema_version": "1.0",
  "graph_name": "procedural_reasoning_graph",
  "provenance": {
    "built_at": "2026-06-30T12:00:00+02:00",
    "builder": "src.procedural_reasoning_graph.build_procedural_reasoning_graph",
    "graph_schema_version": "1.0",
    "source_files": {
      "domain_config": {
        "path": "config/domain_config.yaml",
        "sha256": "...",
        "domain_model_version": "..."
      },
      "thesis_rules": {
        "path": "config/thesis_rules.yaml",
        "sha256": "...",
        "rule_set_version": "..."
      },
      "validation_config": {
        "path": "config/thesis_rules.yaml",
        "sha256": "...",
        "rule_set_version": "..."
      }
    },
    "input_artifacts": {
      "validations": {"path": "...", "sha256": "..."},
      "step_records": {"path": "...", "sha256": "..."},
      "predicates": {"path": "...", "sha256": "..."},
      "constraints": {"path": "...", "sha256": "..."}
    }
  },
  "nodes": [],
  "edges": []
}
```

`provenance.built_at` uses local time with an explicit UTC offset. Hashes are SHA-256 hashes of the files used at graph-build time. If an existing graph predates this metadata, evaluation and experiment reports state that graph provenance is unavailable and recommend rebuilding the graph.

The graph builder also writes:

```text
procedural_reasoning_graph_nodes.csv
procedural_reasoning_graph_edges.csv
```

Node types:

```text
Step        one node per validation record
Predicate   predicate evidence from evidence_predicates / trace.predicate_evidence
Constraint  inferred/validated constraints from evidence and requirement fields
Rule        rule_id provenance from constraints
Entity      object/tool/workspace/material arguments extracted from predicates and constraints
Source      predicate source file/field provenance
```

All nodes include display-oriented properties for Neo4j Aura captions:

```text
display_name   short readable caption, such as Step 2 or requires installed
display_label  slightly richer caption, such as Step 2 [uncertain]
short_id       compact source identifier when available
```

These fields are presentation helpers only. They do not change node ids, relationships, validation status, confidence, provenance, or reasoning semantics.

Step nodes also expose source-clip metadata when the graph is built with `--step-records`. In the IndustReal sample graph, each Step node includes:

```text
clip_result_id: raw_cad_dataset__all_test_clips::od_only::test_p1::03_assy_0_1
run_id: raw_cad_dataset__all_test_clips
mode: od_only
archive_name: test_p1
clip: 03_assy_0_1
```

Step nodes also expose validation diagnostics when present:

```text
warning_count
warnings
has_rule_coverage
matched_rule_count
produced_constraint_count
has_expected_effect
unsupported_action
unsupported_action_name
invalidates_effect_count
invalidated_effects
```

For the sample remove step, these properties make the graph visibly show which installed effect was invalidated by the remove action.

Produced-effect Constraint nodes expose lifecycle fields when Layer 4 provides them:

```text
effect_lifecycle_status: active | invalidated | inactive_rejected
invalidated_by_constraint_id
```

For example, an earlier `produces(installed, wheel, hub)` Constraint can be marked `effect_lifecycle_status="invalidated"` and `invalidated_by_constraint_id` can point to the later `produces(removed, wheel, hub)` Constraint.

The graph also materializes this relationship with an `INVALIDATED_BY` edge between Constraint nodes:

```text
(:Constraint {name: "produces", effect_lifecycle_status: "invalidated"})
  -[:INVALIDATED_BY]->
(:Constraint {name: "produces"})
```

The edge direction reads as "this produced effect was invalidated by that produced effect." The invalidating step and invalidating effect details are intentionally not duplicated on the invalidated node; they can be reached by following `INVALIDATED_BY` to the invalidating Constraint and then following the incoming `PRODUCES` edge back to its Step.

Edge types:

```text
NEXT            Step -> Step ordered by validation index
HAS_PREDICATE   Step -> Predicate
HAS_CONSTRAINT  Step -> Constraint
USES            Step -> Entity from usesObject / usesTool predicates
PRODUCES        Step -> Constraint for produced_effects
REQUIRES        Step -> Constraint for requires / requiresTool / requiresSafety
DEPENDS_ON      later Step -> earlier Step when a requirement is supported by a previous produced effect
SUPPORTED_BY    Constraint -> Predicate or Constraint support evidence
INVALIDATED_BY  invalidated produced-effect Constraint -> invalidating produced-effect Constraint
DERIVED_FROM    Constraint -> Rule and Predicate -> Source
HAS_ENTITY      Predicate or Constraint -> Entity
```

Neo4j import uses only the semantic node type as the Neo4j label for procedural graph nodes:

```text
Step
Predicate
Constraint
Rule
Entity
Source
```

The importer does not add a generic `ProceduralReasoningGraph` or `ProceduralReasoningGraphNode` label to every graph node. Graph-level identity is kept as node and relationship properties, especially `graph_name` and `schema_version`, so imported nodes can still be queried by graph name without cluttering the Aura visualization labels.

For the all-clips rebuild/import wrapper, `graph_name` is per clip:

```text
procedural_reasoning_graph::<clip_result_id>
```

For example:

```text
procedural_reasoning_graph::raw_cad_dataset__all_test_clips::od_only::test_p1::03_assy_0_1
```

The Neo4j importer also creates or updates one `GraphManifest` node per imported graph:

```text
(:GraphManifest {graph_name, prg_id, built_at, builder, graph_schema_version, ...})
```

`GraphManifest` stores flattened graph provenance fields such as `domain_model_version`, `rule_set_version`, `domain_config_sha256`, `thesis_rules_sha256`, and `validation_config_sha256`, plus the full provenance payload as a JSON property. This node is intended for freshness checks and experiment/evaluation reporting; it is not part of the procedural step sequence itself.

Accepted, uncertain, and rejected steps are included by default. `--exclude-rejected` omits rejected steps. Rejected steps are not allowed to support later `DEPENDS_ON` edges. Uncertain steps may support later dependencies, but those dependency edges are marked `provisional=true`.

## Current Output Contract

Current predicate records include:

```text
schema_version
record_type
id
step_id
name
predicate_key
category
args
conf
source
notes
```

`name` is the configured predicate name used by Layer 3 matching.

`predicate_key` is the stable adapter key used to trace the predicate back to the adapter extraction path.

`category` comes from the config grouping under `adapter.predicates`.

`source` records which CSV file and fields produced the predicate.

The reasoning-record contract is stable: the adapter writes `step_records.jsonl` and `predicates.jsonl`, Layer 3 writes `inferred_constraints.csv` plus `rule_coverage_diagnostics.csv`, and Layer 4 writes `validation_records.jsonl` plus human/debug views in `step_validations.csv`, `explanation_traces.json`, and `effect_history_diagnostics.csv`. Validation records include requirement support, missing requirements, dependency support, `invalidated_effects`, and `produced_effect_lifecycle`. The procedural graph export writes JSON plus node/edge CSV files, and node properties include presentation helpers such as `display_name`, `display_label`, and `short_id`. The graph JSON also includes graph-level provenance, and Neo4j imports expose the same provenance through `GraphManifest`.

Configured domain components use the domain individual `name` in predicate arguments, such as `base`, while generic classes stay class-like, such as `Base` or `Chassis`. Labels remain separate through `hasLabel(base, "base")`.

## Domain Configuration

Component-specific assembly knowledge is stored separately in:

```text
config/domain_config.yaml
```

This file maps source component ids to generic assembly roles and relations:

```text
component id/name
generic type
parent component
expected installation target
required tool
required assembly conditions
safety requirements
```

For example, the config maps both `front_chassis` and `rear_chassis` to `Chassis`, and maps chassis pins to `ChassisPin` with their parent chassis as the installation target.

The domain config now also carries lightweight ontology-style metadata:

```text
type_hierarchy
type_defaults
condition_vocabulary
predicate_aliases
```

`type_hierarchy` makes generic classes explicit. The adapter emits the configured class and its parents, for example `isA(front_bracket_screw, Screw)`, `isA(front_bracket_screw, Fastener)`, and `isA(front_bracket_screw, Component)`.

`type_defaults` provides inherited fields for components of a generic type.
`ChassisPin`, `Screw`, and `WheelAssembly` define the mechanically scoped
`aligned($self, $installation_target)` requirement, `Screw` defines
`required_tool: screwdriver`, and `ChassisPin` defines securing requirements
shared by all chassis pins. Alignment is intentionally not inherited by every
`Component`; placement-like `Chassis` and `Bracket` installations do not receive
a separate hard alignment requirement unless configured explicitly.

Component fields override inherited defaults in
`src/layer3_reasoning_adapter.py` when `_effective_domain_entry` applies the
component entry after resolving its type defaults. An override replaces the
complete field value; lists are not merged. The base has no alignment
requirement because neither `Base` nor the generic `Component` type defines one.

`condition_vocabulary` controls condition names and arities used by `required_conditions` and `safety_requirements`. The adapter validates those configured conditions at load time and raises a clear error for unknown names or wrong argument counts.

The adapter materializes this domain config into predicates such as:

```text
isA(component, Chassis)
isA(component, Component)
hasInstallTarget(component, target)
observedInstallTarget(step, component, observed_target)
allowsDomainAssumedInstallTarget(step, component)
requiresInstalledBefore(component, target, support)
hasParentComponent(component, parent)
hasRequiredCondition(component, aligned, component, target)
hasSafetyRequirement(component, secured, base, workspace)
hasRequiredTool(component, screwdriver)
```

Layer 3 rules then match these generic predicates. The rule engine does not hardcode specific component names or read `domain_config.yaml` directly; object-specific knowledge from that file reaches Layer 3 indirectly through the predicates materialized by the adapter.

The `implicit_domain_required_condition` rule matches installed objects typed as
`Component` and consumes their materialized `hasRequiredCondition` predicates.
The rule remains generic, but only component types that actually materialize a
`hasRequiredCondition` predicate produce an implicit alignment constraint. In
the current domain model, this means `ChassisPin`, `Screw`, and
`WheelAssembly`.

In principle, this domain config can be generated from CAD metadata. A CAD-derived generator could inspect assembly hierarchy, mating constraints, fastener relationships, component names, and contact/constraint graphs to propose generic types, parent components, installation targets, and required tools. The current file is manually authored from the exported IndustReal component list.

## Practical Commands

### Rebuild all clip/mode reasoning outputs and update Neo4j

Use the all-clips wrapper when rule, domain, observation-contract, adapter, validation, or graph-export behavior has changed and the whole reasoning corpus should be regenerated. This is the preferred command before reporting dataset-level reasoning-layer evaluation numbers or refreshing Aura after a rule update.

From the repository root:

```powershell
.venv\Scripts\python.exe scripts\25_rebuild_all_reasoning_and_import_neo4j.py
```

The wrapper reads unique `clip_result_id` values from:

```text
results\neo4j\raw_cad_dataset__all_test_clips\nodes_events.csv
```

For each discovered clip/mode result, it writes or overwrites:

```text
results\reasoning_layers\<sanitized_clip_result_id>\
  step_records.jsonl
  predicates.jsonl
  inferred_constraints.csv
  rule_coverage_diagnostics.csv
  validation_records.jsonl
  step_validations.csv
  explanation_traces.json
  effect_history_diagnostics.csv

results\procedural_reasoning_graph\<sanitized_clip_result_id>\
  procedural_reasoning_graph.json
  procedural_reasoning_graph_nodes.csv
  procedural_reasoning_graph_edges.csv
```

`<sanitized_clip_result_id>` is the CSV `clip_result_id` with `::` replaced by `__`. For example:

```text
raw_cad_dataset__all_test_clips::od_only::test_p1::03_assy_0_1
```

is written under:

```text
raw_cad_dataset__all_test_clips__od_only__test_p1__03_assy_0_1
```

Neo4j import is intentionally delayed until all local rebuilds succeed. If any adapter, Layer 3, Layer 4, or graph-builder command fails, the script stops and does not update Aura. After a successful local rebuild, each procedural graph is imported with a graph name derived from its clip/result id:

```text
procedural_reasoning_graph::<clip_result_id>
```

Before importing a graph, the importer clears only existing nodes and relationships with the same `graph_name`. This replaces stale data for rebuilt clips without deleting other imported clip/mode graphs.

The Neo4j import step requires `NEO4J_URI` and `NEO4J_PASSWORD` in `.env` unless a different env file is passed:

```powershell
.venv\Scripts\python.exe scripts\25_rebuild_all_reasoning_and_import_neo4j.py `
  --env-file path\to\.env
```

Useful execution modes:

```powershell
# Print all commands without rebuilding or importing.
.venv\Scripts\python.exe scripts\25_rebuild_all_reasoning_and_import_neo4j.py --dry-run

# Rebuild local artifacts only; do not import to Neo4j.
.venv\Scripts\python.exe scripts\25_rebuild_all_reasoning_and_import_neo4j.py --skip-import

# Rebuild and import one selected clip/mode result.
.venv\Scripts\python.exe scripts\25_rebuild_all_reasoning_and_import_neo4j.py `
  --clip-result-id raw_cad_dataset__all_test_clips::od_only::test_p1::03_assy_0_1

# Rebuild all clips for a different run id and matching Neo4j CSV export root.
.venv\Scripts\python.exe scripts\25_rebuild_all_reasoning_and_import_neo4j.py `
  --run-id raw_cad_dataset__all_test_clips `
  --csv-dir results\neo4j\raw_cad_dataset__all_test_clips
```

The wrapper uses the current Python interpreter for all child scripts. Therefore, invoke it with `.venv\Scripts\python.exe` so the repository virtual environment is used consistently.

### Single-clip manual commands

Build adapter outputs for a filtered clip:

```powershell
.venv\Scripts\python.exe scripts\14_build_layer3_reasoning_adapter.py `
  --clip-result-id raw_cad_dataset__all_test_clips::od_only::test_p1::03_assy_0_1 `
  --output-dir results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1
```

Run Layer 3 inference:

```powershell
.venv\Scripts\python.exe scripts\15_run_layer3_inference.py `
  --step-records results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\step_records.jsonl `
  --predicates results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\predicates.jsonl `
  --output results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\inferred_constraints.csv
```

This also writes:

```text
results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\rule_coverage_diagnostics.csv
```

Run Layer 4 validation:

```powershell
.venv\Scripts\python.exe scripts\16_run_layer4_validation.py `
  --step-records results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\step_records.jsonl `
  --predicates results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\predicates.jsonl `
  --constraints results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\inferred_constraints.csv `
  --rule-coverage results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\rule_coverage_diagnostics.csv `
  --output results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\validation_records.jsonl
```

Build the procedural reasoning graph:

```powershell
.venv\Scripts\python.exe scripts\17_build_procedural_reasoning_graph.py `
  --validations results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\validation_records.jsonl `
  --step-records results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\step_records.jsonl `
  --predicates results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\predicates.jsonl `
  --constraints results\reasoning_layers\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1\inferred_constraints.csv `
  --domain-config config\domain_config.yaml `
  --rules config\thesis_rules.yaml `
  --validation-config config\thesis_rules.yaml `
  --graph-name procedural_reasoning_graph::raw_cad_dataset__all_test_clips::od_only::test_p1::03_assy_0_1 `
  --output-dir results\procedural_reasoning_graph\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1
```

Import the procedural reasoning graph into Neo4j:

```powershell
.venv\Scripts\python.exe scripts\18_import_procedural_reasoning_graph_neo4j.py `
  --graph results\procedural_reasoning_graph\raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1 `
  --graph-name procedural_reasoning_graph::raw_cad_dataset__all_test_clips::od_only::test_p1::03_assy_0_1
```

Build the browser UI graph data from the IndustReal result JSON files and Neo4j CSV export:

```powershell
.venv\Scripts\python.exe scripts\19_build_graph_data_js.py `
  --neo4j-dir results\neo4j\raw_cad_dataset__all_test_clips `
  --results-dir results `
  --output ..\platform\data\graph-data.js
```

The default output path is also `..\platform\data\graph-data.js` relative to this repository. Override `--run-id`, `--mode`, or `--archive` when building UI data for a different Neo4j export or result naming convention.

Verify Neo4j labels after import:

```cypher
MATCH (n)
RETURN labels(n) AS labels, count(*) AS count
ORDER BY count DESC;
```

```cypher
MATCH (n)
WHERE n.graph_name = "procedural_reasoning_graph::raw_cad_dataset__all_test_clips::od_only::test_p1::03_assy_0_1"
RETURN labels(n) AS labels, count(*) AS count
ORDER BY count DESC;
```

Expected label combinations are single semantic labels such as `["Step"]`, `["Constraint"]`, `["Predicate"]`, `["Rule"]`, `["Entity"]`, and `["Source"]`. A `["GraphManifest"]` node is also expected for each imported graph.

Verify display properties after import:

```cypher
MATCH (s:Step)
WHERE s.graph_name = "procedural_reasoning_graph::raw_cad_dataset__all_test_clips::od_only::test_p1::03_assy_0_1"
RETURN s.display_name, s.display_label, s.status, s.confidence
ORDER BY s.index;
```

Verify graph provenance after import:

```cypher
MATCH (m:GraphManifest)
RETURN
  m.graph_name,
  m.built_at,
  m.graph_schema_version,
  m.domain_model_version,
  m.rule_set_version,
  m.domain_config_sha256,
  m.thesis_rules_sha256,
  m.validation_config_sha256
ORDER BY m.graph_name;
```

Use a different predicate/rule config:

```powershell
.venv\Scripts\python.exe scripts\14_build_layer3_reasoning_adapter.py --predicate-config path\to\custom_rules.yaml
```

Use a different domain config:

```powershell
.venv\Scripts\python.exe scripts\14_build_layer3_reasoning_adapter.py --domain-config path\to\domain_config.yaml
```

## Notes For Future README Integration

This implementation currently treats the reasoning adapter as a downstream bridge from the existing graph export to thesis-style reasoning records.

The most important design point is the separation between:

```text
upstream evidence
  what the existing pipeline exports

adapter predicates
  symbolic facts derived from that evidence

Layer 3 rules
  procedural constraints inferred from symbolic facts
```

That separation is useful because it keeps provenance clear. If a later layer derives a constraint, it can be traced back to the rule, the matched predicates, and the original CSV fields that produced those predicates.
