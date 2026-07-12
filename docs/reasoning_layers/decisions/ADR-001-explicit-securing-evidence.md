# ADR-001: Model Securing as an Explicitly Observed Effect

- Status: Accepted
- Date: 2026-06-24
- Domain model version: `1.1.0`
- Rule set version: `1.1.0`

## Context

Installing a chassis and securing it are related but semantically distinct
operations. An installation event establishes that a component was placed on its
expected target. It does not, by itself, establish that the component was
fastened, locked, or otherwise made safe.

Installing a `ChassisPin` requires its installation target to have already been
secured to that target's own installation target. For example:

- Installing `front_chassis_pin` requires `secured(front_chassis, base)`.
- Installing `front_rear_chassis_pin` requires `secured(rear_chassis, base)`.
- Installing `rear_rear_chassis_pin` requires `secured(rear_chassis, base)`.

The requirement must be generic across `ChassisPin` components while preserving
the distinction between installation and securing.

## Decision

Securing is represented as an explicitly observed effect attached to an
installation step.

An annotation such as:

```text
Install and secure rear chassis
```

provides explicit evidence for both:

```text
installed(rear_chassis, base)
secured(rear_chassis, base)
```

A plain annotation such as:

```text
Install rear chassis
```

provides evidence only for:

```text
installed(rear_chassis, base)
```

The reasoning adapter emits a `hasObservedEffect` predicate only when the
annotation matches a configured `observed_effects` pattern. Layer 3 then converts
that predicate into a `produces secured(...)` constraint.

The generic `ChassisPin` safety requirement is expressed as:

```text
secured($installation_target, $installation_target_target)
```

The `$installation_target_target` resolver follows the pin's installation target
to that target's own installation target.

## Alternatives Considered

### Infer securing from installation

Rejected because placement does not prove that a component was secured. This
would create unsupported safety evidence and could incorrectly accept later
steps.

### Represent securing as a separate primary action

Not selected for the current dataset because the source event model has one
primary action per step and the available annotations commonly describe
installation and securing together.

A separate `secure` action remains appropriate if future datasets provide
distinct securing events, timestamps, objects, or evidence.

### Configure each ChassisPin individually

Rejected because it duplicates the same relationship for every pin and makes the
domain configuration harder to maintain. The target-of-target resolver expresses
the invariant once at the `ChassisPin` type level.

### Treat securing wording as informal text only

Rejected because Layer 4 requires structured evidence to support safety
requirements and dependency relationships.

## Consequences

### Positive

- Installation and securing retain distinct meanings.
- Safety validation relies on explicit evidence.
- The requirement applies generically to current and future `ChassisPin`
  components with the same domain structure.
- Securing evidence participates in effect history and can support later steps.
- Annotation-to-predicate behavior remains configurable through the domain model.

### Costs and limitations

- Source annotations must explicitly mention securing.
- Editing an experiment step-list text artifact does not change source evidence;
  the wording must be present in the upstream event `action_desc`.
- Existing Layer 3, Layer 4, and procedural-reasoning graph artifacts must be
  rebuilt after relevant annotation or configuration changes.
- A ChassisPin installation can remain uncertain or be rejected when no prior
  securing evidence is available.
- Text-pattern matching is an interim evidence extraction mechanism. Richer
  structured annotations may replace it later.

## Implementation

The decision is implemented through:

- `config/domain_config.yaml`
  - Generic `ChassisPin` target-of-target safety requirement.
  - Configurable `Chassis.observed_effects`.
- `config/thesis_rules.yaml`
  - `hasObservedEffect` predicate.
  - `effect_explicitly_observed_condition` rule.
- `src/layer3_reasoning_adapter.py`
  - `$installation_target_target` resolution.
  - Explicit observed-effect extraction from annotations.
- `tests/test_layer3_ontology_config.py`
  - Generic safety-requirement and explicit-effect coverage.

## Follow-up

- Record domain-model and rule-set versions and config hashes in generated run
  manifests.
- Reconsider a distinct `secure` action if future source data models securing as
  a separate event.

