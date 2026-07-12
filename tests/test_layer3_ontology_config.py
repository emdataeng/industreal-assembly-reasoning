import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.layer3_inference import Layer3Inputs, run_layer3_inference
from src.layer4_validation import Layer4Inputs, run_layer4_validation
from src.layer3_reasoning_adapter import (
    DEFAULT_CSV_DIR,
    DEFAULT_DOMAIN_CONFIG_PATH,
    DEFAULT_OBSERVATION_CONTRACT_PATH,
    DEFAULT_PREDICATE_CONFIG_PATH,
    AdapterInputs,
    build_reasoning_adapter_outputs,
)


SAMPLE_CLIP_RESULT_ID = "raw_cad_dataset__all_test_clips::od_only::test_p1::03_assy_0_1"


def test_ontology_config_emits_generic_class_facts_and_type_defaults(tmp_path: Path) -> None:
    output_dir = tmp_path / "reasoning"
    adapter_result = build_reasoning_adapter_outputs(
        AdapterInputs(
            csv_dir=DEFAULT_CSV_DIR,
            run_id="test",
            output_dir=output_dir,
            clip_result_id=SAMPLE_CLIP_RESULT_ID,
            predicate_config_path=DEFAULT_PREDICATE_CONFIG_PATH,
            domain_config_path=DEFAULT_DOMAIN_CONFIG_PATH,
        )
    )

    predicates = _read_jsonl(output_dir / "predicates.jsonl")
    steps = _read_jsonl(output_dir / "step_records.jsonl")
    is_a = {tuple(item["args"]) for item in predicates if item["name"] == "isA"}
    labels = {tuple(item["args"]) for item in predicates if item["name"] == "hasLabel"}
    required_tools = {tuple(item["args"]) for item in predicates if item["name"] == "hasRequiredTool"}
    required_conditions = {
        tuple(item["args"]) for item in predicates if item["name"] == "hasRequiredCondition"
    }
    domain_assumed_targets = {
        tuple(item["args"]) for item in predicates if item["name"] == "allowsDomainAssumedInstallTarget"
    }
    safety_requirements = {
        tuple(item["args"]) for item in predicates if item["name"] == "hasSafetyRequirement"
    }
    time_windows = {
        item["source_event_id"].rsplit("::", 1)[-1]: item["time_window"]
        for item in steps
    }
    has_time_window = {
        item["step_id"].rsplit("::", 1)[-1]: tuple(item["args"][1:])
        for item in predicates
        if item["name"] == "hasTimeWindow"
    }

    assert adapter_result["step_records"] == 11
    assert adapter_result["adapter_config_path"] is not None
    assert time_windows["event_0"]["start_s"] == 70.9
    assert time_windows["event_0"]["end_s"] == 118.7
    assert time_windows["event_1"]["end_s"] == 118.7
    assert time_windows["event_2"]["end_s"] == 118.7
    assert has_time_window["event_0"] == (70.9, 118.7)
    assert ("base", "Base") in is_a
    assert ("base", "base") not in is_a
    assert ("base", "base") in labels
    assert ("front_chassis", "Chassis") in is_a
    assert ("rear_chassis", "Chassis") in is_a
    assert ("front_chassis_pin", "ChassisPin") in is_a
    assert ("front_rear_chassis_pin", "ChassisPin") in is_a
    assert ("rear_rear_chassis_pin", "ChassisPin") in is_a
    assert ("front_bracket_screw", "Screw") in is_a
    assert ("front_bracket_screw", "Fastener") in is_a
    assert ("front_bracket_screw", "screwdriver") in required_tools
    assert ("base", "aligned", "base", "workspace") not in required_conditions
    assert ("rear_chassis", "aligned", "rear_chassis", "base") not in required_conditions
    assert ("front_chassis_pin", "aligned", "front_chassis_pin", "front_chassis") in required_conditions
    assert ("front_bracket", "aligned", "front_bracket", "front_chassis") not in required_conditions
    assert ("front_bracket_screw", "aligned", "front_bracket_screw", "front_bracket") in required_conditions
    assert ("front_wheel_assy", "aligned", "front_wheel_assy", "front_chassis") in required_conditions
    assert any(args[-1] == "rear_chassis" for args in required_conditions)
    assert any(args[-1] == "front_chassis" for args in required_conditions)
    assert any(args[1] == "front_rear_chassis_pin" for args in domain_assumed_targets)
    assert (
        "front_chassis_pin",
        "secured",
        "front_chassis",
        "base",
    ) in safety_requirements
    assert (
        "front_rear_chassis_pin",
        "secured",
        "rear_chassis",
        "base",
    ) in safety_requirements
    assert (
        "rear_rear_chassis_pin",
        "secured",
        "rear_chassis",
        "base",
    ) in safety_requirements

    constraints_path = output_dir / "inferred_constraints.csv"
    result = run_layer3_inference(
        Layer3Inputs(
            step_records_path=output_dir / "step_records.jsonl",
            predicates_path=output_dir / "predicates.jsonl",
            rules_path=DEFAULT_PREDICATE_CONFIG_PATH,
            output_path=constraints_path,
        )
    )
    constraints = _read_constraints(constraints_path)
    diagnostics = _read_constraints(output_dir / "rule_coverage_diagnostics.csv")

    assert result["constraints_by_rule"]["effect_install_component_on_target"] >= 10
    assert result["constraints_by_rule"]["precondition_remove_requires_component_installed"] == 1
    assert result["constraints_by_rule"]["effect_remove_component_from_target"] == 1
    assert result["rule_coverage_warnings"] == 0
    assert result["constraints_by_rule"]["implicit_domain_required_condition"] == 6
    assert result["constraints_by_rule"]["safety_domain_requirement"] == 6
    assert result["constraints_by_rule"]["tool_domain_requirement"] == 1
    assert any(
        row["name"] == "requiresTool" and json.loads(row["args"]) == [row["step_id"], "screwdriver"]
        for row in constraints
    )
    remove_diag = next(row for row in diagnostics if row["action_name"] == "remove")
    assert remove_diag["warning_code"] == ""
    assert remove_diag["has_rule_coverage"] == "true"
    assert remove_diag["produced_constraint_count"] == "2"
    assert any(
        row["rule_id"] == "precondition_remove_requires_component_installed"
        and row["name"] == "requires"
        and json.loads(row["args"]) == [row["step_id"], "installed", "front_wheel_assy", "front_chassis"]
        for row in constraints
    )
    assert any(
        row["rule_id"] == "effect_remove_component_from_target"
        and row["name"] == "produces"
        and json.loads(row["args"]) == [row["step_id"], "removed", "front_wheel_assy", "front_chassis"]
        for row in constraints
    )
    install_diag = next(row for row in diagnostics if row["action_name"] == "install" and int(row["produced_constraint_count"]) > 0)
    assert install_diag["warning_code"] == ""


