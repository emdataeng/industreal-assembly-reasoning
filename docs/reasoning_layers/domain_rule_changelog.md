# Domain Model and Rule Set Changelog

This document records semantic changes to:

- `config/domain_config.yaml`
- `config/thesis_rules.yaml`
- Supporting code that resolves domain expressions or converts explicit evidence into predicates

Git remains the source of truth for exact file changes. This changelog explains why
the reasoning semantics changed, what evidence is expected, and how generated
artifacts may be affected.

## Versioning

The domain model and rule set are versioned independently using semantic
versioning:

- **Patch**: descriptions, documentation, or corrections that do not change
  reasoning outcomes.
- **Minor**: backward-compatible predicates, requirements, resolvers, or rules
  that can produce new reasoning outcomes.
- **Major**: incompatible semantic changes, removed concepts, or changed meanings
  of existing predicates and constraints.

Current versions:

- Domain model: `1.3.0`
- Rule set: `1.3.0`

## 2026-06-26 — Scope alignment to mechanically alignment-sensitive component types

Versions:

- Domain model: `1.3.0`
- Rule set: `1.3.0`

Decision record:

- [`ADR-004: Scope Alignment Requirements to Mechanically Alignment-Sensitive Types`](decisions/ADR-004-scope-alignment-requirements.md)

### Changed

- Removed the generic alignment requirement from `type_defaults.Component`.
- Added `aligned($self, $installation_target)` to:
  - `ChassisPin`
  - `Screw`
  - `WheelAssembly`
- Left `Chassis` and `Bracket` without a hard alignment requirement by default.

### Rationale

The all-component alignment rule made placement-like chassis and bracket
installations uncertain unless separate alignment evidence existed. Alignment is
still treated as a real assembly precondition for insertion, fastening, and
interface-fit operations such as pins, screws, and wheel assemblies.

### Impact

- Fewer installation steps produce implicit `aligned(...)` requirements.
- Acceptance ratios can increase after rebuilding artifacts because `Chassis`
  and `Bracket` installations are no longer blocked by missing alignment
  support.
- Existing Layer 3, Layer 4, procedural-reasoning graph, and evaluation
  artifacts must be rebuilt.
- The Layer 3 rule remains generic: it consumes materialized
  `hasRequiredCondition` predicates and therefore only fires for types that
  still configure those requirements.

### Verification

- Updated `tests/test_layer3_ontology_config.py` to verify the new alignment
  scope and adjusted inferred-constraint counts.

## 2026-06-25 — Observed installation-target grounding

Versions:

- Domain model: `1.2.0`
- Rule set: `1.3.0`
- Observation contract: `1.0.0`

Decision record:

- [`ADR-003: Separate Observed and Expected Installation Targets`](decisions/ADR-003-observed-installation-target-grounding.md)

### Added

- Added the source-independent `config/observation_contract.yaml`.
- Added optional canonical event fields for an independently observed target,
  confidence, and source type.
- Added `observedInstallTarget(step, component, target)`.
- Added `allowsDomainAssumedInstallTarget(step, component)` for explicit
  backward-compatible fallback.
- Added reusable `equal` and `not_equal` Layer 3 rule guards.
- Added `incompatibleInstallationTarget(step, component, observed, expected)`.

### Changed

- Matching observed and expected targets now produce installation effects through
  `effect_install_component_on_observed_target`.
- Conflicting targets produce a compatibility constraint and Layer 4 rejection.
- The existing `effect_install_component_on_target` rule now runs only when the
  adapter explicitly permits domain-assumed fallback.

### Backward compatibility

The default policy is:

```text
missing_observation_policy: domain_assumed
```

Current IndustReal events do not contain observed target fields. They therefore
continue to receive domain-inferred installation effects as before.

The optional `require_observed` policy disables that fallback when experiments
need stricter target grounding.

### Impact

- Adapter and downstream reasoning artifacts must be regenerated.
- The domain model version remains `1.2.0` because expected target knowledge did
  not change.
- Rule provenance now distinguishes observed-target confirmation from
  domain-assumed fallback.

### Verification

- Added focused tests for matching targets, conflicting targets, missing
  observations, Layer 4 rejection, and the `require_observed` policy.

## 2026-06-25 — Alignment for all non-base components

Superseded by the 2026-06-26 alignment-scope change. This entry records the
earlier all-component alignment model for traceability.

Versions:

- Domain model: `1.2.0`
- Rule set: `1.2.0`

Decision record:

- [`ADR-002: Require Alignment for Every Non-Base Component Installation`](decisions/ADR-002-align-all-installed-components.md)

### Changed

- Moved the generic alignment requirement from `ChassisPin` to the `Component`
  type default:

  ```text
  aligned($self, $installation_target)
  ```

