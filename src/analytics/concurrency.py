from __future__ import annotations

import pandas as pd


def analyze_concurrency(dataframe: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if dataframe.empty:
        return {
            "employee_date": pd.DataFrame(columns=["employee", "work_date", "parallel_tasks"]),
            "project_date": pd.DataFrame(columns=["project", "work_date", "active_tasks", "active_employees"]),
            "date_overall": pd.DataFrame(columns=["work_date", "active_tasks", "active_projects", "active_employees"]),
        }

    prepared = dataframe.copy()
    prepared["work_date"] = pd.to_datetime(prepared["work_date"])

    employee_date = (
        prepared.groupby(["employee", "work_date"], as_index=False)
        .agg(parallel_tasks=("task_key", "nunique"))
        .sort_values(["employee", "work_date"])
    )
    project_date = (
        prepared.groupby(["project", "work_date"], as_index=False)
        .agg(active_tasks=("task_key", "nunique"), active_employees=("employee", "nunique"))
        .sort_values(["project", "work_date"])
    )
    date_overall = (
        prepared.groupby("work_date", as_index=False)
        .agg(
            active_tasks=("task_key", "nunique"),
            active_projects=("project", "nunique"),
            active_employees=("employee", "nunique"),
        )
        .sort_values("work_date")
    )
    return {
        "employee_date": employee_date.reset_index(drop=True),
        "project_date": project_date.reset_index(drop=True),
        "date_overall": date_overall.reset_index(drop=True),
    }
