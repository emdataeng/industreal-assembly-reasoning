# Architecture

This document describes the system design behind the reasoning layer: the data contracts between stages, the rule and validation semantics, the graph model, and the reasoning behind the major design decisions. For hands-on integration detail (exact CLI flags, field lists, Cypher queries), see [current_pipeline_integration.md](reasoning_layers/current_pipeline_integration.md).

## Design principles

Three commitments shape everything else:

1. **Every stage boundary is a file.** Each pipeline stage reads structured records from disk and writes structured records to disk. There is no shared in-memory state between stages, no hidden caches, and no learning. Given the same inputs and configuration, output is byte-identical in content.
2. **Evidence and inference are never mixed.** Predicates represent what was stated, observed, or configured. Constraints represent what rules *inferred* from predicates. Validation records represent decisions over both. Each record type carries provenance back to the layer below.
3. **Knowledge lives in configuration, mechanism lives in code.** The rule engine and validator are generic; everything IndustReal-specific (component names, install targets, tools, safety conditions) is declarative config that the adapter materializes into predicates.

## Stage-by-stage data flow

![Implemented pipeline and artifacts](reasoning_layers/Implemented_layout_white_bkgrnd.png)

*Each stage reads the previous stage's files and writes its own: the adapter (`layer3_reasoning_adapter.py`) turns the upstream CSVs into `step_records.jsonl` + `predicates.jsonl`; Layer 3 (`layer3_inference.py`) writes `inferred_constraints.csv` + `rule_coverage_diagnostics.csv`; Layer 4 (`layer4_validation.py`) writes `validation_records.jsonl`, `step_validations.csv`, `explanation_traces.json`, and `effect_history_diagnostics.csv`; the graph builder (`procedural_reasoning_graph.py`) exports `procedural_reasoning_graph.json` + node/edge CSVs, which `procedural_neo4j_import.py` loads into Neo4j.*

Configuration inputs (not shown above): `config/thesis_rules.yaml` feeds the adapter (predicate vocabulary) and Layer 3 (aliases, thresholds, rules); `config/domain_config.yaml` feeds only the adapter; `config/observation_contract.yaml` defines optional observed-target fields and the missing-observation policy.

### Adapter: upstream CSVs → symbolic records

The adapter is the boundary between the companion thesis's output and this reasoning stack. Per assembly event it emits one **step record** (identifier, sequence index, time window, source metadata) and a set of **predicates** — each a typed fact with a name, arguments, confidence in `[0,1]`, and a `source` field naming the upstream CSV file and columns it came from.

Three predicate categories are configured under `adapter.predicates`:

| Category | Examples | Derived from |
|---|---|---|
| `event` | `hasAction(step, install)` | `nodes_events.csv` action fields |
| `object_interaction` | `usesObject(step, component)` | `edges_event_component.csv` |
| `entity_metadata` | `isA(comp, Screw)`, `hasInstallTarget(comp, target)`, `hasRequiredTool(comp, screwdriver)` | `nodes_components.csv` + `domain_config.yaml` |

The key move: the adapter *materializes domain knowledge as predicates*. `domain_config.yaml` maps each configured IndustReal component to a generic type from a 10-type hierarchy (`ChassisPin → Fastener → Component`), an expected installation target, required tools, required conditions, and safety requirements. Type defaults let common knowledge be written once (`Screw` ⇒ `required_tool: screwdriver`), with per-component overrides. A condition vocabulary validates names and arities at load time — an unknown condition is a config error, not silent nonsense downstream.

Because domain knowledge arrives as ordinary predicates, Layer 3 rules stay fully generic.

### Layer 3: rule-based constraint inference

Rules live in `config/thesis_rules.yaml` (`rule_set_version: 1.3.0`, 11 rules) across six categories:

| Category | Emits | Role in validation |
|---|---|---|
| `inferred_precondition` | `requires(...)` | Must be supported by evidence or earlier effects |
| `expected_effect` | `produces(...)` | Enters the effect history; supports later steps |
| `safety_constraint` | `requiresSafety(...)` | Requirement; e.g. base secured before pin install |
| `required_tool` | `requiresTool(...)` | Requirement; e.g. screwdriver for screws |
| `implicit_assembly_condition` | `requires(...)` | e.g. alignment for pins/screws/wheel assemblies |
| `compatibility` | `incompatibleAction(...)` | **Hard violation** — rejects the step outright |

A rule is a conjunction of antecedent predicate patterns with variables (`?s`, `?component`), an activation threshold, and consequent constraint templates. Evaluation per step: normalize predicate names via the alias map, find all antecedent bindings, aggregate the confidence of each match's supporting predicates with **min**, and instantiate constraints when the threshold is met. Every constraint stores its confidence, `rule_id`, and the supporting predicate ids.

Rules may also declare `equal` / `not_equal` guards over bound variables, evaluated after matching.

