# Evaluation

The reasoning layer was evaluated through five functional evaluations, each asking a falsifiable question about a specific layer of the stack. This page summarizes what was evaluated, how, and what was found. The per-evaluation evidence reports live in `docs/reasoning_layers/Evaluation1…5/`; the runner scripts belong to the private research archive, but every report documents its inputs, method, and outputs.

## What "evaluation" means here — and what it doesn't

This is a **functional evaluation of reasoning behavior over symbolic inputs**. The upstream artifacts are derived from IndustReal via an oracle-first pipeline, so the evaluations test whether the reasoning layer behaves according to its specification — not whether a perception system is accurate, and not whether the rule base matches expert assembly judgment (which would require external expert annotation and is listed as future work).

The approach was designed to be falsifiable. It would have failed if, for example: input order was not preserved; constraints appeared without traceable rule provenance; rejected or invalidated effects supported later steps; missing requirements went unrecorded; low-confidence evidence did not affect outcomes; or the exported graph contradicted the validation records.

**Data:** 38 clip results (19 IndustReal clips × 2 modes: `od_only` and `od_plus_psr_error_hints`, the latter allowing explicit error annotations as additional evidence), totaling 659 assembly events in the public fixture.

## Evaluation 1 — Pipeline artifact consistency

*Can every stage be inspected independently, with no hidden state?*

One clip (`03_assy_0_1`) was run end-to-end and each artifact checked against its contract: 11 step records for 11 input steps; 106 predicates all referencing valid steps; 26 inferred constraints; a validation record with status for every step; 10 `NEXT` edges preserving input order; 9 `DEPENDS_ON` edges none of which were supported by a rejected step.

The most valuable finding was a **negative** one: the clip's `Remove front wheel assy` step had predicate evidence but matched no rule in the then-current rule base. The pipeline surfaced this as an explicit `no_applicable_rule` coverage warning rather than letting the step pass silently — and the gap drove the design of removal semantics and the effect lifecycle (documented in `Evaluation1_remove_semantics/`, [ADRs](reasoning_layers/decisions/), and the [changelog](reasoning_layers/domain_rule_changelog.md)).

## Evaluation 2 — Constraint inference coverage

*Does Layer 3 actually enrich evidence, or just relabel it?*

Run over all 38 clip results. From 6,568 predicate records, Layer 3 inferred **1,673 constraints**: 643 `produces`, 776 `requires`, 67 `requiresTool`, 171 `requiresSafety`, and 16 incompatibilities. Removal semantics covered all 149 observed removal steps.

Representative behavior: a single "install chassis pin" step generates a precondition (chassis installed), an expected effect (pin installed), an implicit assembly condition (pin aligned with chassis), and a safety requirement (base secured) — none of which appear in the input label. Explicit error annotations in the error-hints mode become incompatibility constraints; clips without error events produce identical constraint counts in both modes, confirming the rule layer responds to evidence rather than mode labels.

## Evaluation 3 — Step validation and effect lifecycle

*Are inferred constraints used consistently to decide?*

Clip `08_assy_0_1` (error-hints mode) was selected because it naturally contains all the constraint types needed. It produced 34 validation records: **18 accepted, 10 uncertain, 6 rejected**, with an effect history of 20 active, 8 invalidated, and 4 `inactive_rejected` effects.

Five behaviors were checked, all passing:

| Behavior | Evidence |
|---|---|
| Requirement support vs. missing | 45 requirements: 27 supported, 18 recorded missing |
| Hard incompatibility → rejection | 2 incompatibilities; both steps rejected with trace |
| Rejected-step isolation | 6 rejected steps; none supported a later dependency |
| Removal invalidation | 10 removal effects; no lifecycle inconsistencies |
| Threshold sensitivity | Controlled confidence drop demoted an accepted step to uncertain |

## Evaluation 4 — Graph traceability

*Can the same decisions be followed in the exported graph?*

The same clip's graph — 34 Step, 326 Predicate, 79 Constraint, 8 Rule, 13 Entity, and 40 Source nodes; 33 `NEXT`, 27 `DEPENDS_ON`, 45 `REQUIRES`, 32 `PRODUCES`, 326 `HAS_PREDICATE`, and 8 `INVALIDATED_BY` edges — was checked against nine structural conditions: order preservation, dependency grounding (every `DEPENDS_ON` backed by a requirement and an earlier produced effect), requirement and missing-requirement visibility, evidence traceability from every step status, rule provenance for all 79 constraints, rejected-step isolation, provisional marking of uncertain-supported dependencies, and `INVALIDATED_BY` visibility for all 8 invalidated effects.

**All nine checks passed with zero failures.** The graph is not a summary of validation — it *is* the validation, in traversable form.

## Evaluation 5 — Robustness under symbolic degradation

*Does the system fail conservatively when evidence goes bad?*

Five adversarial perturbations were applied to the same clip's symbolic inputs before re-running validation:

| Perturbation | Outcome |
|---|---|
| Lower a predicate's confidence | accepted → **uncertain** |
| Delete required support evidence | accepted → **rejected**, missing requirement recorded |
| Swap object for an incompatible type | accepted → **uncertain** |
| Inject an explicit error action | accepted → **rejected**, no later step used it as support |
| Delete a produced effect used downstream | **7 dependent steps** demoted; all missing requirements recorded |

No directly affected accepted step remained accepted, no rejected step ever supported a later dependency, and every changed decision remained explainable from its preserved trace. The cascade in the last row is the effect history working as designed: removing one load-bearing effect correctly propagated to everything that depended on it.

## Honest limitations

Stated in the thesis and worth restating here:

1. **Oracle inputs.** If upstream evidence assigns the wrong object type or action, the reasoning layer reasons correctly about the wrong symbolic state — the trace stays honest, but the status can be semantically wrong.
2. **Manual rule base and domain model.** Correctness of reasoning ≠ coverage of the domain; scaling to new assemblies currently means authoring config.
3. **Selected representative clips** for Evaluations 3–5, chosen to exercise specific behaviors — not random sampling for dataset-wide frequency claims.
4. **No external expert reference.** A systematic mismatch between the rule base and expert judgment would be invisible to these evaluations; detecting it needs labeled correct/faulty executions.
5. **The graph is an inspection artifact,** evaluated as such — not as an executable process model or runtime guidance controller.
