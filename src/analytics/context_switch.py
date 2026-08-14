from __future__ import annotations

import pandas as pd


def analyze_context_switching(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if dataframe.empty:
        empty_daily = pd.DataFrame(
            columns=["employee", "work_date", "unique_tasks", "unique_projects", "total_hours", "context_switches"]
        )
        empty_summary = pd.DataFrame(
            columns=[
                "employee",
                "active_days",
                "average_context_switches_per_active_day",
                "max_context_switches_single_day",
                "high_switch_dates",
            ]
        )
        return empty_daily, empty_summary

    prepared = dataframe.copy()
    prepared["work_date"] = pd.to_datetime(prepared["work_date"])
    prepared["hours"] = prepared["hours"].astype(float)

    daily = (
        prepared.groupby(["employee", "work_date"], as_index=False)
        .agg(
            unique_tasks=("task_key", "nunique"),
            unique_projects=("project", "nunique"),
            total_hours=("hours", "sum"),
        )
        .sort_values(["employee", "work_date"])
    )
    daily["context_switches"] = daily["unique_tasks"].apply(lambda value: max(int(value) - 1, 0))

    summary_rows: list[dict[str, object]] = []
    for employee, group in daily.groupby("employee", sort=True):
        max_switches = int(group["context_switches"].max()) if not group.empty else 0
        high_dates = group[group["context_switches"] == max_switches]["work_date"].dt.date.astype(str).tolist()
        summary_rows.append(
            {
                "employee": employee,
                "active_days": int(len(group)),
                "average_context_switches_per_active_day": float(group["context_switches"].mean()),
                "max_context_switches_single_day": max_switches,
                "high_switch_dates": high_dates,
            }
        )

    return daily.reset_index(drop=True), pd.DataFrame(summary_rows)
