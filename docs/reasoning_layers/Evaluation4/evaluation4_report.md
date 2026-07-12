# Evaluation 4 Report: Procedural Graph Traceability

- Evaluated graph: `procedural_reasoning_graph::raw_cad_dataset__all_test_clips::od_plus_psr_error_hints::test_p1::08_assy_0_1`
- Clip/result ID: `raw_cad_dataset__all_test_clips__od_plus_psr_error_hints__test_p1__08_assy_0_1`
- Timestamp: `2026-06-30T13:49:31+02:00`
- Graph directory: `D:\Code\XR_Event_Grounding_Graph\IndustReal_Pipeline\results\procedural_reasoning_graph\raw_cad_dataset__all_test_clips__od_plus_psr_error_hints__test_p1__08_assy_0_1`
- Reasoning directory: `D:\Code\XR_Event_Grounding_Graph\IndustReal_Pipeline\results\reasoning_layers\raw_cad_dataset__all_test_clips__od_plus_psr_error_hints__test_p1__08_assy_0_1`

## Graph Provenance

- Graph schema version: `1.0`
- Graph built at: `2026-06-30T12:30:08+02:00`
- Graph builder: `src.procedural_reasoning_graph.build_procedural_reasoning_graph`
- Domain config: version `1.3.0`, sha256 `1f92ec4657d8`, path `config\domain_config.yaml`
- Thesis rules: version `1.3.0`, sha256 `bfff375aa487`, path `config\thesis_rules.yaml`
- Validation config: version `1.3.0`, sha256 `bfff375aa487`, path `config\thesis_rules.yaml`

## Node Type Distribution

| Node type | Count |
| --- | ---: |
| Constraint | 91 |
| Entity | 13 |
| Predicate | 367 |
| Rule | 8 |
| Source | 47 |
| Step | 34 |

## Edge Type Distribution

| Edge type | Count |
| --- | ---: |
| DEPENDS_ON | 27 |
| DERIVED_FROM | 458 |
| HAS_CONSTRAINT | 91 |
| HAS_ENTITY | 653 |
| HAS_PREDICATE | 367 |
| INVALIDATED_BY | 8 |
| NEXT | 33 |
| PRODUCES | 32 |
| REQUIRES | 57 |
| SUPPORTED_BY | 27 |
| USES | 34 |

## Step Status Distribution

| Status | Count |
| --- | ---: |
| accepted | 14 |
| rejected | 6 |
| uncertain | 14 |

## Traceability Checks

| Check | Status | Message | Evidence |
| --- | --- | --- | --- |
| Order preservation | PASS | 33 NEXT edge checks; 0 failures. | `order_preservation_results.csv` |
| Dependency grounding | PASS | 27 DEPENDS_ON edges checked; 0 failures. | `dependency_grounding_results.csv` |
| Requirement visibility | PASS | 71 requirements checked; 0 failures. | `requirement_visibility_results.csv` |
| Missing requirement visibility | PASS | All 30 missing requirements are visible as graph constraints. | `missing_requirement_visibility_results.csv` |
| Evidence traceability | PASS | 34 Step nodes checked; 0 failures. | `evidence_traceability_results.csv` |
| Rule provenance | PASS | 91 rule-provenance constraints checked; 0 failures. | `rule_provenance_results.csv` |
| Rejected-step isolation | PASS | 31 rejected-step graph checks; 0 failures. | `rejected_step_isolation_graph_results.csv` |
| Provisional dependency visibility | PASS | 4 uncertain-support dependencies checked; 0 failures. | `provisional_dependency_results.csv` |
| Effect invalidation visibility | PASS | 8 invalidated effects checked; 0 failures. | `effect_invalidation_graph_results.csv` |

## Neo4j Views

Screenshot-oriented Cypher queries are listed in `neo4j_views.md`. They split the evidence into temporal order, dependency, constraint evidence, effect lifecycle, and compact representative trace views.

## Limitations

This evaluation checks graph traceability against the exported artifacts for one representative clip. It does not evaluate perception, dataset-wide graph coverage, or whether every possible Neo4j visualization layout will be visually readable without manual styling.

Status totals: PASS=9, FAIL=0, WARNING=0, SKIPPED=0.