**Coverage diagnostics** are a separate output: for each step, did any rule match? A step with meaningful evidence (`hasAction` + `usesObject`/`usesTool`) but zero matched rules gets `warning_code: no_applicable_rule`. This is deliberately diagnostic — the absence of a rule is a statement about the rule base, not about the step's validity.

### Layer 4: ordered validation with effect lifecycle

The validator walks steps in input order, maintaining two views of produced effects:

- **Historical effects** — everything any step produced, kept forever for traceability.
- **Active effects** — the subset currently available to support later requirements.

Per step, requirements (`requires`, `requiresSafety`, `requiresTool`) are checked against same-step predicates and active earlier effects. Then:

```text
incompatibility present                       → rejected
no missing requirements ∧ conf ≥ τ_acc (0.7)  → accepted
partial support        ∧ conf ≥ τ_unc (0.35)  → uncertain
otherwise                                     → rejected
```

Lifecycle rules that make the history sound:

- **Rejected steps never contribute active effects** (`inactive_rejected`). A rejected "install X" cannot make a later "tighten X" look valid.
- **Removal invalidates installation.** An accepted/uncertain step producing `removed(comp, target)` invalidates the matching active `installed(comp, target)` effect (`invalidated`, with `invalidated_by_constraint_id`). The historical record survives; the support does not.
- **Declared ≠ satisfied.** Domain predicates like `hasRequiredCondition(...)` state that a requirement exists and are explicitly excluded as satisfaction evidence — requirements cannot satisfy themselves.
- **Unknown actions stay visible.** A step flagged `no_applicable_rule` is at best `uncertain`, never silently accepted.

Every decision is stored with an explanation trace separating predicate evidence, constraint evidence, dependency evidence, incompatibilities, missing requirements, status, and confidence.

### Observed vs. expected installation targets

Perception may claim where a component actually went (`observed_installation_target`, with confidence and source, defined in `observation_contract.yaml`). The adapter never reconciles this with the domain expectation:

```text
observed == expected   → produces installed(component, observed_target)
observed != expected   → incompatibleInstallationTarget(...) → step rejected
no observation         → policy-controlled: domain_assumed fallback (default)
                         or require_observed (no confirmed effect without observation)
```

Both claims remain independently traceable. See [ADR-003](reasoning_layers/decisions/ADR-003-observed-installation-target-grounding.md).

## Procedural reasoning graph

The exporter turns validation records into a graph with six node types — `Step`, `Predicate`, `Constraint`, `Rule`, `Entity`, `Source` — and eleven edge types:

| Edge | Meaning |
|---|---|
| `NEXT` | Input temporal order (never inferred) |
| `DEPENDS_ON` | A requirement of this step is grounded in an earlier step's produced effect; `provisional=true` when the supporter is uncertain |
| `REQUIRES` / `PRODUCES` | Step → requirement / produced-effect constraints |
| `HAS_PREDICATE` / `HAS_CONSTRAINT` | Step → its evidence |
| `SUPPORTED_BY` | Constraint → the predicates/constraints that support it |
| `DERIVED_FROM` | Constraint → Rule; Predicate → Source |
| `INVALIDATED_BY` | Invalidated produced effect → the removal effect that invalidated it |
| `USES` / `HAS_ENTITY` | Step/predicate/constraint → entity arguments |

The separation of `NEXT` and `DEPENDS_ON` is the graph's core semantic point: adjacency is an observation; dependency is a reasoning result. Two consecutive steps may share no dependency, and a step may depend on a much earlier one.

**Provenance manifest.** Each exported graph embeds SHA-256 hashes and versions of the domain config, rule config, and input artifacts used to build it. The Neo4j importer materializes this as a `GraphManifest` node per graph, so any imported graph can prove which rule/domain versions produced it. Imports are idempotent per `graph_name` (one graph per clip result): re-importing replaces only that clip's nodes and relationships.

Neo4j is intentionally *downstream* of all reasoning — a persistence and inspection layer, never a dependency of the validation semantics.

## Knowledge governance

Rule and domain semantics are treated like code:

- Independent **semantic versioning** for `domain_model_version` and `rule_set_version` (both 1.3.0), with a [changelog](reasoning_layers/domain_rule_changelog.md) explaining *why* each semantic change was made and its expected impact on artifacts.
- **Architecture Decision Records** in [decisions/](reasoning_layers/decisions/) capture the non-obvious calls — including [ADR-002](reasoning_layers/decisions/ADR-002-align-all-installed-components.md), preserved in its superseded state: requiring alignment for *every* component made ordinary chassis placements uncertain, so [ADR-004](reasoning_layers/decisions/ADR-004-scope-alignment-requirements.md) scoped alignment to mechanically alignment-sensitive types (pins, screws, wheel assemblies).

## Testing

22 pytest tests (~1,600 lines) cover the behaviors the design promises: validation status assignment and thresholds, effect lifecycle and removal invalidation, rejected-step isolation, ontology/config validation (type hierarchy, condition vocabulary, overrides), graph construction, and Neo4j import mapping. The tests encode the *semantics* — e.g., "a rejected step's effect must not support a later requirement" — not just I/O plumbing.
