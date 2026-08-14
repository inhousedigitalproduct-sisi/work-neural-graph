from __future__ import annotations

import pandas as pd


def calculate_fragmentation_score(continuation_count: int, total_interruption_days: int) -> int:
    return int(continuation_count) + int(total_interruption_days)


def classify_fragmentation(score: int) -> str:
    if score == 0:
        return "Continuous / Single-day"
    if score <= 2:
        return "Low fragmentation"
    if score <= 5:
        return "Moderate fragmentation"
    return "High fragmentation"


def analyze_fragmentation(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(
            columns=[
                "task_key",
                "task",
                "project",
                "employees",
                "total_hours",
                "first_work_date",
                "last_work_date",
                "active_days",
                "calendar_span_days",
                "continuation_count",
                "interruption_count",
                "average_date_gap_days",
                "max_date_gap_days",
                "total_interruption_days",
                "fragmentation_score",
                "fragmentation_band",
                "continuous_work_ratio",
            ]
        )

    prepared = dataframe.copy()
    prepared["work_date"] = pd.to_datetime(prepared["work_date"])
    prepared["hours"] = prepared["hours"].astype(float)

    task_date_rollup = (
        prepared.groupby(["task_key", "work_date"], as_index=False)
        .agg(
            task=("task", "first"),
            project=("project", "first"),
            employees=("employee", lambda values: sorted(set(values))),
            hours=("hours", "sum"),
        )
        .sort_values(["task_key", "work_date"])
    )

    rows: list[dict[str, object]] = []
    for task_key, group in task_date_rollup.groupby("task_key", sort=False):
        dates = group["work_date"].tolist()
        gaps = [int((dates[index + 1] - dates[index]).days) for index in range(len(dates) - 1)]
        interruption_days = [max(gap - 1, 0) for gap in gaps]
        active_days = len(dates)
        calendar_span_days = int((dates[-1] - dates[0]).days) + 1 if dates else 0
        continuation_count = max(active_days - 1, 0)
        interruption_count = sum(1 for gap in gaps if gap > 1)
        total_interruption_days = sum(interruption_days)
        score = calculate_fragmentation_score(continuation_count, total_interruption_days)
        continuity_ratio = (active_days / calendar_span_days) if calendar_span_days else 0.0

        rows.append(
            {
                "task_key": task_key,
                "task": group["task"].iloc[0],
                "project": group["project"].iloc[0],
                "employees": sorted({employee for values in group["employees"] for employee in values}),
                "total_hours": float(group["hours"].sum()),
                "first_work_date": dates[0].date().isoformat(),
                "last_work_date": dates[-1].date().isoformat(),
                "active_days": active_days,
                "calendar_span_days": calendar_span_days,
                "continuation_count": continuation_count,
                "interruption_count": interruption_count,
                "average_date_gap_days": float(sum(gaps) / len(gaps)) if gaps else 0.0,
                "max_date_gap_days": max(gaps) if gaps else 0,
                "total_interruption_days": total_interruption_days,
                "fragmentation_score": score,
                "fragmentation_band": classify_fragmentation(score),
                "continuous_work_ratio": float(continuity_ratio),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["fragmentation_score", "total_interruption_days", "active_days", "task"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
