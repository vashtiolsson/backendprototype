"""
Transformation engine for the Person concept.

Reads:
  data/raw/*.csv          synthetic SSBTEK source data, at project root
  src/mappings/person.json declarative Person rules

Run from the project root:
  python -m src.transform.person
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.models.person import Person


PROJECT_ROOT  = Path(__file__).resolve().parent.parent.parent
DATA_DIR      = PROJECT_ROOT / "data" / "raw"
MAPPINGS_FILE = PROJECT_ROOT / "src" / "mappings" / "person.json"

JANE_PNR = "20000421-1234"


# ── Loading ───────────────────────────────────────────────────────────────────

def load_mappings(path: Path = MAPPINGS_FILE) -> list[dict]:
    """Return the list of rules from the mapping spec file."""
    return json.loads(path.read_text(encoding="utf-8"))["rules"]


# ── Value parsing ─────────────────────────────────────────────────────────────

def _safe_text(value: str | None) -> str | None:
    """Normalize a source text value."""
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


# ── Core transformation ───────────────────────────────────────────────────────

def transform_person(
    personal_id: str,
    mappings: list[dict] | None = None,
    data_dir: Path = DATA_DIR,
) -> Person | None:
    """
    Resolve one Person instance from the source data.

    Since Person only contains personId, the first matching personal_id found
    in any mapped source file is enough to create the ontology-level Person.
    """
    if mappings is None:
        mappings = load_mappings()

    for rule in mappings:
        source_file = rule["source_file"]
        source_field = rule["source_field"]

        matching_files = (
            sorted(data_dir.glob("*.csv"))
            if source_file == "*"
            else [data_dir / source_file]
        )

        for path in matching_files:
            if not path.exists():
                print(f"  ⚠  {path.name} not found at {path} — skipping")
                continue

            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    source_value = _safe_text(row.get(source_field))

                    if source_value == personal_id:
                        return Person(person_id=source_value)

    return None


# ── Demo: resolve Jane as Person ──────────────────────────────────────────────

def demo_jane() -> None:
    print("=" * 64)
    print(f"  Resolving Person concept for {JANE_PNR} (Jane Doe)")
    print("=" * 64)
    print()
    print(f"  Project root: {PROJECT_ROOT}")
    print(f"  Data dir:     {DATA_DIR}")
    print(f"  Mappings:     {MAPPINGS_FILE}")
    print()

    person = transform_person(JANE_PNR)

    if person is None:
        print("  No Person found. Did you run synthetic.py first?")
        print(f"  Expected CSVs in: {DATA_DIR}")
        return

    print("Found Person instance:\n")
    print(f"  personId = {person.person_id}")


if __name__ == "__main__":
    demo_jane()