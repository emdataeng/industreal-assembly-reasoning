#!/usr/bin/env python3
"""Rebuild reasoning artifacts for every clip and import all procedural graphs.

The script reads unique clip_result_id values from nodes_events.csv, rebuilds
adapter outputs, Layer 3 constraints, Layer 4 validations, and procedural
reasoning graphs for each clip/mode, then imports the rebuilt graphs to Neo4j.

Neo4j import happens only after every local rebuild succeeds. Each graph is
named with its clip_result_id and replaces only the existing Neo4j subgraph with
the same graph_name, so all clips remain present while stale nodes for rebuilt
clips are removed.
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUN_ID = "raw_cad_dataset__all_test_clips"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--csv-dir", type=Path, default=None)
    parser.add_argument("--reasoning-root", type=Path, default=Path("results/reasoning_layers"))
    parser.add_argument(
        "--graph-root",
        type=Path,
        default=Path("results/procedural_reasoning_graph"),
    )
    parser.add_argument("--rules", type=Path, default=Path("config/thesis_rules.yaml"))
    parser.add_argument("--domain-config", type=Path, default=Path("config/domain_config.yaml"))
    parser.add_argument("--validation-config", type=Path, default=Path("config/thesis_rules.yaml"))
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--clip-result-id",
        action="append",
        default=None,
        help=(
            "Optional clip_result_id filter. Can be passed multiple times. "
            "By default all clip_result_id values in nodes_events.csv are rebuilt."
        ),
    )
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Rebuild local artifacts but do not import graphs into Neo4j.",
    )
    parser.add_argument(
        "--drop-legacy-prg-id-constraints",
        action="store_true",
        help="Forwarded to script 18 on the first Neo4j import.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run without executing them.",
    )
    args = parser.parse_args()

    csv_dir = args.csv_dir or Path("results/neo4j") / args.run_id
    events_csv = csv_dir / "nodes_events.csv"
    clip_ids = args.clip_result_id or read_clip_result_ids(events_csv)
    if not clip_ids:
        raise SystemExit(f"No clip_result_id values found in {events_csv}")

    print(f"Found {len(clip_ids)} clip/mode result(s) to rebuild.")
    rebuilt_graph_dirs: list[Path] = []
    for index, clip_id in enumerate(clip_ids, start=1):
        folder_id = sanitize_clip_result_id(clip_id)
        reasoning_dir = args.reasoning_root / folder_id
        graph_dir = args.graph_root / folder_id
        print(f"\n[{index}/{len(clip_ids)}] Rebuilding {clip_id}")

        run(
            [
                sys.executable,
                script("14_build_layer3_reasoning_adapter.py"),
                "--run-id",
                args.run_id,
                "--csv-dir",
                csv_dir,
                "--output-dir",
                reasoning_dir,
                "--clip-result-id",
                clip_id,
                "--domain-config",
                args.domain_config,
            ],
            dry_run=args.dry_run,
        )
        run(
            [
                sys.executable,
                script("15_run_layer3_inference.py"),
                "--step-records",
                reasoning_dir / "step_records.jsonl",
                "--predicates",
                reasoning_dir / "predicates.jsonl",
                "--rules",
                args.rules,
                "--output",
                reasoning_dir / "inferred_constraints.csv",
            ],
            dry_run=args.dry_run,
        )
        run(
            [
                sys.executable,
                script("16_run_layer4_validation.py"),
                "--step-records",
                reasoning_dir / "step_records.jsonl",
                "--predicates",
                reasoning_dir / "predicates.jsonl",
                "--constraints",
                reasoning_dir / "inferred_constraints.csv",
                "--rule-coverage",
                reasoning_dir / "rule_coverage_diagnostics.csv",
                "--output",
                reasoning_dir / "validation_records.jsonl",
                "--config",
                args.validation_config,
            ],
            dry_run=args.dry_run,
        )
        run(
            [
                sys.executable,
                script("17_build_procedural_reasoning_graph.py"),
                "--validations",
                reasoning_dir / "validation_records.jsonl",
                "--step-records",
                reasoning_dir / "step_records.jsonl",
                "--predicates",
                reasoning_dir / "predicates.jsonl",
                "--constraints",
                reasoning_dir / "inferred_constraints.csv",
                "--domain-config",
                args.domain_config,
                "--rules",
                args.rules,
                "--validation-config",
                args.validation_config,
                "--output-dir",
                graph_dir,
                "--graph-name",
                f"procedural_reasoning_graph::{clip_id}",
            ],
            dry_run=args.dry_run,
        )
        rebuilt_graph_dirs.append(graph_dir)

    print(f"\nSuccessfully rebuilt {len(rebuilt_graph_dirs)} graph(s).")
    if args.skip_import:
        print("Skipping Neo4j import because --skip-import was passed.")
        return

    print("\nImporting rebuilt procedural graphs into Neo4j.")
    for index, graph_dir in enumerate(rebuilt_graph_dirs, start=1):
        command: list[object] = [
            sys.executable,
            script("18_import_procedural_reasoning_graph_neo4j.py"),
            "--graph",
            graph_dir,
            "--env-file",
            args.env_file,
            "--batch-size",
            args.batch_size,
        ]
        if index == 1 and args.drop_legacy_prg_id_constraints:
            command.append("--drop-legacy-prg-id-constraints")
        print(f"\n[{index}/{len(rebuilt_graph_dirs)}] Importing {graph_dir}")
        run(command, dry_run=args.dry_run)

    print(f"\nDone. Rebuilt and imported {len(rebuilt_graph_dirs)} procedural graph(s).")


def read_clip_result_ids(events_csv: Path) -> list[str]:
    if not events_csv.exists():
        raise SystemExit(f"Missing events CSV: {events_csv}")
    seen: set[str] = set()
    clip_ids: list[str] = []
    with open(events_csv, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            clip_id = str(row.get("clip_result_id") or "").strip()
            if clip_id and clip_id not in seen:
                seen.add(clip_id)
                clip_ids.append(clip_id)
    return sorted(clip_ids)


def sanitize_clip_result_id(clip_id: str) -> str:
    return clip_id.replace("::", "__")


def script(name: str) -> Path:
    return ROOT / "scripts" / name


def run(command: list[object], *, dry_run: bool) -> None:
    text_command = [str(part) for part in command]
    print(" ".join(quote_for_display(part) for part in text_command))
    if dry_run:
        return
    subprocess.run(text_command, cwd=ROOT, check=True)


def quote_for_display(value: str) -> str:
    if any(char.isspace() for char in value):
        return f'"{value}"'
    return value


if __name__ == "__main__":
    main()