def test_observed_installation_target_match_confirms_installation(tmp_path: Path) -> None:
    csv_dir = _copy_csv_fixture(tmp_path)
    _set_event_observed_target(
        csv_dir / "nodes_events.csv",
        local_event_id="1",
        target="industreal_component::base",
        confidence="0.82",
        source_type="vlm",
    )
    output_dir = tmp_path / "reasoning"
    build_reasoning_adapter_outputs(
        AdapterInputs(
            csv_dir=csv_dir,
            run_id="test",
            output_dir=output_dir,
            clip_result_id=SAMPLE_CLIP_RESULT_ID,
            predicate_config_path=DEFAULT_PREDICATE_CONFIG_PATH,
            domain_config_path=DEFAULT_DOMAIN_CONFIG_PATH,
            observation_contract_path=DEFAULT_OBSERVATION_CONTRACT_PATH,
        )
    )

    predicates = _read_jsonl(output_dir / "predicates.jsonl")
    observed = next(
        item
        for item in predicates
        if item["name"] == "observedInstallTarget" and item["step_id"].endswith("event_1")
    )
    assert observed["args"][1:] == ["rear_chassis", "base"]
    assert observed["conf"] == 0.82
    assert observed["source"]["type"] == "vlm"
    assert not any(
        item["name"] == "allowsDomainAssumedInstallTarget" and item["step_id"].endswith("event_1")
        for item in predicates
    )

    constraints_path = output_dir / "inferred_constraints.csv"
    run_layer3_inference(
        Layer3Inputs(
            step_records_path=output_dir / "step_records.jsonl",
            predicates_path=output_dir / "predicates.jsonl",
            rules_path=DEFAULT_PREDICATE_CONFIG_PATH,
            output_path=constraints_path,
        )
    )
    constraints = _read_constraints(constraints_path)
    matching = [
        row
        for row in constraints
        if row["step_id"].endswith("event_1")
        and row["name"] == "produces"
        and json.loads(row["args"])[1:] == ["installed", "rear_chassis", "base"]
    ]
    assert len(matching) == 1
    assert matching[0]["rule_id"] == "effect_install_component_on_observed_target"


