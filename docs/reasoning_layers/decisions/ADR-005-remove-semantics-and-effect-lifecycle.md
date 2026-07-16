# ADR-005: Remove Semantics and the Produced-Effect Lifecycle

- Status: Accepted
- Date decided: on or before 2026-05-18 (timestamp of the Evaluation 1 run that
  exercised these semantics end-to-end)
- Date recorded: 2026-07-16
- Domain model version: predates `1.1.0` (pre-changelog)
- Rule set version: predates `1.1.0` (pre-changelog); the rules are present in
  the current `1.3.0` rule set

> Recorded retrospectively. This decision predates the adoption of ADRs and the
> domain/rule changelog in this project. It was originally documented in the
> thesis report and in the evaluation evidence under
> `docs/reasoning_layers/Evaluation1_remove_semantics/`.

## Context

IndustReal executions contain `remove` actions (for example,
`Remove front wheel assy`), reflecting disassembly and error-recovery behavior
in real assembly recordings.

The initial rule set covered installation-oriented semantics only. Remove
events therefore produced symbolic predicates that no Layer 3 rule consumed,
which surfaced as `no_applicable_rule` rows in
`rule_coverage_diagnostics.csv`. The diagnostics made two gaps explicit:

1. **Layer 3 coverage gap.** Remove steps carried real evidence but received no
   procedural semantics: no preconditions, no expected effects, no rule
   provenance.
2. **Layer 4 stale-support problem.** Without removal effects, an
   `installed(component, target)` effect produced by an earlier step remained
   available to support later requirements even after the component had
   visibly been removed. Later steps could be accepted on the basis of state
   that no longer held.

The observations themselves were correct; the knowledge model was the
incomplete side. The decision below gives removal first-class semantics rather
than treating the unmatched evidence as noise.

## Decision

The decision has two parts: generic remove rules in Layer 3, and an explicit
produced-effect lifecycle in Layer 4.

### Layer 3: generic remove rules

Two config-driven rules in `config/thesis_rules.yaml` cover any `Component`
with a configured installation target:

```text
precondition_remove_requires_component_installed
hasAction(step, remove)
usesObject(step, component)
isA(component, Component)
hasInstallTarget(component, target)
  -> requires(step, installed, component, target)
```

```text
effect_remove_component_from_target
hasAction(step, remove)
usesObject(step, component)
isA(component, Component)
hasInstallTarget(component, target)
  -> produces(step, removed, component, target)
```

A remove step is validated like any other step: it requires the component to
be actively installed, and that requirement must be grounded in an earlier
non-rejected step's produced effect.

### Layer 4: produced-effect lifecycle

Layer 4 separates **historical** produced effects from **active** ones. Every
produced effect carries an `effect_lifecycle_status`:

- `active` — produced by a non-rejected step and still available to support
  later requirements.
- `invalidated` — a later `removed(component, target)` effect invalidated the
  matching active `installed(component, target)` effect. The record is kept,
  annotated with the invalidating step and constraint
  (`invalidated_by_constraint_id`), but no longer supports future steps.
- `inactive_rejected` — produced by a rejected step; never becomes available
  as support.

Only active effects can satisfy later requirements. Historical effects remain
in validation records, explanation traces, and
`effect_history_diagnostics.csv` for audit.

## Alternatives Considered

### Treat remove events as noise and drop them

Rejected. The evidence was real: removal is part of the recorded assembly
process. Dropping the events would leave steps permanently unexplained,
keep the coverage diagnostics noisy, and hide the stale-support problem
instead of solving it.

### Give remove steps validation status but no effect semantics

Rejected. This closes the Layer 3 coverage gap but not the Layer 4 one: an
installed effect would continue to support later steps after the component was
removed, producing unsupported acceptances.

### Delete invalidated effects from the effect history

Rejected. Deleting state breaks end-to-end traceability. An auditor must be
able to see that an effect existed, when it stopped holding, and which step
invalidated it. Retention with an explicit lifecycle status preserves both
correctness and auditability.

### Full temporal state retraction

Not selected. Invalidation is deliberately scoped to `installed` effects
matched by a `removed` effect on the same component and target. Retracting
derived conditions (for example, `secured` or `aligned` states that depended
on the removed component) would require a broader temporal state model than
the thesis scope justified. The scope note in
`Evaluation1_remove_semantics/layer3_remove_rule_check.md` records this
boundary explicitly.

## Consequences

### Positive

- Remove steps receive requirements, effects, and rule provenance like any
  other step; `rule_coverage_diagnostics.csv` reports full coverage
  (`matched_rule_count: 2`, no warning code) for remove actions.
- Stale support is eliminated: later steps cannot depend on an installation
  that a removal has invalidated.
- The full effect history is preserved for audit; invalidation is itself
  traceable to the invalidating step and constraint.
- The lifecycle mechanism generalizes beyond removal: effects of rejected
  steps are carried as `inactive_rejected` under the same field.
- The rules are generic over `Component`; no per-component configuration was
  needed.

### Costs and limitations

- Invalidation covers only `installed` effects. Derived conditions that
  depended on the removed component are not retracted.
- Matching is exact on the (component, installation target) pair; it relies on
  the domain model's `hasInstallTarget` knowledge.
- Existing Layer 3, Layer 4, and procedural-reasoning graph artifacts must be
  rebuilt when these semantics change.

## Implementation

The decision is implemented through:

- `config/thesis_rules.yaml`
  - `precondition_remove_requires_component_installed`
  - `effect_remove_component_from_target`
- `src/layer4_validation.py`
  - Active vs. historical effect tracking and `effect_lifecycle_status`.
  - Invalidation of matching active installed effects, recorded in
    `invalidated_effects` on validation records and traces.
  - `effect_history_diagnostics.csv` export.
- `src/procedural_reasoning_graph.py`
  - Lifecycle status and `INVALIDATED_BY` relations exported to the graph.
- `tests/test_layer4_validation.py`
  - Coverage of invalidation and lifecycle behavior.

Evaluation evidence:

- `docs/reasoning_layers/Evaluation1_remove_semantics/` — end-to-end artifact
  checks including the remove rule and remove validation reports.
- Evaluation 3 (validation behavior) exercises invalidation as one of its five
  checked behaviors.

## Follow-up

- Consider retracting derived conditions (for example, `secured`) whose
  supporting installation has been invalidated.
- Consider generalizing the lifecycle to other state-retracting actions if
  future datasets model them.
