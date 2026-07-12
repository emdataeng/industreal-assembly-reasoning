#!/usr/bin/env python3
"""Build thesis Layer 1/2 adapter outputs from existing IndustReal graph CSVs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.layer3_reasoning_adapter import (
    DEFAULT_ADAPTER_CONFIG_PATH,
    AdapterInputs,
    build_reasoning_adapter_outputs,
    load_adapter_config,
)


def main() -> None:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--adapter-config", type=Path, default=DEFAULT_ADAPTER_CONFIG_PATH)
    bootstrap_args, _ = bootstrap.parse_known_args()
    adapter_config = load_adapter_config(bootstrap_args.adapter_config)

    parser = argparse.ArgumentParser(parents=[bootstrap])
    parser.add_argument("--run-id", type=str, default=adapter_config.run_id)
    parser.add_argument("--csv-dir", type=Path, default=adapter_config.csv_dir)
    parser.add_argument("--output-root", type=Path, default=adapter_config.output_root)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--clip-result-id", type=str, default=None)
    parser.add_argument("--mode", type=str, default=None)
    parser.add_argument("--archive", type=str, default=None)
    parser.add_argument("--clip", type=str, default=None)
    parser.add_argument("--evidence-root", type=Path, default=None)
    parser.add_argument("--predicate-config", type=Path, default=adapter_config.predicate_config_path)
    parser.add_argument("--domain-config", type=Path, default=adapter_config.domain_config_path)
    parser.add_argument(
        "--observation-contract",
        type=Path,
        default=adapter_config.observation_contract_path,
    )
    args = parser.parse_args()

    output_dir = args.output_dir or (args.output_root / args.run_id)
    result = build_reasoning_adapter_outputs(
        AdapterInputs(
            csv_dir=args.csv_dir,
            run_id=args.run_id,
            output_dir=output_dir,
            clip_result_id=args.clip_result_id,
            mode=args.mode,
            archive_name=args.archive,
            clip=args.clip,
            evidence_root=args.evidence_root,
            adapter_config_path=args.adapter_config,
            predicate_config_path=args.predicate_config,
            domain_config_path=args.domain_config,
            observation_contract_path=args.observation_contract,
        )
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