- Added an explicit empty `required_conditions` override for
  `industreal_component::base`.
- Generalized `implicit_domain_required_condition` from `ChassisPin` to
  `Component`.
- Kept chassis-pin securing requirements scoped to `ChassisPin`.

### Rationale

Alignment is a general precondition for installing one assembly component onto
another. The base is excluded because it establishes the assembly reference in
the workspace.

The adapter resolves type defaults first and then applies component fields.
Consequently, the base's empty list replaces the inherited alignment list.

### Impact

- Every non-base install step can now produce an implicit
  `requires(..., aligned, component, installation_target)` constraint.
- Existing generated reasoning artifacts must be rebuilt.
- In the ontology integration sample, the number of constraints produced by
  `implicit_domain_required_condition` increases from 3 to 9.

### Verification

- Updated `tests/test_layer3_ontology_config.py` to cover inherited alignment,
  the base override, representative component types, and expanded inference.

## 2026-06-24 — Explicit chassis securing

Versions:

- Domain model: `1.1.0`
- Rule set: `1.1.0`

Decision record:

- [`ADR-001: Model Securing as an Explicitly Observed Effect`](decisions/ADR-001-explicit-securing-evidence.md)

### Changed

- Added a generic `ChassisPin` safety requirement:

  ```text
  secured($installation_target, $installation_target_target)
  ```

- Added the `$installation_target_target` domain argument resolver.
- Added configurable `observed_effects` for components and component types.
- Added the `hasObservedEffect` predicate.
- Added the `effect_explicitly_observed_condition` rule, which converts an
  explicitly annotated observation into a produced effect.
- Configured `Chassis` annotations containing `secure`, `secured`, or `securing`
  to produce:

  ```text
  secured(chassis, chassis_installation_target)
  ```

### Annotation example

```text
Install and secure rear chassis
```

This produces:

```text
installed(rear_chassis, base)
secured(rear_chassis, base)
```

A plain annotation such as:

```text
Install rear chassis
```

produces only:

```text
installed(rear_chassis, base)
```

### Rationale

Installation and securing are distinct facts. A component must not be considered
secured merely because it was installed. Securing therefore requires explicit
annotation evidence.

The generic target-of-target expression allows every `ChassisPin` to require its
particular installation target to have been secured to that target's own support.
For example:

- `front_chassis_pin` requires `secured(front_chassis, base)`.
- `front_rear_chassis_pin` requires `secured(rear_chassis, base)`.
- `rear_rear_chassis_pin` requires `secured(rear_chassis, base)`.

### Impact

- Existing Layer 3, Layer 4, and procedural-reasoning graph artifacts must be
  rebuilt to use these semantics.
- Chassis-pin installation steps can have an additional missing safety
  requirement when no prior explicit securing observation exists.
- Editing an experiment step-list text file does not alter source graph evidence.
  The explicit wording must be present in the upstream event `action_desc`.

### Verification

- Added coverage in `tests/test_layer3_ontology_config.py`.
- Full test suite result at implementation time: `128 passed`.

## Pre-changelog — Remove semantics and the produced-effect lifecycle

Recorded retrospectively on 2026-07-16. This change predates the adoption of
this changelog and semantic versioning; it was implemented on or before
2026-05-18 (the Evaluation 1 run that exercised it end-to-end) and is part of
every versioned rule set since.

Decision record:

- [`ADR-005: Remove Semantics and the Produced-Effect Lifecycle`](decisions/ADR-005-remove-semantics-and-effect-lifecycle.md)

### Added

- Two generic Layer 3 rules covering `remove` actions:
  - `precondition_remove_requires_component_installed`, producing
    `requires(step, installed, component, target)`.
  - `effect_remove_component_from_target`, producing
    `produces(step, removed, component, target)`.
- The Layer 4 produced-effect lifecycle (`effect_lifecycle_status`):
  `active`, `invalidated`, and `inactive_rejected`. Only active effects can
  support later requirements; invalidated and rejected-step effects are
  retained for traceability.
- `invalidated_effects` on validation records and traces, and the
  `effect_history_diagnostics.csv` export.

### Rationale

Remove events in the IndustReal data produced predicates that no rule
consumed, surfacing as `no_applicable_rule` coverage diagnostics. The
observations were correct; the knowledge model was incomplete. Without remove
semantics, an `installed(...)` effect also continued to support later steps
after the component had been removed.

### Impact

- Remove steps receive requirements, effects, and rule provenance like any
  other step.
- Later steps can no longer be supported by installation effects that a
  removal has invalidated.
- Evidence: `Evaluation1_remove_semantics/` reports.