def test_observed_installation_target_conflict_rejects_step(tmp_path: Path) -> None:
    csv_dir = _copy_csv_fixture(tmp_path)
    _set_event_observed_target(
        csv_dir / "nodes_events.csv",
        local_event_id="1",
        target="industreal_component::front_bracket",
        confidence="0.91",
        source_type="vlm",
    )
    output_dir = tmp_path / "reasoning"
    build_reasoning_adapter_outputs(
        AdapterInputs(
            csv_dir=csv_dir,
            run_id="test",
            output_dir=output_dir,
            clip_result_id=SAMPLE_CLIP_RESULT_ID,
            predicate_config_path=DEFAULT_PREDICATE_CONFIG_PATH,
            domain_config_path=DEFAULT_DOMAIN_CONFIG_PATH,
            observation_contract_path=DEFAULT_OBSERVATION_CONTRACT_PATH,
        )
    )

    constraints_path = output_dir / "inferred_constraints.csv"
    run_layer3_inference(
        Layer3Inputs(
            step_records_path=output_dir / "step_records.jsonl",
            predicates_path=output_dir / "predicates.jsonl",
            rules_path=DEFAULT_PREDICATE_CONFIG_PATH,
            output_path=constraints_path,
        )
    )
    constraints = _read_constraints(constraints_path)
    event_constraints = [row for row in constraints if row["step_id"].endswith("event_1")]
    mismatch = next(row for row in event_constraints if row["name"] == "incompatibleInstallationTarget")
    assert json.loads(mismatch["args"])[1:] == [
        "rear_chassis",
        "front_bracket",
        "base",
    ]
    assert mismatch["rule_id"] == "compat_observed_installation_target_mismatch"
    assert not any(
        row["name"] == "produces" and json.loads(row["args"])[1] == "installed"
        for row in event_constraints
    )

    validations_path = output_dir / "validation_records.jsonl"
    run_layer4_validation(
        Layer4Inputs(
            step_records_path=output_dir / "step_records.jsonl",
            predicates_path=output_dir / "predicates.jsonl",
            constraints_path=constraints_path,
            rule_coverage_path=output_dir / "rule_coverage_diagnostics.csv",
            output_path=validations_path,
            config_path=DEFAULT_PREDICATE_CONFIG_PATH,
        )
    )
    validation = next(
        item for item in _read_jsonl(validations_path) if item["step_id"].endswith("event_1")
    )
    assert validation["status"] == "rejected"
    assert validation["incompatibilities"][0]["name"] == "incompatibleInstallationTarget"


