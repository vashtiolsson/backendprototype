from __future__ import annotations

import json
from pathlib import Path


MAPPINGS_FILE = Path(__file__).resolve().parent / "period.json"


def demo_jane() -> None:
    print("=" * 64)
    print("TimePeriod mapping rules")
    print("=" * 64)
    print()

    data = json.loads(MAPPINGS_FILE.read_text(encoding="utf-8"))

    print(f"Concept: {data['concept']}")
    print(f"Ontology: {data['ontology_iri']}")
    print()

    print(f"Found {len(data['rules'])} mapping rule(s):")
    print()

    for rule in data["rules"]:
        end_field = rule["end_field"] or "N/A"
        print(
            f"  {rule['source_file']:35s} "
            f"{rule['start_field']:20s} → {end_field:20s}"
            f"  [{rule['format']}]"
        )
        print(
            f"      target={rule['target_class']}.{rule['start_property']}"
            f" / {rule['end_property']}"
        )
        print(f"      transformation={rule['transformation']}")
        print(f"      rationale={rule['rationale']}")
        print()


if __name__ == "__main__":
    demo_jane()
