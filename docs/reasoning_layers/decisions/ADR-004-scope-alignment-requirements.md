# ADR-004: Scope Alignment Requirements to Mechanically Alignment-Sensitive Types

- Status: Accepted
- Date: 2026-06-26
- Domain model version: `1.3.0`
- Rule set version: `1.3.0`

## Context

ADR-002 generalized `aligned(component, installation_target)` to all non-base
components by placing the requirement on `type_defaults.Component`. After
regenerating all reasoning artifacts, this proved too strict for the current
IndustReal evidence contract. Most installation steps became `uncertain` because
the source artifacts do not provide separate alignment evidence for placement-like
operations such as installing chassis or bracket components.

In assembly terms, alignment is still important, but it is most defensible as a
hard validation requirement for operations where insertion, fastening, or
interface fit can fail if the relevant parts are not aligned.

## Decision

Remove the generic alignment requirement from `Component` and configure it only
for component types where alignment is mechanically central:

```text
ChassisPin     aligned($self, $installation_target)
Screw          aligned($self, $installation_target)
WheelAssembly aligned($self, $installation_target)
```

`Chassis` and `Bracket` installations do not receive a hard alignment
requirement by default. They may still be treated as placement or installation
operations through their installed effects and target preconditions.

The Layer 3 `implicit_domain_required_condition` rule remains generic. It still
matches components typed as `Component`, but it only produces constraints when
the adapter has materialized a `hasRequiredCondition(...)` predicate from the
domain configuration.

## Alternatives Considered

### Keep alignment on every non-base component

Rejected for the current evidence contract. It made most steps uncertain because
the dataset does not expose explicit alignment observations for every placement
operation.

### Remove alignment entirely

Rejected because pins, screws, and wheel assemblies have meaningful mechanical
alignment requirements that should remain visible in the reasoning layer.

### Treat alignment as a warning-only diagnostic

Not selected for this change. A warning-only representation may be useful later,
but the current implementation already supports hard requirements through
`hasRequiredCondition`, so the smaller change is to scope that requirement to
the component types where it is most defensible.

## Consequences

### Positive

- Chassis and bracket installations are no longer blocked by missing alignment
  evidence when no explicit alignment observation exists.
- Alignment remains represented for insertion, fastening, and interface-fit
  components.
- The rule engine remains generic and inspectable; the domain configuration
  controls which components emit alignment requirements.

### Costs and limitations

- Chassis and bracket alignment errors will not be detected as hard missing
  requirements unless future evidence or configuration adds them back.
- Existing Layer 3, Layer 4, graph, and evaluation artifacts must be rebuilt.
- The domain model now duplicates the same alignment requirement across three
  type defaults instead of defining it once on `Component`.

## Implementation

- `config/domain_config.yaml`
  - Bumps the domain model to `1.3.0`.
  - Removes `Component.required_conditions`.
  - Adds alignment requirements to `ChassisPin`, `Screw`, and `WheelAssembly`.
- `tests/test_layer3_ontology_config.py`
  - Verifies that `Chassis` and `Bracket` no longer emit alignment
    requirements.
  - Verifies that `ChassisPin`, `Screw`, and `WheelAssembly` still emit
    alignment requirements.
  - Updates the expected `implicit_domain_required_condition` count.
