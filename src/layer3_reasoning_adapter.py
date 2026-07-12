"""Adapt existing IndustReal graph CSVs into thesis Layer 1/2 records.

This module is intentionally downstream of the existing graph exporter. It
does not change the current assembly graph generation, Neo4j CSV export, or
Neo4j import path.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ADAPTER_CONFIG_PATH = ROOT / "config" / "reasoning_adapter.yaml"


@dataclass(frozen=True)
class ReasoningAdapterConfig:
    run_id: str
    csv_dir: Path
    output_root: Path
    predicate_config_path: Path
    domain_config_path: Path
    observation_contract_path: Path
    events_csv: str
    event_component_csv: str
    event_next_csv: str
    components_csv: str


def load_adapter_config(config_path: Path | None = DEFAULT_ADAPTER_CONFIG_PATH) -> ReasoningAdapterConfig:
    """Load adapter paths and input CSV filenames from config."""
    path = Path(config_path or DEFAULT_ADAPTER_CONFIG_PATH)
    config = _load_config_file(path)
    run_id = str(config.get("default_run_id") or "")
    if not run_id:
        raise ValueError(f"adapter config missing default_run_id: {path}")
    paths = config.get("paths", {})
    csv_files = config.get("csv_files", {})
    if not isinstance(paths, dict):
        raise ValueError(f"adapter config paths must be a mapping: {path}")
    if not isinstance(csv_files, dict):
        raise ValueError(f"adapter config csv_files must be a mapping: {path}")
    return ReasoningAdapterConfig(
        run_id=run_id,
        csv_dir=_config_path(path, _expand_config_value(paths.get("csv_dir"), run_id)),
        output_root=_config_path(path, _expand_config_value(paths.get("output_root"), run_id)),
        predicate_config_path=_config_path(path, _expand_config_value(paths.get("predicate_config"), run_id)),
        domain_config_path=_config_path(path, _expand_config_value(paths.get("domain_config"), run_id)),
        observation_contract_path=_config_path(path, _expand_config_value(paths.get("observation_contract"), run_id)),
        events_csv=_required_config_string(csv_files, "events", path),
        event_component_csv=_required_config_string(csv_files, "event_component", path),
        event_next_csv=_required_config_string(csv_files, "event_next", path),
        components_csv=_required_config_string(csv_files, "components", path),
    )


def _load_config_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ImportError:
        loaded = json.loads(text)
    else:
        loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"config must be a mapping: {path}")
    return loaded


def _expand_config_value(value: Any, run_id: str) -> str:
    return str(value or "").replace("${default_run_id}", run_id)


def _config_path(config_path: Path, value: str) -> Path:
    if not value:
        raise ValueError(f"adapter config path value cannot be empty: {config_path}")
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path


def _required_config_string(mapping: dict[str, Any], key: str, path: Path) -> str:
    value = str(mapping.get(key) or "")
    if not value:
        raise ValueError(f"adapter config missing csv_files.{key}: {path}")
    return value


_DEFAULT_ADAPTER_CONFIG = None


def default_adapter_config() -> ReasoningAdapterConfig:
    """Return the default adapter config loaded from config/reasoning_adapter.yaml."""
    global _DEFAULT_ADAPTER_CONFIG
    if _DEFAULT_ADAPTER_CONFIG is None:
        _DEFAULT_ADAPTER_CONFIG = load_adapter_config(DEFAULT_ADAPTER_CONFIG_PATH)
    return _DEFAULT_ADAPTER_CONFIG


DEFAULT_RUN_ID = default_adapter_config().run_id
DEFAULT_CSV_DIR = default_adapter_config().csv_dir
DEFAULT_OUTPUT_ROOT = default_adapter_config().output_root
DEFAULT_PREDICATE_CONFIG_PATH = default_adapter_config().predicate_config_path
DEFAULT_DOMAIN_CONFIG_PATH = default_adapter_config().domain_config_path
DEFAULT_OBSERVATION_CONTRACT_PATH = default_adapter_config().observation_contract_path

EVENTS_CSV = default_adapter_config().events_csv
EVENT_COMPONENT_CSV = default_adapter_config().event_component_csv
EVENT_NEXT_CSV = default_adapter_config().event_next_csv
COMPONENTS_CSV = default_adapter_config().components_csv

REQUIRED_PREDICATE_KEYS = (
    "has_action",
    "has_time_window",
    "uses_tool",
    "uses_object",
    "is_a",
    "has_label",
    "has_parent_component",
    "has_install_target",
    "observed_install_target",
    "allows_domain_assumed_install_target",
    "requires_installed_before",
    "has_required_condition",
    "has_safety_requirement",
    "has_observed_effect",
    "has_required_tool",
)


@dataclass(frozen=True)
class AdapterInputs:
    csv_dir: Path
    run_id: str
    output_dir: Path
    clip_result_id: str | None = None
    mode: str | None = None
    archive_name: str | None = None
    clip: str | None = None
    evidence_root: Path | None = None
    adapter_config_path: Path | None = DEFAULT_ADAPTER_CONFIG_PATH
    predicate_config_path: Path | None = DEFAULT_PREDICATE_CONFIG_PATH
    domain_config_path: Path | None = DEFAULT_DOMAIN_CONFIG_PATH
    observation_contract_path: Path | None = DEFAULT_OBSERVATION_CONTRACT_PATH


def build_reasoning_adapter_outputs(inputs: AdapterInputs) -> dict[str, Any]:
    """Build step_records.jsonl and predicates.jsonl from existing graph CSVs."""
    adapter_config = load_adapter_config(inputs.adapter_config_path)
    csv_dir = Path(inputs.csv_dir)
    output_dir = Path(inputs.output_dir)
    events_csv = adapter_config.events_csv
    event_component_csv = adapter_config.event_component_csv
    event_next_csv = adapter_config.event_next_csv
    components_csv = adapter_config.components_csv
    events = _read_csv(csv_dir / events_csv)
    event_component_edges = _read_csv(csv_dir / event_component_csv)
    event_next_edges = _read_csv(csv_dir / event_next_csv)
    components = _read_csv(csv_dir / components_csv)
    predicate_defs = _load_predicate_defs(inputs.predicate_config_path)
    domain_config = _load_domain_config(inputs.domain_config_path)
    observation_contract = _load_observation_contract(inputs.observation_contract_path)

    filtered_events = _filter_events(
        events,
        clip_result_id=inputs.clip_result_id,
        mode=inputs.mode,
        archive_name=inputs.archive_name,
        clip=inputs.clip,
    )
    event_ids = {_event_id(row) for row in filtered_events}
    component_by_id = {_component_id(row): row for row in components}
    edges_by_event: dict[str, list[dict[str, str]]] = {}
    for edge in event_component_edges:
        start_id = edge.get(":START_ID(AssemblyEvent)", "")
        if start_id in event_ids:
            edges_by_event.setdefault(start_id, []).append(edge)

    next_by_event = {
        edge.get(":START_ID(AssemblyEvent)", ""): edge.get(":END_ID(AssemblyEvent)", "")
        for edge in event_next_edges
        if edge.get(":START_ID(AssemblyEvent)", "") in event_ids
    }
    previous_by_event = {
        edge.get(":END_ID(AssemblyEvent)", ""): edge.get(":START_ID(AssemblyEvent)", "")
        for edge in event_next_edges
        if edge.get(":END_ID(AssemblyEvent)", "") in event_ids
    }

    ordered_events = sorted(
        filtered_events,
        key=lambda row: (
            row.get("clip_result_id", ""),
            _parse_int(row.get("local_event_id:int"), default=0),
            _parse_int(row.get("frame:int"), default=0),
            _event_id(row),
        ),
    )
    inferred_time_windows = _infer_time_window_ends(ordered_events)

    step_records: list[dict[str, Any]] = []
    predicates: list[dict[str, Any]] = []
    for row in ordered_events:
        inferred_window = inferred_time_windows.get(_event_id(row), {})
        step_record = _step_record(
            row,
            edges_by_event=edges_by_event,
            component_by_id=component_by_id,
            next_event_id=next_by_event.get(_event_id(row)),
            previous_event_id=previous_by_event.get(_event_id(row)),
            inferred_end_frame=inferred_window.get("end_frame"),
            inferred_end_s=inferred_window.get("end_s"),
            csv_files=adapter_config,
            evidence_root=inputs.evidence_root,
        )
        step_records.append(step_record)
        predicates.extend(
            _predicates_for_step(
                step_record,
                row,
                edges_by_event=edges_by_event,
                component_by_id=component_by_id,
                predicate_defs=predicate_defs,
                domain_config=domain_config,
                observation_contract=observation_contract,
                csv_files=adapter_config,
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    step_path = output_dir / "step_records.jsonl"
    pred_path = output_dir / "predicates.jsonl"
    _write_jsonl(step_path, step_records)
    _write_jsonl(pred_path, predicates)

    return {
        "run_id": inputs.run_id,
        "csv_dir": str(csv_dir),
        "output_dir": str(output_dir),
        "step_records_path": str(step_path),
        "predicates_path": str(pred_path),
        "adapter_config_path": str(inputs.adapter_config_path) if inputs.adapter_config_path else None,
        "predicate_config_path": str(inputs.predicate_config_path) if inputs.predicate_config_path else None,
        "domain_config_path": str(inputs.domain_config_path) if inputs.domain_config_path else None,
        "observation_contract_path": (
            str(inputs.observation_contract_path) if inputs.observation_contract_path else None
        ),
        "step_records": len(step_records),
        "predicates": len(predicates),
        "clip_result_ids": sorted({str(row.get("clip_result_id", "")) for row in ordered_events}),
        "missing_information": _missing_information_summary(step_records),
    }


def _step_record(
    row: dict[str, str],
    *,
    edges_by_event: dict[str, list[dict[str, str]]],
    component_by_id: dict[str, dict[str, str]],
    next_event_id: str | None,
    previous_event_id: str | None,
    inferred_end_frame: int | None,
    inferred_end_s: float | None,
    csv_files: ReasoningAdapterConfig,
    evidence_root: Path | None,
) -> dict[str, Any]:
    event_id = _event_id(row)
    step_id = _step_id(event_id)
    frame = _parse_int(row.get("frame:int"))
    time_s = _parse_float(row.get("time_s:float"))
    component_refs = _component_refs(event_id, edges_by_event=edges_by_event, component_by_id=component_by_id)
    missing_inputs = []
    if inferred_end_frame is None:
        missing_inputs.append("time_window.end_frame")
    if inferred_end_s is None:
        missing_inputs.append("time_window.end_s")
    evidence_paths = _available_evidence_paths(row, evidence_root=evidence_root)
    if not evidence_paths:
        missing_inputs.extend(
            [
                "state_sequence.csv",
                "frame_evidence.jsonl",
                "smoothed_frame_evidence.jsonl",
            ]
        )

    return {
        "schema_version": "thesis_reasoning_adapter.v1",
        "record_type": "step_segment",
        "id": step_id,
        "source_event_id": event_id,
        "clip_result_id": _blank_to_none(row.get("clip_result_id")),
        "run_id": _blank_to_none(row.get("run_id")),
        "mode": _blank_to_none(row.get("mode")),
        "archive_name": _blank_to_none(row.get("archive_name")),
        "clip": _blank_to_none(row.get("clip")),
        "index": _parse_int(row.get("local_event_id:int")),
        "sequence": {
            "previous_event_id": previous_event_id,
            "next_event_id": next_event_id,
            "source": f"{csv_files.event_next_csv} when present; local_event_id:int otherwise",
        },
        "time_window": {
            "start_frame": frame,
            "end_frame": inferred_end_frame,
            "start_s": time_s,
            "end_s": inferred_end_s,
            "source": (
                f"{csv_files.events_csv}: frame:int/time_s:float; "
                "end inferred from next distinct timestamp in the same clip when available"
            ),
            "notes": (
                "Existing graph stores step instants; end time is inferred from the next distinct "
                "event timestamp and remains null for the final timestamp group."
            ),
        },
        "action": {
            "name": _normalize_action(row),
            "event_type": _blank_to_none(row.get("event_type")),
            "description": _blank_to_none(row.get("action_desc")),
            "source": f"{csv_files.events_csv}: event_type/action_desc",
        },
        "objects": component_refs,
        "source_descriptions": [
            _source_description("display_name", row.get("display_name"), csv_files.events_csv),
            _source_description("name", row.get("name"), csv_files.events_csv),
            _source_description("action_desc", row.get("action_desc"), csv_files.events_csv),
        ],
        "confidence": _parse_float(row.get("conf:float")),
        "available_evidence_files": evidence_paths,
        "missing_inputs": sorted(set(missing_inputs)),
        "provenance": {
            "source": "existing_industreal_graph_csv",
            "source_files": [
                csv_files.events_csv,
                csv_files.event_component_csv,
                csv_files.event_next_csv,
                csv_files.components_csv,
            ],
        },
    }


def _infer_time_window_ends(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    by_clip: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_clip.setdefault(str(row.get("clip_result_id") or ""), []).append(row)

    inferred: dict[str, dict[str, Any]] = {}
    for clip_rows in by_clip.values():
        groups: list[dict[str, Any]] = []
        for row in clip_rows:
            time_s = _parse_float(row.get("time_s:float"))
            frame = _parse_int(row.get("frame:int"))
            if not groups or groups[-1]["time_s"] != time_s:
                groups.append({"time_s": time_s, "frame": frame, "rows": [row]})
            else:
                groups[-1]["rows"].append(row)

        for idx, group in enumerate(groups):
            next_group = _next_distinct_time_group(groups, idx)
            end_s = next_group["time_s"] if next_group else None
            end_frame = next_group["frame"] if next_group else None
            for row in group["rows"]:
                inferred[_event_id(row)] = {"end_s": end_s, "end_frame": end_frame}
    return inferred


def _next_distinct_time_group(groups: list[dict[str, Any]], idx: int) -> dict[str, Any] | None:
    current_time = groups[idx]["time_s"]
    for group in groups[idx + 1 :]:
        if group["time_s"] != current_time:
            return group
    return None


def _predicates_for_step(
    step_record: dict[str, Any],
    row: dict[str, str],
    *,
    edges_by_event: dict[str, list[dict[str, str]]],
    component_by_id: dict[str, dict[str, str]],
    predicate_defs: dict[str, dict[str, Any]],
    domain_config: dict[str, Any],
    observation_contract: dict[str, Any],
    csv_files: ReasoningAdapterConfig,
) -> list[dict[str, Any]]:
    event_id = str(step_record["source_event_id"])
    step_id = str(step_record["id"])
    conf = _parse_float(row.get("conf:float"))
    predicates: list[dict[str, Any]] = []
    predicates.extend(
        item
        for item in [
            _predicate_from_key(
                predicate_defs,
                "has_action",
                step_id,
                [step_id, step_record["action"]["name"]],
                conf,
                source_file=csv_files.events_csv,
                source_fields=["event_type", "action_desc"],
                notes=None
                if step_record["action"]["name"] is not None
                else "Action could not be normalized from event_type/action_desc.",
            ),
            _predicate_from_key(
                predicate_defs,
                "has_time_window",
                step_id,
                [
                    step_id,
                    step_record["time_window"]["start_s"],
                    step_record["time_window"]["end_s"],
                ],
                conf,
                source_file=csv_files.events_csv,
                source_fields=["frame:int", "time_s:float"],
                notes=(
                    "End time is inferred from the next distinct event timestamp in the same clip "
                    "when available; it is null for the final timestamp group."
                ),
            ),
        ]
        if item is not None
    )
    for edge in edges_by_event.get(event_id, []):
        source_component_id = edge.get(":END_ID(Component)", "")
        component_id = _domain_individual_id(domain_config, source_component_id)
        component = component_by_id.get(source_component_id, {})
        domain_entry = _effective_domain_entry(domain_config, source_component_id)
        component_label = (
            _blank_to_none(domain_entry.get("name"))
            or _blank_to_none(component.get("name"))
            or _label_from_component_id(source_component_id)
        )
        component_type = _blank_to_none(component.get("normalized_name")) or _normalize_token(component_label)
        has_domain_type = bool(_blank_to_none(domain_entry.get("generic_type")))
        edge_role = str(edge.get("role") or "component").lower()
        relation_key = "uses_tool" if edge_role == "tool" else "uses_object"
        role_note = None
        if relation_key == "uses_object":
            role_note = "Existing graph marks this ACTS_ON edge as a component; no tool-specific role was available."
        interaction_predicate = _predicate_from_key(
            predicate_defs,
            relation_key,
            step_id,
            [step_id, component_id],
            conf,
            source_file=csv_files.event_component_csv,
            source_fields=[":START_ID(AssemblyEvent)", ":END_ID(Component)", "role"],
            notes=role_note,
        )
        observed_target_predicates = []
        if relation_key == "uses_object" and step_record["action"]["name"] == "install":
            observed_target_predicates = _observed_install_target_predicates(
                predicate_defs,
                observation_contract,
                domain_config,
                row,
                step_id=step_id,
                component_id=component_id,
                event_conf=conf,
                source_file=csv_files.events_csv,
            )
        type_predicate = None
        if not has_domain_type:
            type_predicate = _predicate_from_key(
                predicate_defs,
                "is_a",
                step_id,
                [component_id, component_type],
                conf,
                source_file=csv_files.components_csv,
                source_fields=["component_id:ID(Component)", "name", "normalized_name"],
                notes="Component type is derived from the existing component normalized_name, not from a richer ontology.",
            )
        label_predicate = _predicate_from_key(
            predicate_defs,
            "has_label",
            step_id,
            [component_id, component_label],
            conf,
            source_file=csv_files.components_csv,
            source_fields=["component_id:ID(Component)", "display_name", "name"],
            notes=None,
        )
        domain_predicates = _domain_predicates_for_component(
            predicate_defs,
            domain_config,
            step_id,
            source_component_id,
            component_id,
            conf,
            action_description=_blank_to_none(row.get("action_desc")),
            source_file=csv_files.events_csv,
        )
        predicates.extend(
            item
            for item in [
                interaction_predicate,
                type_predicate,
                label_predicate,
                *observed_target_predicates,
                *domain_predicates,
            ]
            if item is not None
        )
    return predicates


def _observed_install_target_predicates(
    predicate_defs: dict[str, dict[str, Any]],
    observation_contract: dict[str, Any],
    domain_config: dict[str, Any],
    row: dict[str, str],
    *,
    step_id: str,
    component_id: str,
    event_conf: float | None,
    source_file: str,
) -> list[dict[str, Any] | None]:
    target_config = observation_contract["installation_target"]
    fields = target_config["event_fields"]
    target_field = str(fields["target"])
    raw_target = _blank_to_none(row.get(target_field))
    if raw_target is None:
        if target_config["missing_observation_policy"] != "domain_assumed":
            return []
        return [
            _predicate_from_key(
                predicate_defs,
                "allows_domain_assumed_install_target",
                step_id,
                [step_id, component_id],
                event_conf,
                source_file=str(observation_contract["_source_path"]),
                source_fields=["installation_target", "missing_observation_policy"],
                notes="No observed installation target was supplied; domain-assumed fallback is enabled.",
                source_type="configuration",
            )
        ]

    observed_target = _resolve_observed_entity_id(domain_config, raw_target)
    confidence_field = str(fields["confidence"])
    observed_conf = _parse_float(row.get(confidence_field))
    if observed_conf is None and target_config["fallback_to_event_confidence"]:
        observed_conf = event_conf
    source_type_field = str(fields["source_type"])
    source_type = _blank_to_none(row.get(source_type_field)) or str(target_config["default_source_type"])
    return [
        _predicate_from_key(
            predicate_defs,
            "observed_install_target",
            step_id,
            [step_id, component_id, observed_target],
            observed_conf,
            source_file=source_file,
            source_fields=[target_field, confidence_field, source_type_field],
            notes="Observed target is preserved independently from the expected domain installation target.",
            source_type=source_type,
        )
    ]


def _domain_predicates_for_component(
    predicate_defs: dict[str, dict[str, Any]],
    domain_config: dict[str, Any],
    step_id: str,
    source_component_id: str,
    individual_id: str,
    conf: float | None,
    *,
    action_description: str | None,
    source_file: str,
) -> list[dict[str, Any]]:
    entry = _effective_domain_entry(domain_config, source_component_id)
    if not entry:
        return []

    output: list[dict[str, Any] | None] = []
    generic_type = _blank_to_none(entry.get("generic_type"))
    for type_name in _type_closure(domain_config, generic_type):
        output.append(
            _domain_predicate(
                predicate_defs,
                "is_a",
                step_id,
                [individual_id, type_name],
                conf,
                fields=["components", source_component_id, "generic_type"],
            )
        )

    parent = _domain_individual_id(domain_config, _blank_to_none(entry.get("parent_component")))
    if parent:
        output.append(
            _domain_predicate(
                predicate_defs,
                "has_parent_component",
                step_id,
                [individual_id, parent],
                conf,
                fields=["components", source_component_id, "parent_component"],
            )
        )

    installation_target_source = _blank_to_none(entry.get("installation_target"))
    installation_target = _domain_individual_id(domain_config, installation_target_source)
    if installation_target:
        output.append(
            _domain_predicate(
                predicate_defs,
                "has_install_target",
                step_id,
                [individual_id, installation_target],
                conf,
                fields=["components", source_component_id, "installation_target"],
            )
        )
        target_entry = _effective_domain_entry(domain_config, installation_target_source)
        if isinstance(target_entry, dict):
            target_support = _domain_individual_id(domain_config, _blank_to_none(target_entry.get("installation_target")))
            if target_support:
                output.append(
                    _domain_predicate(
                        predicate_defs,
                        "requires_installed_before",
                        step_id,
                        [individual_id, installation_target, target_support],
                        conf,
                        fields=["components", source_component_id, "installation_target"],
                    )
                )

    required_tool = _blank_to_none(entry.get("required_tool"))
    if required_tool:
        output.append(
            _domain_predicate(
                predicate_defs,
                "has_required_tool",
                step_id,
                [individual_id, required_tool],
                conf,
                fields=["components", source_component_id, "required_tool"],
            )
        )

    for idx, condition in enumerate(entry.get("required_conditions", []) or []):
        if not isinstance(condition, dict):
            continue
        condition_name = _blank_to_none(condition.get("name"))
        args = _resolve_domain_args(condition.get("args", []), individual_id, entry, domain_config)
        if condition_name and len(args) == 2:
            output.append(
                _domain_predicate(
                    predicate_defs,
                    "has_required_condition",
                    step_id,
                    [individual_id, condition_name, *args],
                    conf,
                    fields=["components", source_component_id, "required_conditions", str(idx)],
                )
            )

    for idx, requirement in enumerate(entry.get("safety_requirements", []) or []):
        if not isinstance(requirement, dict):
            continue
        requirement_name = _blank_to_none(requirement.get("name"))
        args = _resolve_domain_args(requirement.get("args", []), individual_id, entry, domain_config)
        if requirement_name and len(args) == 2:
            output.append(
                _domain_predicate(
                    predicate_defs,
                    "has_safety_requirement",
                    step_id,
                    [individual_id, requirement_name, *args],
                    conf,
                    fields=["components", source_component_id, "safety_requirements", str(idx)],
                )
            )

    for idx, effect in enumerate(entry.get("observed_effects", []) or []):
        if not isinstance(effect, dict):
            continue
        effect_name = _blank_to_none(effect.get("name"))
        description_pattern = _blank_to_none(effect.get("description_pattern"))
        args = _resolve_domain_args(effect.get("args", []), individual_id, entry, domain_config)
        if (
            effect_name
            and description_pattern
            and action_description
            and len(args) == 2
            and re.search(description_pattern, action_description, flags=re.IGNORECASE)
        ):
            output.append(
                _predicate_from_key(
                    predicate_defs,
                    "has_observed_effect",
                    step_id,
                    [step_id, effect_name, *args],
                    conf,
                    source_file=source_file,
                    source_fields=["action_desc"],
                    notes=(
                        "Explicit effect extracted from the step annotation using "
                        f"type_defaults observed_effects pattern {description_pattern!r}."
                    ),
                )
            )
    return [item for item in output if item is not None]


def _domain_predicate(
    predicate_defs: dict[str, dict[str, Any]],
    key: str,
    step_id: str,
    args: list[Any],
    conf: float | None,
    *,
    fields: list[str],
) -> dict[str, Any] | None:
    return _predicate_from_key(
        predicate_defs,
        key,
        step_id,
        args,
        conf,
        source_file="config/domain_config.yaml",
        source_fields=fields,
        notes="Derived from manually authored domain_config.yaml.",
    )


def _resolve_domain_args(args: Any, component_id: str, entry: dict[str, Any], domain_config: dict[str, Any]) -> list[Any]:
    output = []
    for arg in list(args or []):
        if arg == "$self":
            output.append(component_id)
        elif arg == "$installation_target":
            output.append(_domain_individual_id(domain_config, _blank_to_none(entry.get("installation_target"))))
        elif arg == "$installation_target_target":
            installation_target = _blank_to_none(entry.get("installation_target"))
            target_entry = _effective_domain_entry(domain_config, installation_target)
            output.append(
                _domain_individual_id(
                    domain_config,
                    _blank_to_none(target_entry.get("installation_target")),
                )
            )
        elif arg == "$parent_component":
            output.append(_domain_individual_id(domain_config, _blank_to_none(entry.get("parent_component"))))
        else:
            output.append(_domain_individual_id(domain_config, _blank_to_none(arg)) or arg)
    return output


def _predicate_from_key(
    predicate_defs: dict[str, dict[str, Any]],
    key: str,
    step_id: str,
    args: list[Any],
    conf: float | None,
    *,
    source_file: str,
    source_fields: list[str],
    notes: str | None,
    source_type: str = "existing_graph_csv",
) -> dict[str, Any] | None:
    predicate_def = predicate_defs.get(key)
    if predicate_def is None:
        raise KeyError(f"missing adapter predicate definition: {key}")
    if not predicate_def.get("enabled", True):
        return None
    return _predicate(
        step_id,
        str(predicate_def["name"]),
        args,
        conf,
        source_file=source_file,
        source_fields=source_fields,
        notes=notes,
        source_type=source_type,
        category=_blank_to_none(predicate_def.get("category")),
        predicate_key=key,
    )


def _predicate(
    step_id: str,
    name: str,
    args: list[Any],
    conf: float | None,
    *,
    source_file: str,
    source_fields: list[str],
    notes: str | None,
    category: str | None,
    predicate_key: str | None,
    source_type: str = "existing_graph_csv",
) -> dict[str, Any]:
    suffix = _normalize_token("_".join(str(arg) for arg in args if arg is not None))[:96]
    return {
        "schema_version": "thesis_reasoning_adapter.v1",
        "record_type": "predicate",
        "id": f"{step_id}::p::{name}::{suffix}",
        "step_id": step_id,
        "name": name,
        "predicate_key": predicate_key,
        "category": category,
        "args": args,
        "conf": conf,
        "source": {
            "type": source_type,
            "file": source_file,
            "fields": source_fields,
        },
        "notes": notes,
    }


def _load_predicate_defs(config_path: Path | None) -> dict[str, dict[str, Any]]:
    if config_path is None:
        raise ValueError("adapter predicate config path is required")

    config = _load_config(Path(config_path))
    configured = config.get("adapter", {}).get("predicates", {})
    if not configured:
        raise ValueError(f"adapter predicate config missing adapter.predicates: {config_path}")

    flattened: dict[str, dict[str, Any]] = {}
    for category, entries in configured.items():
        if not isinstance(entries, dict):
            raise ValueError(f"adapter predicate category must be a mapping: {category}")
        for key, value in entries.items():
            if not isinstance(value, dict):
                raise ValueError(f"adapter predicate definition must be a mapping: {category}.{key}")
            name = value.get("name")
            if not name:
                raise ValueError(f"adapter predicate definition missing name: {category}.{key}")
            flattened[str(key)] = {
                **value,
                "name": str(name),
                "category": str(category),
                "enabled": bool(value.get("enabled", True)),
            }

    missing_keys = [key for key in REQUIRED_PREDICATE_KEYS if key not in flattened]
    if missing_keys:
        raise ValueError(f"adapter predicate config missing required keys: {', '.join(missing_keys)}")
    return flattened


def _load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ImportError:
        return json.loads(text)
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"config must be a mapping: {path}")
    return loaded


def _load_domain_config(config_path: Path | None) -> dict[str, Any]:
    if config_path is None:
        return {"components": {}, "entities": {}}
    config = _load_config(Path(config_path))
    if not isinstance(config.get("components", {}), dict):
        raise ValueError(f"domain config components must be a mapping: {config_path}")
    _validate_domain_config(config, Path(config_path))
    return config


def _load_observation_contract(config_path: Path | None) -> dict[str, Any]:
    if config_path is None:
        raise ValueError("observation contract config path is required")
    path = Path(config_path)
    config = _load_config(path)
    target_config = config.get("installation_target")
    if not isinstance(target_config, dict):
        raise ValueError(f"observation contract missing installation_target mapping: {path}")
    required = (
        "missing_observation_policy",
        "supported_missing_observation_policies",
        "event_fields",
        "fallback_to_event_confidence",
        "default_source_type",
    )
    missing = [key for key in required if key not in target_config]
    if missing:
        raise ValueError(f"observation contract installation_target missing: {', '.join(missing)}")
    supported = list(target_config["supported_missing_observation_policies"] or [])
    policy = str(target_config["missing_observation_policy"])
    if policy not in supported:
        raise ValueError(
            f"unsupported missing installation-target observation policy '{policy}' in {path}; "
            f"expected one of: {', '.join(str(item) for item in supported)}"
        )
    fields = target_config["event_fields"]
    if not isinstance(fields, dict):
        raise ValueError(f"observation contract installation_target.event_fields must be a mapping: {path}")
    missing_fields = [key for key in ("target", "confidence", "source_type") if not fields.get(key)]
    if missing_fields:
        raise ValueError(
            f"observation contract installation_target.event_fields missing: {', '.join(missing_fields)}"
        )
    return {**config, "_source_path": path}


def _resolve_observed_entity_id(domain_config: dict[str, Any], raw_value: str) -> str:
    direct = _domain_individual_id(domain_config, raw_value)
    components = domain_config.get("components", {})
    entities = domain_config.get("entities", {})
    if raw_value in components or raw_value in entities:
        return str(direct)
    normalized = _normalize_token(raw_value)
    for entries in (components, entities):
        for source_id, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            candidates = (
                source_id,
                entry.get("name"),
                entry.get("display_name"),
            )
            if any(_normalize_token(candidate) == normalized for candidate in candidates if candidate):
                return str(_domain_individual_id(domain_config, str(source_id)))
    return str(direct)


def _domain_individual_id(domain_config: dict[str, Any], source_id: str | None) -> str | None:
    if not source_id:
        return None
    components = domain_config.get("components", {})
    entry = components.get(source_id)
    if isinstance(entry, dict):
        return _blank_to_none(entry.get("name")) or source_id
    entities = domain_config.get("entities", {})
    entity = entities.get(source_id)
    if isinstance(entity, dict):
        return _blank_to_none(entity.get("name")) or source_id
    return source_id


def _effective_domain_entry(domain_config: dict[str, Any], source_component_id: str | None) -> dict[str, Any]:
    if not source_component_id:
        return {}
    components = domain_config.get("components", {})
    entry = components.get(source_component_id)
    if not isinstance(entry, dict):
        return {}
    effective: dict[str, Any] = {}
    for type_name in reversed(_type_closure(domain_config, _blank_to_none(entry.get("generic_type")))):
        defaults = domain_config.get("type_defaults", {}).get(type_name)
        if isinstance(defaults, dict):
            for key, value in defaults.items():
                effective.setdefault(key, value)
    effective.update(entry)
    return effective


def _type_closure(domain_config: dict[str, Any], type_name: str | None) -> list[str]:
    if not type_name:
        return []
    hierarchy = domain_config.get("type_hierarchy", {})
    output: list[str] = []
    seen: set[str] = set()

    def visit(current: str) -> None:
        if current in seen:
            return
        seen.add(current)
        output.append(current)
        entry = hierarchy.get(current, {})
        parents = entry.get("parents", []) if isinstance(entry, dict) else []
        for parent in parents or []:
            visit(str(parent))

    visit(str(type_name))
    return output


def _validate_domain_config(config: dict[str, Any], path: Path) -> None:
    vocabulary = config.get("condition_vocabulary", {})
    if not isinstance(vocabulary, dict):
        raise ValueError(f"domain config condition_vocabulary must be a mapping: {path}")
    type_hierarchy = config.get("type_hierarchy", {})
    if not isinstance(type_hierarchy, dict):
        raise ValueError(f"domain config type_hierarchy must be a mapping: {path}")

    for type_name, entry in config.get("type_defaults", {}).items():
        if not isinstance(entry, dict):
            raise ValueError(f"domain config type default must be a mapping: type_defaults.{type_name}")
        _validate_condition_list(entry, vocabulary, path, ["type_defaults", str(type_name), "required_conditions"])
        _validate_condition_list(entry, vocabulary, path, ["type_defaults", str(type_name), "safety_requirements"])
        _validate_observed_effects(entry, vocabulary, path, ["type_defaults", str(type_name), "observed_effects"])

    for component_id, entry in config.get("components", {}).items():
        if not isinstance(entry, dict):
            raise ValueError(f"domain config component must be a mapping: components.{component_id}")
        generic_type = _blank_to_none(entry.get("generic_type"))
        if generic_type and generic_type not in type_hierarchy:
            raise ValueError(f"domain config unknown generic_type '{generic_type}' at components.{component_id}")
        _validate_condition_list(entry, vocabulary, path, ["components", str(component_id), "required_conditions"])
        _validate_condition_list(entry, vocabulary, path, ["components", str(component_id), "safety_requirements"])
        _validate_observed_effects(entry, vocabulary, path, ["components", str(component_id), "observed_effects"])


def _validate_condition_list(
    entry: dict[str, Any],
    vocabulary: dict[str, Any],
    path: Path,
    fields: list[str],
) -> None:
    list_name = fields[-1]
    for idx, condition in enumerate(entry.get(list_name, []) or []):
        if not isinstance(condition, dict):
            raise ValueError(f"domain config condition must be a mapping at {'.'.join(fields + [str(idx)])}")
        name = _blank_to_none(condition.get("name"))
        if not name or name not in vocabulary:
            raise ValueError(
                f"domain config unknown condition '{name}' at {'.'.join(fields + [str(idx)])}; "
                f"add it to condition_vocabulary in {path}"
            )
        vocab_entry = vocabulary.get(name)
        expected_arity = int(vocab_entry.get("arity")) if isinstance(vocab_entry, dict) else None
        actual_arity = len(list(condition.get("args", []) or []))
        if expected_arity is not None and actual_arity != expected_arity:
            raise ValueError(
                f"domain config condition '{name}' at {'.'.join(fields + [str(idx)])} has arity "
                f"{actual_arity}, expected {expected_arity}"
            )


def _validate_observed_effects(
    entry: dict[str, Any],
    vocabulary: dict[str, Any],
    path: Path,
    fields: list[str],
) -> None:
    _validate_condition_list(entry, vocabulary, path, fields)
    list_name = fields[-1]
    for idx, effect in enumerate(entry.get(list_name, []) or []):
        pattern = _blank_to_none(effect.get("description_pattern"))
        location = ".".join(fields + [str(idx)])
        if not pattern:
            raise ValueError(f"domain config observed effect missing description_pattern at {location}")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"domain config invalid description_pattern at {location}: {exc}") from exc


def _filter_events(
    rows: list[dict[str, str]],
    *,
    clip_result_id: str | None,
    mode: str | None,
    archive_name: str | None,
    clip: str | None,
) -> list[dict[str, str]]:
    output = []
    for row in rows:
        if clip_result_id and row.get("clip_result_id") != clip_result_id:
            continue
        if mode and row.get("mode") != mode:
            continue
        if archive_name and row.get("archive_name") != archive_name:
            continue
        if clip and row.get("clip") != clip:
            continue
        output.append(row)
    return output


def _component_refs(
    event_id: str,
    *,
    edges_by_event: dict[str, list[dict[str, str]]],
    component_by_id: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    refs = []
    for edge in edges_by_event.get(event_id, []):
        component_id = edge.get(":END_ID(Component)", "")
        component = component_by_id.get(component_id, {})
        refs.append(
            {
                "id": component_id or None,
                "label": _blank_to_none(component.get("name")) or _label_from_component_id(component_id),
                "type": _blank_to_none(component.get("normalized_name")),
                "role": _blank_to_none(edge.get("role")) or "component",
                "source_edge_type": _blank_to_none(edge.get(":TYPE")),
            }
        )
    return refs


def _available_evidence_paths(row: dict[str, str], *, evidence_root: Path | None) -> dict[str, str]:
    if evidence_root is None:
        return {}
    mode = row.get("mode")
    archive_name = row.get("archive_name")
    clip = row.get("clip")
    if not mode or not archive_name or not clip:
        return {}
    clip_dir = Path(evidence_root) / "modes" / mode / archive_name / clip
    candidates = {
        "state_sequence": clip_dir / "state_sequence.csv",
        "frame_evidence": clip_dir / "frame_evidence.jsonl",
        "smoothed_frame_evidence": clip_dir / "smoothed_frame_evidence.jsonl",
    }
    return {key: str(path) for key, path in candidates.items() if path.exists()}


def _normalize_action(row: dict[str, str]) -> str | None:
    event_type = str(row.get("event_type") or "").strip().lower()
    if event_type:
        return event_type
    action_desc = str(row.get("action_desc") or "").strip().lower()
    if not action_desc:
        return None
    return action_desc.split(maxsplit=1)[0]


def _source_description(kind: str, value: str | None, source_file: str) -> dict[str, Any]:
    return {
        "type": kind,
        "text": _blank_to_none(value),
        "source": source_file,
    }


def _missing_information_summary(step_records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in step_records:
        for item in record.get("missing_inputs", []):
            counts[str(item)] = counts.get(str(item), 0) + 1
    return dict(sorted(counts.items()))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _event_id(row: dict[str, str]) -> str:
    return str(row.get("event_id:ID(AssemblyEvent)") or "")


def _component_id(row: dict[str, str]) -> str:
    return str(row.get("component_id:ID(Component)") or "")


def _step_id(event_id: str) -> str:
    return f"step::{event_id}"


def _label_from_component_id(component_id: str) -> str | None:
    if not component_id:
        return None
    return component_id.rsplit("::", 1)[-1].replace("_", " ")


def _normalize_token(value: Any) -> str:
    text = str(value or "unknown").lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return cleaned or "unknown"


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _parse_int(value: str | None, *, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    return int(float(value))


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
