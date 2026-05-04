from copy import deepcopy
from typing import Any, Dict, List, Optional

from src.config.categories import CATEGORY_TEMPLATES, MULTI_VALUE_CONCEPTS
from src.mappings.category_org import CATEGORY_ORG
from src.mappings.csn_mapping import CSN_MAPPING
from src.logic.transform import apply_transform


ORG_MAPPINGS = {
    "CSN": CSN_MAPPING,
}

ORG_DATA: Dict[str, Any] = {}


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
    return all(row.get(k) == v for k, v in where_clause.items())


def resolve_rule(record: Dict[str, Any], rule: Dict[str, Any]) -> Optional[Any]:
    table_name = rule["table"]
    table_data = record.get(table_name)

    if table_data is None:
        return None

    # Case 1: field is a list — combine multiple fields from one dict-table
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
            if row.get(field_name) not in (None, ""):
                return apply_transform(row[field_name], rule["transform"])
        return None

    # Case 3: table is a dict
    if isinstance(table_data, dict):
        field_name = rule["field"]
        if table_data.get(field_name) not in (None, ""):
            return apply_transform(table_data[field_name], rule["transform"])

    return None


def fill_from_org(org_name: str, template: Dict[str, Any]) -> Dict[str, Any]:
    mapping = ORG_MAPPINGS.get(org_name, {})
    record = ORG_DATA.get(org_name, {})

    for concept, current_value in template.items():
        rules: List[Dict[str, Any]] = sorted(
            mapping.get(concept, []),
            key=lambda r: r.get("priority", 999),
        )

        # Multi-value concepts: collect one best value per table
        if concept in MULTI_VALUE_CONCEPTS:
            collected: List[str] = []
            seen_tables: set = set()

            for rule in rules:
                table_name = rule["table"]
                if table_name in seen_tables:
                    continue

                resolved = resolve_rule(record, rule)
                if resolved is None:
                    continue

                items = resolved if isinstance(resolved, list) else [resolved]
                for item in items:
                    if item not in collected:
                        collected.append(item)

                seen_tables.add(table_name)

            if collected:
                template[concept] = ", ".join(str(i) for i in collected)

            continue

        # Single-value concepts
        if is_filled(current_value):
            continue

        for rule in rules:
            resolved = resolve_rule(record, rule)
            if resolved is not None:
                template[concept] = resolved
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
