from __future__ import annotations

import json
from pathlib import Path


MAPPINGS_FILE = Path(__file__).resolve().parent / "occupation.json"


def demo_jane() -> None:
    print("=" * 64)
    print("Occupation mapping rules")
    print("=" * 64)
    print()

    data = json.loads(MAPPINGS_FILE.read_text(encoding="utf-8"))

    print(f"Concept: {data['concept']}")
    print(f"Ontology: {data['ontology_iri']}")
    print()

    print(f"Found {len(data['rules'])} mapping rule(s):")
    print()

    for rule in data["rules"]:
        print(
            f"  {rule['source_file']:35s} "
            f"{rule['source_field']:30s} "
            f"→ {rule['target_class']}.{rule['target_property']}"
        )
        print(f"      scope_field={rule.get('scope_field', '-')}")
        print(f"      target_value={rule.get('target_value', '-')}")
        print(f"      transformation={rule['transformation']}")
        print(f"      rationale={rule['rationale']}")
        print()


if __name__ == "__main__":
    demo_jane()
