from __future__ import annotations

import numpy as np
import pandas as pd

from src.quality.timesheet_quality import (
    enrich_semantic_pairs,
    find_copy_pairs,
    find_overlap_pairs,
    prepare_quality_dataframe,
)


def build_quality_dataframe() -> pd.DataFrame:
    return prepare_quality_dataframe(
        pd.DataFrame(
            [
                {
                    "employee": "Ari",
                    "work_date": "2026-08-01",
                    "project": "FORCA ERP",
                    "task": "Review API",
                    "note": "Review API dan validasi hasil",
                    "hours": 2.0,
                    "actual_start": "2026-08-01 09:00:00",
                    "actual_finish": "2026-08-01 11:00:00",
                },
                {
                    "employee": "Ari",
                    "work_date": "2026-08-02",
                    "project": "FORCA ERP",
                    "task": "Review API lanjutan",
                    "note": "Review API dan validasi hasil",
                    "hours": 1.5,
                    "actual_start": "2026-08-01 10:30:00",
                    "actual_finish": "2026-08-01 12:00:00",
                },
            ]
        )
    )


def test_copy_pairs_include_both_activity_details() -> None:
    pairs = find_copy_pairs(build_quality_dataframe(), threshold=0.9)
    assert pairs.iloc[0]["Aktivitas 1"] == "Review API"
    assert pairs.iloc[0]["Aktivitas 2"] == "Review API lanjutan"
    assert pairs.iloc[0]["Note 1"] == "Review API dan validasi hasil"
    assert pairs.iloc[0]["Tanggal 2"] == "02 Aug 2026"


def test_overlap_pairs_include_time_and_note_evidence() -> None:
    overlaps = find_overlap_pairs(build_quality_dataframe())
    assert overlaps.iloc[0]["Overlap menit"] == 30.0
    assert overlaps.iloc[0]["Aktivitas 1"] == "Review API"
    assert overlaps.iloc[0]["Mulai 2"].endswith("10:30")


def test_semantic_pairs_are_enriched_with_readable_content() -> None:
    dataframe = build_quality_dataframe()
    pairs = pd.DataFrame([{"Row 1": 1, "Row 2": 2, "Skor semantik": 0.93}])
    enriched = enrich_semantic_pairs(pairs, dataframe)
    assert enriched.iloc[0]["Kedekatan makna"] == "Sangat dekat"
    assert enriched.iloc[0]["Aktivitas 1"] == "Review API"
    assert enriched.iloc[0]["Aktivitas 2"] == "Review API lanjutan"
