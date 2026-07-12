# ADR-002: Require Alignment for Every Non-Base Component Installation

- Status: Superseded by ADR-004
- Date: 2026-06-25
- Domain model version: `1.2.0`
- Rule set version: `1.2.0`

## Context

> Superseded note: ADR-004 narrows the alignment requirement from all non-base
> component types to `ChassisPin`, `Screw`, and `WheelAssembly`. This record is
> retained to document the earlier all-component alignment decision.

The domain model previously defined `aligned(component, installation_target)` as
a required condition only for `ChassisPin`. The corresponding Layer 3 rule also
required the installed object to be a `ChassisPin`.

Alignment is an assembly precondition for every component installed onto or into
another assembly component, not a property unique to chassis pins. The base is
the exception: it is installed in the workspace and establishes the assembly
reference rather than being aligned to another component.

The requirement should be expressed once, inherited by current and future
component types, and explicitly disabled for the base.

## Decision

Define the alignment requirement as a `Component` type default:

```text
aligned($self, $installation_target)
```

Every configured component inherits this requirement through the domain type
hierarchy. The `industreal_component::base` entry explicitly sets
`required_conditions` to an empty list, overriding the inherited default.

Generalize the `implicit_domain_required_condition` rule to match
`isA(?component, Component)` instead of `isA(?component, ChassisPin)`. The rule
still depends on a materialized `hasRequiredCondition` predicate, so being a
`Component` alone does not invent a requirement.

The existing chassis-pin safety requirements remain on `ChassisPin`; this
decision changes only the implicit alignment condition.

## Alternatives Considered

### Configure alignment on every concrete component type

Rejected because it duplicates one invariant across `Base`, `Chassis`,
`ChassisPin`, `Bracket`, `Screw`, and `WheelAssembly`, and future component
types could omit it accidentally.

### Configure alignment on every component instance

Rejected because instance-level duplication is harder to maintain and obscures
the fact that alignment is a general assembly invariant.

### Keep the Layer 3 rule restricted to ChassisPin

Rejected because the adapter would materialize alignment requirements that the
rule could never convert into constraints for other component types.

### Require base alignment with Workspace

Rejected because the base establishes the assembly reference in the workspace;
the intended condition applies to components assembled onto other components.

## Consequences

### Positive

- All current and future non-base component types inherit one alignment rule.
- The base exception is visible and reviewable in its component entry.
- Domain configuration and Layer 3 rule matching describe the same scope.
- Component-specific fields can opt out of or replace inherited defaults.

### Costs and limitations

- More installation steps can have a missing alignment requirement during
  Layer 4 validation.
- Existing Layer 3, Layer 4, and procedural-reasoning artifacts must be rebuilt.
- Adding another assembly-root component requires an explicit override if it
  should not inherit alignment.
- `required_conditions` is replaced as a whole by a component override; list
  entries are not merged.

## Implementation

- `config/domain_config.yaml`
  - Bumps the domain model to `1.2.0`.
  - Moves the alignment requirement to `type_defaults.Component`.
  - Adds the base-level empty-list override.
- `config/thesis_rules.yaml`
  - Bumps the rule set to `1.2.0`.
  - Generalizes `implicit_domain_required_condition` to `Component`.
- `tests/test_layer3_ontology_config.py`
  - Verifies inheritance across representative component types.
  - Verifies that base does not receive the requirement.
  - Verifies the expanded inferred-constraint count.