def test_require_observed_policy_disables_domain_assumed_installation(tmp_path: Path) -> None:
    csv_dir = _copy_csv_fixture(tmp_path)
    contract = json.loads(DEFAULT_OBSERVATION_CONTRACT_PATH.read_text(encoding="utf-8"))
    contract["installation_target"]["missing_observation_policy"] = "require_observed"
    contract_path = tmp_path / "observation_contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    output_dir = tmp_path / "reasoning"
    build_reasoning_adapter_outputs(
        AdapterInputs(
            csv_dir=csv_dir,
            run_id="test",
            output_dir=output_dir,
            clip_result_id=SAMPLE_CLIP_RESULT_ID,
            predicate_config_path=DEFAULT_PREDICATE_CONFIG_PATH,
            domain_config_path=DEFAULT_DOMAIN_CONFIG_PATH,
            observation_contract_path=contract_path,
        )
    )

    predicates = _read_jsonl(output_dir / "predicates.jsonl")
    assert not any(item["name"] == "allowsDomainAssumedInstallTarget" for item in predicates)
    constraints_path = output_dir / "inferred_constraints.csv"
    run_layer3_inference(
        Layer3Inputs(
            step_records_path=output_dir / "step_records.jsonl",
            predicates_path=output_dir / "predicates.jsonl",
            rules_path=DEFAULT_PREDICATE_CONFIG_PATH,
            output_path=constraints_path,
        )
    )
    constraints = _read_constraints(constraints_path)
    assert not any(
        row["name"] == "produces" and json.loads(row["args"])[1] == "installed"
        for row in constraints
    )


def test_explicit_secured_annotation_produces_secured_effect(tmp_path: Path) -> None:
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    for filename in ("nodes_events.csv", "edges_event_component.csv", "edges_event_next.csv", "nodes_components.csv"):
        shutil.copy2(DEFAULT_CSV_DIR / filename, csv_dir / filename)

    events_path = csv_dir / "nodes_events.csv"
    with open(events_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0])
    target = next(
        row
        for row in rows
        if row["clip_result_id"] == SAMPLE_CLIP_RESULT_ID
        and row["component"] == "rear chassis"
        and row["event_type"] == "INSTALL"
    )
    target["action_desc"] = "Install and secure rear chassis"
    target["display_name"] = target["action_desc"]
    target["name"] = target["action_desc"]
    with open(events_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    output_dir = tmp_path / "reasoning"
    build_reasoning_adapter_outputs(
        AdapterInputs(
            csv_dir=csv_dir,
            run_id="test",
            output_dir=output_dir,
            clip_result_id=SAMPLE_CLIP_RESULT_ID,
            predicate_config_path=DEFAULT_PREDICATE_CONFIG_PATH,
            domain_config_path=DEFAULT_DOMAIN_CONFIG_PATH,
        )
    )
    predicates = _read_jsonl(output_dir / "predicates.jsonl")
    observed = next(item for item in predicates if item["name"] == "hasObservedEffect")
    assert observed["args"][1:] == ["secured", "rear_chassis", "base"]

    constraints_path = output_dir / "inferred_constraints.csv"
    run_layer3_inference(
        Layer3Inputs(
            step_records_path=output_dir / "step_records.jsonl",
            predicates_path=output_dir / "predicates.jsonl",
            rules_path=DEFAULT_PREDICATE_CONFIG_PATH,
            output_path=constraints_path,
        )
    )
    constraints = _read_constraints(constraints_path)
    assert any(
        row["rule_id"] == "effect_explicitly_observed_condition"
        and row["name"] == "produces"
        and json.loads(row["args"]) == [row["step_id"], "secured", "rear_chassis", "base"]
        for row in constraints
    )


def _copy_csv_fixture(tmp_path: Path) -> Path:
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    for filename in ("nodes_events.csv", "edges_event_component.csv", "edges_event_next.csv", "nodes_components.csv"):
        shutil.copy2(DEFAULT_CSV_DIR / filename, csv_dir / filename)
    return csv_dir


def _set_event_observed_target(
    events_path: Path,
    *,
    local_event_id: str,
    target: str,
    confidence: str,
    source_type: str,
) -> None:
    with open(events_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0])
    for field in (
        "observed_installation_target",
        "observed_installation_target_confidence",
        "observed_installation_target_source",
    ):
        if field not in fieldnames:
            fieldnames.append(field)
    target_row = next(
        row
        for row in rows
        if row["clip_result_id"] == SAMPLE_CLIP_RESULT_ID and row["local_event_id:int"] == local_event_id
    )
    target_row["observed_installation_target"] = target
    target_row["observed_installation_target_confidence"] = confidence
    target_row["observed_installation_target_source"] = source_type
    with open(events_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_constraints(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
