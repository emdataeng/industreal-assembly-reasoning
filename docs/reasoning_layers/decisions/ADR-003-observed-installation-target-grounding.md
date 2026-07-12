# ADR-003: Separate Observed and Expected Installation Targets

- Status: Accepted
- Date: 2026-06-25
- Domain model version: `1.2.0`
- Rule set version: `1.3.0`
- Observation contract version: `1.0.0`

## Context

The adapter previously emitted `hasInstallTarget(component, target)` from the
domain model and Layer 3 used that expected target to produce an installed
effect. This supports existing IndustReal clips, whose events identify an action
and component but do not provide an independently observed installation target.

However, the expected domain target cannot validate an upstream claim about
where installation actually occurred. Future AI, VLM, annotation, or sensor
outputs may provide a target that either agrees or conflicts with the domain.
The reasoning layer must preserve those two facts independently:

```text
observedInstallTarget(step, component, observed_target)
hasInstallTarget(component, expected_target)
```

Existing clips must remain usable when no observed target is available.

## Decision

Introduce a source-independent observation contract configured in:

```text
config/observation_contract.yaml
```

The existing event input may optionally expose these canonical fields:

```text
observed_installation_target
observed_installation_target_confidence
observed_installation_target_source
```

No additional observation artifact is required. Any upstream source can populate
these fields before the adapter runs.

The adapter resolves the observed target to the same domain individual
vocabulary used by expected targets and emits `observedInstallTarget`. It never
replaces the observed value with the expected value.

Layer 3 handles three cases:

1. **Observed target matches expected target**
   - Shared variable binding requires both predicates to bind the same target.
   - `effect_install_component_on_observed_target` produces the installed
     effect.
2. **Observed target conflicts with expected target**
   - A `not_equal` rule guard detects the mismatch.
   - `compat_observed_installation_target_mismatch` produces
     `incompatibleInstallationTarget`.
   - Layer 4 rejects the step because the constraint has compatibility status.
3. **No observed target exists**
   - Under the default `domain_assumed` policy, the adapter emits
     `allowsDomainAssumedInstallTarget`.
   - The existing `effect_install_component_on_target` rule preserves the
     domain-inferred installed effect.

The observation contract also supports `require_observed`. Under that policy,
missing target evidence does not enable the domain-assumed effect.

## Alternatives Considered

### Require observed targets immediately

Rejected as the default because current IndustReal events do not contain target
observations. Most installation effects would disappear, making existing
artifacts incompatible with the new feature.

### Treat the domain target as an observation

Rejected because it would compare the domain model with itself and could never
detect an upstream target mismatch.

### Add a separate observed-relations artifact

Not selected. A separate file could be useful for some integrations, but it is
not necessary for the contract. Optional canonical fields on the existing event
input provide a smaller initial integration surface.

### Detect mismatches in Python

Rejected because match and mismatch semantics belong in inspectable,
version-controlled rules. Python performs extraction and normalization; YAML
rules perform inference.

## Consequences

### Positive

- AI/VLM target claims can be checked against domain expectations.
- Existing target-less IndustReal clips preserve their current behavior.
- Observed values retain confidence and source provenance.
- Correct target confirmation uses ordinary rule-variable binding.
- Inequality guards are reusable for future observed-versus-expected checks,
  such as tool compatibility.

### Costs and limitations

- Upstream systems must populate the canonical optional fields to obtain
  observation-verified target grounding.
- `domain_assumed` effects remain inferred from expected knowledge and must not
  be described as independently observed.
- The current contract assumes one observed installation target field applies
  to the installed component associated with the event.
- Changing the missing-observation policy requires rebuilding adapter and
  downstream reasoning artifacts.

## Implementation

- `config/observation_contract.yaml`
  - Defines canonical event fields and missing-observation policy.
- `config/reasoning_adapter.yaml`
  - References the shared observation contract.
- `config/thesis_rules.yaml`
  - Adds predicates, observed-target confirmation, and mismatch compatibility.
  - Bumps the rule set to `1.3.0`.
- `src/layer3_reasoning_adapter.py`
  - Loads the contract and emits observed or fallback-policy predicates.
- `src/layer3_inference.py`
  - Supports two-argument `equal` and `not_equal` guards.
- `tests/test_layer3_ontology_config.py`
  - Covers matching, conflicting, missing, and `require_observed` cases.

## Follow-up

- Apply the same observed-versus-expected pattern to tool observations.
- Consider structured multiple-target observations if future events act on more
  than one installed component.
- Record observation-contract version and policy in generated run manifests.
