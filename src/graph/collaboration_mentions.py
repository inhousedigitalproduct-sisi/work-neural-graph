from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata

import pandas as pd


DEFAULT_ALIAS_PATH = Path("config/employee_aliases.json")
DEFAULT_MIN_CONFIDENCE = 0.90

EVIDENCE_COLUMNS = [
    "source_employee",
    "target_employee",
    "entry_id",
    "work_date",
    "task_key",
    "project",
    "matched_alias",
    "confidence",
    "context",
    "note_hash",
]
DIRECTION_COLUMNS = [
    "source_employee",
    "target_employee",
    "acknowledgement_entry_count",
    "unique_task_count",
    "unique_project_count",
    "first_date",
    "last_date",
    "evidence_entry_ids",
]
INSIGHT_COLUMNS = [
    "employee_a",
    "employee_b",
    "shared_task_count",
    "a_to_b_count",
    "b_to_a_count",
    "acknowledgement_reciprocity",
    "evidence_type",
]


@dataclass(frozen=True)
class CollaborationMentionResult:
    evidence_dataframe: pd.DataFrame
    directional_dataframe: pd.DataFrame


def normalize_person_text(value: object) -> str:
    """Normalize employee names/notes for deterministic word-boundary matching."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def load_employee_aliases(path: str | Path = DEFAULT_ALIAS_PATH) -> dict[str, tuple[str, ...]]:
    """Load optional canonical-name -> aliases mapping; missing file means no manual aliases."""
    alias_path = Path(path)
    if not alias_path.exists():
        return {}
    payload = json.loads(alias_path.read_text(encoding="utf-8") or "{}")
    if not isinstance(payload, dict):
        raise ValueError("employee alias config must be a JSON object")

    aliases: dict[str, tuple[str, ...]] = {}
    for employee, values in payload.items():
        canonical = str(employee).strip()
        if not canonical:
            continue
        if isinstance(values, str):
            raw_values = [values]
        elif isinstance(values, list):
            raw_values = values
        else:
            raise ValueError(f"aliases for {canonical!r} must be a string or list")
        cleaned = tuple(dict.fromkeys(str(value).strip() for value in raw_values if str(value).strip()))
        aliases[canonical] = cleaned
    return aliases


def _employee_candidates(
    employee: str,
    manual_aliases: Mapping[str, Sequence[str]],
) -> dict[str, float]:
    normalized = normalize_person_text(employee)
    tokens = normalized.split()
    candidates: dict[str, float] = {}
    if normalized:
        candidates[normalized] = 1.0

    if len(tokens) >= 2:
        for index in range(len(tokens) - 1):
            pair = " ".join(tokens[index : index + 2])
            candidates[pair] = max(candidates.get(pair, 0.0), 0.95)
        first_last = f"{tokens[0]} {tokens[-1]}"
        candidates[first_last] = max(candidates.get(first_last, 0.0), 0.95)

    for token in tokens:
        if len(token) >= 3 and not token.isdigit():
            # Short canonical names are common (Ari, Eko, Adi, Ayu). A single token
            # is still accepted only after _build_alias_index proves it is unique.
            candidates[token] = max(candidates.get(token, 0.0), 0.92)

    for alias in manual_aliases.get(employee, ()):  # Manual aliases may safely be single-token nicknames.
        normalized_alias = normalize_person_text(alias)
        if normalized_alias:
            candidates[normalized_alias] = max(candidates.get(normalized_alias, 0.0), 0.98)
    return candidates


def _build_alias_index(
    employees: Sequence[str],
    manual_aliases: Mapping[str, Sequence[str]],
    *,
    min_confidence: float,
) -> dict[str, list[tuple[tuple[str, ...], str, str, float]]]:
    alias_owners: dict[str, dict[str, float]] = defaultdict(dict)
    for raw_employee in employees:
        employee = str(raw_employee).strip()
        if not employee:
            continue
        for alias, confidence in _employee_candidates(employee, manual_aliases).items():
            alias_owners[alias][employee] = max(alias_owners[alias].get(employee, 0.0), confidence)

    by_first_token: dict[str, list[tuple[tuple[str, ...], str, str, float]]] = defaultdict(list)
    for alias, owners in alias_owners.items():
        if len(owners) != 1:
            continue
        employee, confidence = next(iter(owners.items()))
        if confidence < min_confidence:
            continue
        alias_tokens = tuple(alias.split())
        if not alias_tokens:
            continue
        by_first_token[alias_tokens[0]].append((alias_tokens, alias, employee, confidence))

    for first_token, values in by_first_token.items():
        values.sort(key=lambda item: (-len(item[0]), -item[3], item[1], item[2]))
        by_first_token[first_token] = values
    return dict(by_first_token)


def _safe_text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _date_text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return _safe_text(value)
    return parsed.date().isoformat()


def extract_collaboration_mentions(
    dataframe: pd.DataFrame,
    *,
    employee_roster: Sequence[str] | None = None,
    aliases: Mapping[str, Sequence[str]] | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    note_column: str = "note",
) -> CollaborationMentionResult:
    """Extract directional collaboration acknowledgements from timesheet notes."""
    if dataframe.empty or "employee" not in dataframe.columns or note_column not in dataframe.columns:
        return CollaborationMentionResult(
            pd.DataFrame(columns=EVIDENCE_COLUMNS),
            pd.DataFrame(columns=DIRECTION_COLUMNS),
        )

    roster_source = employee_roster if employee_roster is not None else dataframe["employee"].tolist()
    roster = tuple(dict.fromkeys(str(value).strip() for value in roster_source if str(value).strip()))
    manual_aliases = aliases or {}
    alias_index = _build_alias_index(roster, manual_aliases, min_confidence=min_confidence)
    if not alias_index:
        return CollaborationMentionResult(
            pd.DataFrame(columns=EVIDENCE_COLUMNS),
            pd.DataFrame(columns=DIRECTION_COLUMNS),
        )

    evidence_rows: list[dict[str, object]] = []
    for index, row in dataframe.iterrows():
        source = str(row.get("employee", "")).strip()
        raw_note = _safe_text(row.get(note_column))
        if not source or not raw_note:
            continue

        normalized_note = normalize_person_text(raw_note)
        tokens = normalized_note.split()
        if not tokens:
            continue

        best_match_by_target: dict[str, tuple[str, float]] = {}
        for position, token in enumerate(tokens):
            for alias_tokens, alias, target, confidence in alias_index.get(token, ()):
                if target == source:
                    continue
                width = len(alias_tokens)
                if tuple(tokens[position : position + width]) != alias_tokens:
                    continue
                existing = best_match_by_target.get(target)
                if existing is None or (confidence, len(alias)) > (existing[1], len(existing[0])):
                    best_match_by_target[target] = (alias, confidence)

        if not best_match_by_target:
            continue

        raw_entry_id = row.get("entry_id") if "entry_id" in dataframe.columns else None
        entry_id = _safe_text(raw_entry_id) or str(index)
        note_hash = sha256(normalized_note.encode("utf-8")).hexdigest()[:16]
        context = raw_note if len(raw_note) <= 240 else raw_note[:237].rstrip() + "..."

        for target, (matched_alias, confidence) in sorted(best_match_by_target.items()):
            evidence_rows.append(
                {
                    "source_employee": source,
                    "target_employee": target,
                    "entry_id": entry_id,
                    "work_date": _date_text(row.get("work_date")),
                    "task_key": _safe_text(row.get("task_key")),
                    "project": _safe_text(row.get("project")),
                    "matched_alias": matched_alias,
                    "confidence": round(float(confidence), 2),
                    "context": context,
                    "note_hash": note_hash,
                }
            )

    if not evidence_rows:
        return CollaborationMentionResult(
            pd.DataFrame(columns=EVIDENCE_COLUMNS),
            pd.DataFrame(columns=DIRECTION_COLUMNS),
        )

    evidence = pd.DataFrame(evidence_rows, columns=EVIDENCE_COLUMNS).drop_duplicates(
        subset=["source_employee", "target_employee", "entry_id"]
    )
    evidence = evidence.sort_values(
        ["source_employee", "target_employee", "work_date", "entry_id"],
        na_position="last",
    ).reset_index(drop=True)

    directional_rows: list[dict[str, object]] = []
    for (source, target), group in evidence.groupby(["source_employee", "target_employee"], sort=True):
        task_keys = sorted({value for value in group["task_key"].dropna().astype(str) if value})
        projects = sorted({value for value in group["project"].dropna().astype(str) if value})
        dates = sorted({value for value in group["work_date"].dropna().astype(str) if value})
        entry_ids = sorted({value for value in group["entry_id"].dropna().astype(str) if value})
        directional_rows.append(
            {
                "source_employee": source,
                "target_employee": target,
                "acknowledgement_entry_count": int(len(entry_ids)),
                "unique_task_count": int(len(task_keys)),
                "unique_project_count": int(len(projects)),
                "first_date": dates[0] if dates else None,
                "last_date": dates[-1] if dates else None,
                "evidence_entry_ids": entry_ids,
            }
        )

    directional = pd.DataFrame(directional_rows, columns=DIRECTION_COLUMNS).sort_values(
        ["acknowledgement_entry_count", "source_employee", "target_employee"],
        ascending=[False, True, True],
    ).reset_index(drop=True)
    return CollaborationMentionResult(evidence, directional)


def build_mention_diagnostics(
    dataframe: pd.DataFrame,
    result: CollaborationMentionResult,
    visible_signals: Sequence[Mapping[str, object]] | None = None,
    *,
    note_column: str = "note",
) -> dict[str, int]:
    """Return compact, explainable counters for troubleshooting missing directional dots."""
    notes_scanned = 0
    if not dataframe.empty and note_column in dataframe.columns:
        notes_scanned = int(dataframe[note_column].map(_safe_text).notna().sum())

    accepted_note_count = 0
    if not result.evidence_dataframe.empty and "entry_id" in result.evidence_dataframe.columns:
        accepted_note_count = int(result.evidence_dataframe["entry_id"].astype(str).nunique())

    accepted_evidence = int(len(result.evidence_dataframe))
    directional_pairs = int(len(result.directional_dataframe))
    visible_signal_count = int(len(list(visible_signals or ())))

    return {
        "notes_scanned": notes_scanned,
        "notes_with_accepted_evidence": accepted_note_count,
        "notes_without_accepted_evidence": max(0, notes_scanned - accepted_note_count),
        "accepted_evidence": accepted_evidence,
        "directional_pairs": directional_pairs,
        "visible_signals": visible_signal_count,
    }


def build_acknowledgement_insights(
    shared_edges: pd.DataFrame,
    directional: pd.DataFrame,
) -> pd.DataFrame:
    """Combine shared-task evidence with directional note acknowledgement evidence."""
    pair_rows: dict[tuple[str, str], dict[str, object]] = {}

    if not shared_edges.empty:
        for row in shared_edges.to_dict(orient="records"):
            source = str(row.get("source", "")).strip()
            target = str(row.get("target", "")).strip()
            if not source or not target or source == target:
                continue
            employee_a, employee_b = sorted((source, target))
            pair_rows[(employee_a, employee_b)] = {
                "employee_a": employee_a,
                "employee_b": employee_b,
                "shared_task_count": int(row.get("shared_task_count", 0) or 0),
                "a_to_b_count": 0,
                "b_to_a_count": 0,
            }

    if not directional.empty:
        for row in directional.to_dict(orient="records"):
            source = str(row.get("source_employee", "")).strip()
            target = str(row.get("target_employee", "")).strip()
            if not source or not target or source == target:
                continue
            employee_a, employee_b = sorted((source, target))
            pair = pair_rows.setdefault(
                (employee_a, employee_b),
                {
                    "employee_a": employee_a,
                    "employee_b": employee_b,
                    "shared_task_count": 0,
                    "a_to_b_count": 0,
                    "b_to_a_count": 0,
                },
            )
            count = int(row.get("acknowledgement_entry_count", 0) or 0)
            if source == employee_a:
                pair["a_to_b_count"] = int(pair["a_to_b_count"]) + count
            else:
                pair["b_to_a_count"] = int(pair["b_to_a_count"]) + count

    insights: list[dict[str, object]] = []
    for pair in pair_rows.values():
        shared = int(pair["shared_task_count"])
        a_to_b = int(pair["a_to_b_count"])
        b_to_a = int(pair["b_to_a_count"])
        acknowledgement_total = a_to_b + b_to_a
        reciprocity = (2 * min(a_to_b, b_to_a) / acknowledgement_total) if acknowledgement_total else 0.0
        if shared > 0 and a_to_b > 0 and b_to_a > 0:
            evidence_type = "SHARED_MUTUAL"
        elif shared > 0 and acknowledgement_total > 0:
            evidence_type = "SHARED_ONE_SIDED"
        elif shared > 0:
            evidence_type = "SHARED_SILENT"
        else:
            evidence_type = "MENTION_ONLY"
        insights.append(
            {
                **pair,
                "acknowledgement_reciprocity": round(float(reciprocity), 4),
                "evidence_type": evidence_type,
            }
        )

    if not insights:
        return pd.DataFrame(columns=INSIGHT_COLUMNS)
    return pd.DataFrame(insights, columns=INSIGHT_COLUMNS).sort_values(
        ["shared_task_count", "a_to_b_count", "b_to_a_count", "employee_a", "employee_b"],
        ascending=[False, False, False, True, True],
    ).reset_index(drop=True)


def build_visible_directional_signals(
    directional: pd.DataFrame,
    visible_edges: pd.DataFrame,
) -> list[dict[str, object]]:
    """Return note-derived one-way signals only for currently visible shared-task edges."""
    if directional.empty or visible_edges.empty:
        return []
    visible_pairs = {
        tuple(sorted((str(row["source"]), str(row["target"]))))
        for row in visible_edges.to_dict(orient="records")
        if row.get("source") and row.get("target")
    }
    signals = [
        {
            "source": str(row["source_employee"]),
            "target": str(row["target_employee"]),
            "count": int(row["acknowledgement_entry_count"]),
        }
        for row in directional.to_dict(orient="records")
        if tuple(sorted((str(row["source_employee"]), str(row["target_employee"])))) in visible_pairs
        and int(row.get("acknowledgement_entry_count", 0) or 0) > 0
    ]
    signals.sort(key=lambda row: (-int(row["count"]), str(row["source"]), str(row["target"])))
    return signals
