from copy import deepcopy
from typing import Any, Dict, List, Optional

from src.config.categories import CATEGORY_TEMPLATES
from src.mappings.category_org import CATEGORY_ORG
from src.mappings.csn_mapping import CSN_MAPPING
from src.logic.transform import apply_transform


ORG_MAPPINGS = {
    "CSN": CSN_MAPPING,
}

ORG_DATA = {}

MULTI_VALUE_CONCEPTS = {"support_type"}


def register_org_data(org_name: str, data: Dict[str, Any]) -> None:
    ORG_DATA[org_name] = data


def build_template(category: str) -> Dict[str, Any]:
    if category not in CATEGORY_TEMPLATES:
        raise ValueError(f"Unknown category: {category}")
    return deepcopy(CATEGORY_TEMPLATES[category])


def is_filled(value: Any) -> bool:
    if isinstance(value, list):
        return len(value) > 0
    return value is not None


def all_concepts_filled(template: Dict[str, Any]) -> bool:
    return all(is_filled(v) for v in template.values())


def matches_where(row: Dict[str, Any], where_clause: Dict[str, Any]) -> bool:
    for key, expected_value in where_clause.items():
        if row.get(key) != expected_value:
            return False
    return True


def resolve_rule(record: Dict[str, Any], rule: Dict[str, Any]) -> Optional[Any]:
    table_name = rule["table"]
    table_data = record.get(table_name)

    if table_data is None:
        return None

    # Case 1: field is a list -> combine multiple fields from one dict-table
    if isinstance(rule["field"], list):
        if not isinstance(table_data, dict):
            return None
        values = []
        for field_name in rule["field"]:
            if field_name not in table_data:
                return None
            values.append(table_data[field_name])
        return apply_transform(values, rule["transform"])

    # Case 2: table is a list of rows
    if isinstance(table_data, list):
        where_clause = rule.get("where")
        for row in table_data:
            if where_clause and not matches_where(row, where_clause):
                continue
            field_name = rule["field"]
            if field_name in row and row[field_name] not in [None, ""]:
                return apply_transform(row[field_name], rule["transform"])
        return None

    # Case 3: table is a dict
    if isinstance(table_data, dict):
        field_name = rule["field"]
        if field_name in table_data and table_data[field_name] not in [None, ""]:
            return apply_transform(table_data[field_name], rule["transform"])

    return None


def fill_from_org(
    org_name: str,
    template: Dict[str, Any],
) -> Dict[str, Any]:
    mapping = ORG_MAPPINGS.get(org_name, {})
    record = ORG_DATA.get(org_name, {})

    for concept, current_value in template.items():
        rules: List[Dict[str, Any]] = sorted(
            mapping.get(concept, []),
            key=lambda r: (r["table"], r.get("priority", 999)),
        )

        print("CONCEPT:", concept)
        print("RULES:", rules)
        print("RECORD KEYS:", list(record.keys()))

        # MULTI-VALUE concepts: one best value per table
        if concept in MULTI_VALUE_CONCEPTS:
            collected = []
            seen_tables = set()

            for rule in rules:
                table_name = rule["table"]

                # Skip table if we already found its best value
                if table_name in seen_tables:
                    continue

                resolved = resolve_rule(record, rule)
                print(" TRY RULE:", rule)
                print(" RESOLVED:", resolved)

                if resolved is None:
                    continue

                if isinstance(resolved, list):
                    for item in resolved:
                        if item not in collected:
                            collected.append(item)
                else:
                    if resolved not in collected:
                        collected.append(resolved)

                # Mark this table as done once first valid value is found
                seen_tables.add(table_name)

            if collected:
                template[concept] = ", ".join(collected)

            continue

        # SINGLE-VALUE concepts
        if is_filled(current_value):
            print(" SKIP, already filled:", current_value)
            continue

        for rule in rules:
            resolved = resolve_rule(record, rule)
            print(" TRY RULE:", rule)
            print(" RESOLVED:", resolved)

            if resolved is not None:
                template[concept] = resolved
                print(" SET:", concept, "=", resolved)
                break

    return template


def run_pipeline(category: str) -> Dict[str, Any]:
    template = build_template(category)
    orgs = CATEGORY_ORG.get(category, [])

    for org_name in orgs:
        template = fill_from_org(org_name, template)

        if all_concepts_filled(template):
            break

    return template