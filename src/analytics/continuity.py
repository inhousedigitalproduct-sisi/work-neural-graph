from __future__ import annotations

import pandas as pd

from src.analytics.fragmentation import analyze_fragmentation


def analyze_continuity(dataframe: pd.DataFrame) -> pd.DataFrame:
    fragmentation = analyze_fragmentation(dataframe)
    if fragmentation.empty:
        return pd.DataFrame(
            columns=[
                "task_key",
                "task",
                "project",
                "first_work_date",
                "last_work_date",
                "active_days",
                "calendar_span_days",
                "average_date_gap_days",
                "max_date_gap_days",
                "total_interruption_days",
                "continuous_work_ratio",
            ]
        )

    return fragmentation[
        [
            "task_key",
            "task",
            "project",
            "first_work_date",
            "last_work_date",
            "active_days",
            "calendar_span_days",
            "average_date_gap_days",
            "max_date_gap_days",
            "total_interruption_days",
            "continuous_work_ratio",
        ]
    ].copy()
