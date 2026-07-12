#!/usr/bin/env python3
"""Run thesis Layer 3 rule-based inference over Layer 1/2 records."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.layer3_inference import DEFAULT_RULES_PATH, Layer3Inputs, run_layer3_inference


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step-records", type=Path, required=True)
    parser.add_argument("--predicates", type=Path, required=True)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = run_layer3_inference(
        Layer3Inputs(
            step_records_path=args.step_records,
            predicates_path=args.predicates,
            rules_path=args.rules,
            output_path=args.output,
        )
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
