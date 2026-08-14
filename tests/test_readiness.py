from __future__ import annotations

import pandas as pd

from src.quality.readiness import build_dataset_readiness


def test_readiness_treats_note_quality_and_overlap_as_attention_not_blocker() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "employee": "Ari",
                "project": "FORCA ERP",
                "task": "Review API",
                "note": "cek",
                "work_date": "2026-08-01",
                "hours": 2.0,
                "actual_start": "2026-08-01 09:00:00",
                "actual_finish": "2026-08-01 11:00:00",
            },
            {
                "employee": "Ari",
                "project": "FORCA ERP",
                "task": "Review API lanjutan",
                "note": "cek",
                "work_date": "2026-08-01",
                "hours": 1.5,
                "actual_start": "2026-08-01 10:30:00",
                "actual_finish": "2026-08-01 12:00:00",
            },
        ]
    )

    readiness = build_dataset_readiness(dataframe)

    assert readiness.is_ready is True
    assert readiness.minimal_note_count == 2
    assert readiness.overlap_pair_count == 1
    assert readiness.timed_entry_count == 2
    assert readiness.timed_entry_coverage == 1.0


def test_readiness_blocks_missing_essential_values() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "employee": "",
                "project": "FORCA HR",
                "task": "Testing ESS",
                "note": "Testing login ESS dan validasi hasil",
                "work_date": "not-a-date",
                "hours": 1.0,
            }
        ]
    )

    readiness = build_dataset_readiness(dataframe)

    assert readiness.is_ready is False
    assert readiness.invalid_work_dates == 1
    assert readiness.missing_essential_values == 1
