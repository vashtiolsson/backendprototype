from __future__ import annotations

import json
from pathlib import Path


MAPPINGS_FILE = Path(__file__).resolve().parent / "support_type.json"


def demo_jane() -> None:
    print("=" * 64)
    print("SupportType mapping rules")
    print("=" * 64)
    print()

    data = json.loads(MAPPINGS_FILE.read_text(encoding="utf-8"))

    print(f"Concept: {data.get('concept')}")
    print(f"Ontology: {data.get('ontology_iri')}")
    print()
    print(f"Found {len(data.get('rules', []))} mapping rule(s):")
    print()

    for rule in data.get("rules", []):
        print(
            f"  {rule.get('source_file', '-'):35s} "
            f"{rule.get('source_field', '-'):30s} "
            f"→ {rule.get('target_class', 'SupportType')}.{rule.get('target_property', 'support_type')}"
        )
        print(f"      transformation={rule.get('transformation', '-')}")

        if rule.get("target_value_map"):
            print("      value mappings:")
            for source, target in rule["target_value_map"].items():
                print(f"        {source} → {target}")

        if rule.get("rationale"):
            print(f"      rationale={rule.get('rationale')}")
        print()


if __name__ == "__main__":
    demo_jane()