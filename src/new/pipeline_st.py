"""
End-to-end driver for the SupportType pipeline.

Runs reasoner -> matcher -> transformer, persists the transformation, and
produces a single ``demo_snapshot.json`` file the HTML demo consumes.

Usage:
    python3 -m src.new.pipeline                  # runs and persists
    python3 -m src.new.pipeline --no-persist     # dry run, no disk writes
    python3 -m src.new.pipeline --snapshot       # also write demo snapshot
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.new.matcher_st import DEFAULT_PERSON_ID, match_support_type
from src.new.reasoner_st import run_support_type_reasoner
from src.new.storage_st import (
    list_transformations,
    load_all_rules,
    load_system_rules,
    load_user_rules,
)
from src.new.transformer_st import transform_support_type_matches


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEMO_SNAPSHOT = PROJECT_ROOT / "demo" / "demo_snapshot.json"


def run(person_id: str = DEFAULT_PERSON_ID, persist: bool = True) -> dict[str, Any]:
    reasoner_output = run_support_type_reasoner(person_id=person_id)
    matcher_output = match_support_type(
        person_id=person_id, reasoner_output=reasoner_output
    )
    transformer_output = transform_support_type_matches(matcher_output)

    return {
        "person_id": person_id,
        "reasoner": reasoner_output,
        "matcher": matcher_output,
        "transformer": transformer_output,
    }


def write_demo_snapshot(payload: dict[str, Any]) -> Path:
    DEMO_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        **payload,
        "rules": {
            "system": load_system_rules(),
            "user": load_user_rules(),
            "all": load_all_rules(),
        },
        "transformations": list_transformations(),
    }
    DEMO_SNAPSHOT.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    return DEMO_SNAPSHOT


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--person", default=DEFAULT_PERSON_ID)
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--snapshot", action="store_true",
                        help="write demo/demo_snapshot.json after the run")
    args = parser.parse_args()

    payload = run(person_id=args.person, persist=not args.no_persist)

    if args.snapshot:
        out = write_demo_snapshot(payload)
        print(f"\nWrote {out}")
