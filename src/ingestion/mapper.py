from __future__ import annotations

from collections import Counter

REQUIRED_FIELDS = ["employee", "date", "project", "task", "hours"]
TEMPLATE_REQUIRED_FIELDS = [
    "Assigned to",
    "Project Name",
    "Summary",
    "Actual Start",
    "Actual Duration (Hours)",
    "State",
]
TEMPLATE_ALL_FIELDS = [
    "Assigned to",
    "Project Name",
    "Summary",
    "Note",
    "Completed Date",
    "Actual Start",
    "Actual Finish",
    "Actual Duration (Hours)",
    "State",
]
TEMPLATE_FIELD_ALIASES = {
    "Assigned to": "assigned_to",
    "Project Name": "project_name",
    "Summary": "summary",
    "Note": "note",
    "Completed Date": "completed_date",
    "Actual Start": "actual_start",
    "Actual Finish": "actual_finish",
    "Actual Duration (Hours)": "actual_duration_hours",
    "State": "state",
}

AUTO_MAP_CANDIDATES = {
    "employee": {"employee", "employee name", "name", "staff", "team member"},
    "date": {"date", "work date", "day", "entry date"},
    "project": {"project", "project name", "client project", "engagement"},
    "task": {"task", "description", "task description", "work item", "activity"},
    "hours": {"hours", "duration", "time spent", "effort", "qty hours"},
}


def normalize_column_name(name: str) -> str:
    return " ".join(str(name).strip().lower().replace("_", " ").split())


def suggest_column_mapping(columns: list[str]) -> dict[str, str | None]:
    normalized_lookup = {normalize_column_name(column): column for column in columns}
    mapping: dict[str, str | None] = {}
    for logical_field in REQUIRED_FIELDS:
        match = next(
            (
                normalized_lookup[candidate]
                for candidate in AUTO_MAP_CANDIDATES[logical_field]
                if candidate in normalized_lookup
            ),
            None,
        )
        mapping[logical_field] = match
    return mapping


def validate_mapping(mapping: dict[str, str | None]) -> list[str]:
    errors: list[str] = []
    missing = [field for field in REQUIRED_FIELDS if not mapping.get(field)]
    if missing:
        errors.append(f"Missing mappings for required fields: {', '.join(missing)}")

    selected_columns = [column for column in mapping.values() if column]
    duplicates = [column for column, count in Counter(selected_columns).items() if count > 1]
    if duplicates:
        errors.append(
            "Each source column can only be mapped once. Duplicates: "
            + ", ".join(sorted(duplicates))
        )
    return errors


def detect_template_columns(columns: list[str]) -> dict[str, object]:
    normalized_lookup = {normalize_column_name(column): column for column in columns}
    matched_headers = {
        expected_header: normalized_lookup[normalize_column_name(expected_header)]
        for expected_header in TEMPLATE_ALL_FIELDS
        if normalize_column_name(expected_header) in normalized_lookup
    }
    missing_required = [
        header for header in TEMPLATE_REQUIRED_FIELDS if header not in matched_headers
    ]
    extra_columns = [
        column
        for column in columns
        if column not in matched_headers.values()
    ]
    return {
        "matched_headers": matched_headers,
        "missing_required": missing_required,
        "extra_columns": extra_columns,
        "recognized_count": len(matched_headers),
        "is_full_template": len(matched_headers) == len(TEMPLATE_ALL_FIELDS),
        "is_template_candidate": len(matched_headers) > 0,
    }


def normalize_template_headers(dataframe):
    template_info = detect_template_columns(dataframe.columns.tolist())
    rename_map = {
        template_info["matched_headers"][expected_header]: internal_name
        for expected_header, internal_name in TEMPLATE_FIELD_ALIASES.items()
        if expected_header in template_info["matched_headers"]
    }
    normalized = dataframe.rename(columns=rename_map).copy()
    normalized.attrs.update(dataframe.attrs)
    normalized.attrs["template_info"] = template_info
    return normalized, template_info
