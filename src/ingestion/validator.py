from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.ingestion.mapper import REQUIRED_FIELDS
from src.ingestion.mapper import TEMPLATE_REQUIRED_FIELDS, detect_template_columns


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_required_fields(dataframe: pd.DataFrame) -> ValidationResult:
    result = ValidationResult()
    missing = [field for field in REQUIRED_FIELDS if field not in dataframe.columns]
    if missing:
        result.errors.append(f"Missing required logical fields: {', '.join(missing)}")
    return result


def validate_template_dataframe(dataframe: pd.DataFrame) -> ValidationResult:
    result = ValidationResult()
    template_info = detect_template_columns(dataframe.columns.tolist())
    missing_required = template_info["missing_required"]
    if missing_required:
        result.errors.append(
            "Missing required Excel template columns: " + ", ".join(missing_required)
        )
    if template_info["extra_columns"]:
        result.warnings.append(
            "Additional columns detected and preserved as raw metadata: "
            + ", ".join(template_info["extra_columns"])
        )
    return result
