from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Callable
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


def normalize_text(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    text = re.sub(r"[^\w\s]", " ", text.casefold().strip())
    return re.sub(r"\s+", " ", text)


def _display_date(value: object) -> str:
    if value is None or pd.isna(value):
        return "-"
    return pd.to_datetime(value).strftime("%d %b %Y")


def _display_datetime(value: object) -> str:
    if value is None or pd.isna(value):
        return "-"
    return pd.to_datetime(value).strftime("%d %b %Y %H:%M")


def _safe_text(value: object) -> str:
    if value is None or pd.isna(value):
        return "-"
    text = " ".join(str(value).split())
    return text or "-"


def prepare_quality_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy().reset_index(drop=True)
    result["row_id"] = result.index + 1
    result["analysis_text"] = "Summary: " + result["task"].fillna("").astype(str) + "\nNote: " + result["note"].fillna("").astype(str)
    result["normalized_note"] = result["note"].map(normalize_text)
    result["normalized_task"] = result["task"].map(normalize_text)
    result["work_date"] = pd.to_datetime(result["work_date"], errors="coerce")
    result["actual_start"] = pd.to_datetime(result["actual_start"], errors="coerce")
    result["actual_finish"] = pd.to_datetime(result["actual_finish"], errors="coerce")
    result["hours"] = pd.to_numeric(result["hours"], errors="coerce").fillna(0.0)
    result["calculated_hours"] = (result["actual_finish"] - result["actual_start"]).dt.total_seconds() / 3600
    result["duration_difference_hours"] = result["hours"] - result["calculated_hours"]
    return result


def find_duration_issues(dataframe: pd.DataFrame, tolerance_hours: float = 0.05) -> pd.DataFrame:
    invalid = (
        dataframe["actual_start"].isna()
        | dataframe["actual_finish"].isna()
        | (dataframe["calculated_hours"] < 0)
        | (dataframe["duration_difference_hours"].abs() > tolerance_hours)
    )
    return dataframe.loc[
        invalid,
        [
            "row_id",
            "employee",
            "task",
            "note",
            "actual_start",
            "actual_finish",
            "hours",
            "calculated_hours",
            "duration_difference_hours",
        ],
    ].copy()


def find_copy_pairs(
    dataframe: pd.DataFrame,
    threshold: float,
    progress_callback: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Find same-employee exact/near copy Note pairs with evidence for manual validation."""
    rows: list[dict[str, object]] = []
    records = dataframe[
        ["row_id", "employee", "work_date", "task", "note", "hours", "normalized_note"]
    ].to_dict("records")
    for record in records:
        record["tokens"] = set(record["normalized_note"].split())

    total = len(records) * (len(records) - 1) // 2
    checked = 0
    for index, left in enumerate(records):
        for right in records[index + 1:]:
            checked += 1
            if left["employee"] != right["employee"] or not left["normalized_note"] or not right["normalized_note"]:
                if progress_callback and (checked % 250 == 0 or checked == total):
                    progress_callback(checked, total)
                continue

            union = left["tokens"] | right["tokens"]
            exact = left["normalized_note"] == right["normalized_note"]
            if not exact and (not union or len(left["tokens"] & right["tokens"]) / len(union) < 0.45):
                if progress_callback and (checked % 250 == 0 or checked == total):
                    progress_callback(checked, total)
                continue

            score = SequenceMatcher(None, left["normalized_note"], right["normalized_note"]).ratio()
            if exact or score >= threshold:
                rows.append(
                    {
                        "Row 1": left["row_id"],
                        "Row 2": right["row_id"],
                        "Pegawai": left["employee"],
                        "Tanggal 1": _display_date(left["work_date"]),
                        "Aktivitas 1": _safe_text(left["task"]),
                        "Note 1": _safe_text(left["note"]),
                        "Jam 1": round(float(left["hours"]), 2),
                        "Tanggal 2": _display_date(right["work_date"]),
                        "Aktivitas 2": _safe_text(right["task"]),
                        "Note 2": _safe_text(right["note"]),
                        "Jam 2": round(float(right["hours"]), 2),
                        "Jenis": "Exact copy" if exact else "Near copy",
                        "Skor fuzzy": round(score, 4),
                    }
                )
            if progress_callback and (checked % 250 == 0 or checked == total):
                progress_callback(checked, total)
    return pd.DataFrame(rows)


def find_overlap_pairs(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Return overlapping time ranges with both activities shown for validation."""
    rows: list[dict[str, object]] = []
    valid = dataframe.dropna(subset=["employee", "actual_start", "actual_finish"])
    valid = valid[valid["actual_finish"] > valid["actual_start"]]
    for employee, group in valid.groupby("employee"):
        records = group.sort_values("actual_start").to_dict("records")
        for index, left in enumerate(records):
            for right in records[index + 1:]:
                if right["actual_start"] >= left["actual_finish"]:
                    break
                minutes = (
                    min(left["actual_finish"], right["actual_finish"])
                    - max(left["actual_start"], right["actual_start"])
                ).total_seconds() / 60
                if minutes > 0:
                    rows.append(
                        {
                            "Pegawai": employee,
                            "Row 1": left["row_id"],
                            "Row 2": right["row_id"],
                            "Aktivitas 1": _safe_text(left.get("task")),
                            "Mulai 1": _display_datetime(left.get("actual_start")),
                            "Selesai 1": _display_datetime(left.get("actual_finish")),
                            "Note 1": _safe_text(left.get("note")),
                            "Aktivitas 2": _safe_text(right.get("task")),
                            "Mulai 2": _display_datetime(right.get("actual_start")),
                            "Selesai 2": _display_datetime(right.get("actual_finish")),
                            "Note 2": _safe_text(right.get("note")),
                            "Overlap menit": round(minutes, 1),
                        }
                    )
    return pd.DataFrame(rows)


def embed_texts(
    texts: list[str],
    host: str,
    model: str,
    progress_callback: Callable[[int, int], None] | None = None,
    batch_size: int = 16,
) -> np.ndarray:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        request = Request(
            f"{host}/api/embed",
            data=json.dumps({"model": model, "input": texts[start:start + batch_size]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=300) as response:
            vectors.extend(json.loads(response.read().decode())["embeddings"])
        if progress_callback:
            progress_callback(min(start + batch_size, len(texts)), len(texts))
    matrix = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1, norms)


def semantic_pairs(vectors: np.ndarray, row_ids: list[int], threshold: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    similarities = vectors @ vectors.T
    for left in range(len(vectors)):
        accepted = 0
        for right in np.argsort(similarities[left])[::-1]:
            if right <= left:
                continue
            score = float(similarities[left, right])
            if score < threshold:
                break
            rows.append({"Row 1": row_ids[left], "Row 2": row_ids[right], "Skor semantik": round(score, 4)})
            accepted += 1
            if accepted == 3:
                break
    return pd.DataFrame(rows)


def enrich_semantic_pairs(pair_dataframe: pd.DataFrame, dataframe: pd.DataFrame) -> pd.DataFrame:
    """Attach the actual pair content so a semantic relation can be reviewed without row lookup."""
    columns = [
        "Pegawai 1",
        "Tanggal 1",
        "Aktivitas 1",
        "Note 1",
        "Pegawai 2",
        "Tanggal 2",
        "Aktivitas 2",
        "Note 2",
        "Skor semantik",
        "Kedekatan makna",
        "Row 1",
        "Row 2",
    ]
    if pair_dataframe.empty:
        return pd.DataFrame(columns=columns)

    lookup = dataframe.set_index("row_id", drop=False).to_dict("index")
    rows: list[dict[str, object]] = []
    for pair in pair_dataframe.to_dict("records"):
        left = lookup.get(pair["Row 1"], {})
        right = lookup.get(pair["Row 2"], {})
        score = float(pair["Skor semantik"])
        rows.append(
            {
                "Pegawai 1": _safe_text(left.get("employee")),
                "Tanggal 1": _display_date(left.get("work_date")),
                "Aktivitas 1": _safe_text(left.get("task")),
                "Note 1": _safe_text(left.get("note")),
                "Pegawai 2": _safe_text(right.get("employee")),
                "Tanggal 2": _display_date(right.get("work_date")),
                "Aktivitas 2": _safe_text(right.get("task")),
                "Note 2": _safe_text(right.get("note")),
                "Skor semantik": round(score, 4),
                "Kedekatan makna": "Sangat dekat" if score >= 0.90 else "Dekat",
                "Row 1": pair["Row 1"],
                "Row 2": pair["Row 2"],
            }
        )
    return pd.DataFrame(rows, columns=columns)


def cluster_vectors(vectors: np.ndarray, threshold: float) -> list[int]:
    centroids: list[np.ndarray] = []
    counts: list[int] = []
    labels: list[int] = []
    for vector in vectors:
        if not centroids:
            centroids.append(vector.copy())
            counts.append(1)
            labels.append(1)
            continue
        scores = np.asarray(centroids) @ vector
        best = int(np.argmax(scores))
        if float(scores[best]) >= threshold:
            count = counts[best] + 1
            centroid = (centroids[best] * counts[best] + vector) / count
            centroids[best] = centroid / max(np.linalg.norm(centroid), 1)
            counts[best] = count
            labels.append(best + 1)
        else:
            centroids.append(vector.copy())
            counts.append(1)
            labels.append(len(centroids))
    return labels


def build_topic_summary(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Summarize embedding clusters using deterministic representative task labels."""
    columns = [
        "Kelompok topik",
        "Tema representatif",
        "Jumlah entri",
        "Total jam",
        "Pegawai terkait",
        "Proyek terkait",
        "Contoh Note",
    ]
    if dataframe.empty or "Topic Group" not in dataframe.columns:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, object]] = []
    for topic_group, group in dataframe.groupby("Topic Group", sort=True):
        task_counts = group["task"].fillna("").astype(str).value_counts()
        representative_task = task_counts.index[0] if not task_counts.empty else "-"
        notes = [value for value in group["note"].fillna("").astype(str).tolist() if value.strip()]
        rows.append(
            {
                "Kelompok topik": int(topic_group),
                "Tema representatif": representative_task or "-",
                "Jumlah entri": int(len(group)),
                "Total jam": round(float(group["hours"].sum()), 2),
                "Pegawai terkait": ", ".join(sorted(group["employee"].dropna().astype(str).unique().tolist())[:8]) or "-",
                "Proyek terkait": ", ".join(sorted(group["project"].dropna().astype(str).unique().tolist())[:6]) or "-",
                "Contoh Note": _safe_text(notes[0]) if notes else "-",
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("Jumlah entri", ascending=False).reset_index(drop=True)


ACTION_WORDS = {
    "analisis",
    "buat",
    "perbaikan",
    "testing",
    "uji",
    "cek",
    "konfigurasi",
    "implementasi",
    "deploy",
    "review",
    "debug",
    "update",
    "migrasi",
    "dokumentasi",
}
OUTCOME_WORDS = {
    "selesai",
    "berhasil",
    "hasil",
    "fix",
    "fixed",
    "valid",
    "release",
    "deployed",
    "tested",
    "approved",
}


def writing_quality(dataframe: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for record in dataframe.to_dict("records"):
        words = normalize_text(record.get("note")).split()
        unique = set(words)
        score = 30 if len(words) >= 12 else 20 if len(words) >= 7 else 10 if len(words) >= 4 else 0
        score += 20 if unique & ACTION_WORDS else 0
        score += 15 if unique & OUTCOME_WORDS else 0
        score += 15 if len(unique) >= 6 else 0
        score += 10 if re.search(
            r"\d|modul|fitur|sistem|workflow|api|report|menu",
            " ".join(words + normalize_text(record.get("task")).split()),
        ) else 0
        score = max(0, min(100, score - (20 if len(words) < 3 else 0)))
        rows.append(
            {
                "row_id": record["row_id"],
                "Skor penulisan": score,
                "Kategori": "Detail" if score >= 70 else "Cukup" if score >= 45 else "Minim",
            }
        )
    return pd.DataFrame(rows)


def repeated_activities(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, set[int]]:
    rows: list[dict[str, object]] = []
    long_ids: set[int] = set()
    p75 = dataframe.groupby("employee")["hours"].quantile(0.75)
    for (employee, _key), group in dataframe[dataframe["normalized_task"].ne("")].groupby(["employee", "normalized_task"]):
        if len(group) < 2:
            continue
        median = float(group["hours"].median())
        threshold = float(p75[employee])
        long = median > 0 and median > threshold
        if long:
            long_ids.update(group["row_id"].astype(int))
        rows.append(
            {
                "Pegawai": employee,
                "Aktivitas": group["task"].iloc[0],
                "Jumlah pengulangan": len(group),
                "Total jam": round(float(group["hours"].sum()), 2),
                "Median jam": round(median, 2),
                "P75 pegawai": round(threshold, 2),
                "Cenderung lama": "Ya" if long else "Tidak",
            }
        )
    return pd.DataFrame(rows), long_ids


def managerial_summary(
    dataframe: pd.DataFrame,
    copy_pairs: pd.DataFrame,
    overlap_pairs: pd.DataFrame,
    duration_issues: pd.DataFrame,
) -> tuple[dict[str, float | int], pd.DataFrame, pd.DataFrame, list[str]]:
    row_result = dataframe[["row_id", "employee", "task", "note", "hours"]].copy()
    copy_ids = set(copy_pairs.get("Row 1", pd.Series(dtype=int))) | set(copy_pairs.get("Row 2", pd.Series(dtype=int)))
    overlap_ids = set(overlap_pairs.get("Row 1", pd.Series(dtype=int))) | set(overlap_pairs.get("Row 2", pd.Series(dtype=int)))
    duration_ids = set(duration_issues.get("row_id", pd.Series(dtype=int)))
    quality = writing_quality(dataframe)
    repeated, long_ids = repeated_activities(dataframe)
    row_result = row_result.merge(quality, on="row_id", how="left")
    row_result["Indikasi copy"] = row_result["row_id"].isin(copy_ids)
    row_result["Indikasi overlap"] = row_result["row_id"].isin(overlap_ids)
    row_result["Masalah durasi"] = row_result["row_id"].isin(duration_ids)
    row_result["Berulang dan lama"] = row_result["row_id"].isin(long_ids)

    total = max(len(row_result), 1)
    copy_rate = len(copy_ids) / total
    minimal_rate = float((row_result["Kategori"] == "Minim").mean())
    score = max(
        0,
        round(
            100
            * (
                1
                - 0.30 * copy_rate
                - 0.25 * minimal_rate
                - 0.20 * len(overlap_ids) / total
                - 0.10 * len(duration_ids) / total
                - 0.15 * len(long_ids) / total
            ),
            1,
        ),
    )
    kpis = {
        "total": len(row_result),
        "copy": len(copy_ids),
        "copy_rate": round(copy_rate * 100, 1),
        "overlap": len(overlap_ids),
        "duration": len(duration_ids),
        "minimal": int((row_result["Kategori"] == "Minim").sum()),
        "minimal_rate": round(minimal_rate * 100, 1),
        "writing": round(float(row_result["Skor penulisan"].mean()), 1),
        "effectiveness": score,
    }

    recommendations = []
    if copy_ids:
        recommendations.append(
            "Kalibrasi standar Note pada entri yang identik/hampir identik dengan format Aksi — Objek/modul — Hasil — Kendala/next step."
        )
    if overlap_ids:
        recommendations.append(
            "Lakukan sampling dan konfirmasi entri waktu overlap untuk membedakan aktivitas paralel yang wajar dari potensi double counting."
        )
    if duration_ids:
        recommendations.append(
            "Validasi entri yang durasinya tidak selaras dengan Actual Start dan Actual Finish sebelum laporan digunakan untuk analisis lanjutan."
        )
    if long_ids:
        recommendations.append(
            "Tinjau aktivitas berulang dengan durasi di atas pola normal untuk mencari dependency, bottleneck proses, atau peluang standardisasi/otomasi."
        )
    if not recommendations:
        recommendations.append(
            "Tidak ada indikator kualitas yang dominan. Pertahankan sampling review berkala dan kalibrasi ambang berdasarkan pola kerja aktual."
        )
    return kpis, row_result, repeated, recommendations
