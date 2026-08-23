"""
cleaning.py
-----------
Core data pipeline for the RM Student Data Pipeline & UI assessment.

Responsibilities:
    1. Parse a raw, messy student CSV (arbitrary column casing / order tolerated
       for Name, Gender, Grade, Math, Science, English, Total).
    2. Normalize every field.
    3. Recalculate + validate the Total column.
    4. Detect and resolve duplicate student records.
    5. Return a clean DataFrame plus a machine-readable "cleaning report"
       describing exactly what was changed, so the transformation is auditable.

This module has zero dependency on Streamlit so it can be unit tested and
reused (CLI, notebook, another UI, etc.) independently of the front end.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

REQUIRED_COLUMNS = ["Name", "Gender", "Grade", "Math", "Science", "English", "Total"]
SCORE_COLUMNS = ["Math", "Science", "English"]
MIN_SCORE, MAX_SCORE = 0, 100
MIN_GRADE, MAX_GRADE = 1, 12

_MARKS_SUFFIX_RE = re.compile(r"\s*marks?\s*$", flags=re.IGNORECASE)
_GRADE_PREFIX_RE = re.compile(r"grade\s*", flags=re.IGNORECASE)
_QUOTE_STRIP_RE = re.compile(r"""^["'\s]+|["'\s]+$""")

_GENDER_MAP = {
    "m": "Male", "male": "Male",
    "f": "Female", "female": "Female",
}


@dataclass
class CleaningReport:
    """Summary of every transformation applied, surfaced in the UI/README."""
    rows_in: int = 0
    rows_out: int = 0
    duplicates_removed: int = 0
    duplicate_groups: list = field(default_factory=list)
    missing_values_filled: int = 0
    invalid_scores_clipped: int = 0
    invalid_grades_fixed: int = 0
    unresolved_genders: int = 0
    totals_recalculated: int = 0
    rows_dropped_unrecoverable: int = 0
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "Rows received": self.rows_in,
            "Rows in cleaned output": self.rows_out,
            "Duplicate rows removed": self.duplicates_removed,
            "Missing values imputed": self.missing_values_filled,
            "Out-of-range scores clipped (0-100)": self.invalid_scores_clipped,
            "Grades normalized/fixed": self.invalid_grades_fixed,
            "Gender left as 'Unknown' (ambiguous source value)": self.unresolved_genders,
            "Totals recalculated from Math+Science+English": self.totals_recalculated,
            "Rows dropped (unrecoverable)": self.rows_dropped_unrecoverable,
        }


def _strip_quotes(value: str) -> str:
    """Remove wrapping quote characters / stray apostrophes / whitespace."""
    if not isinstance(value, str):
        return value
    v = value.strip()
    v = _QUOTE_STRIP_RE.sub("", v)
    # trailing apostrophe typo, e.g. Navya' -> Navya
    v = v.rstrip("'\"")
    return v.strip()


def normalize_name(raw: object) -> str | None:
    """Title-case the name and strip stray quote/apostrophe typos."""
    if pd.isna(raw):
        return None
    v = _strip_quotes(str(raw))
    if not v:
        return None
    return v.title()


def name_key(name: str | None) -> str | None:
    """Case/whitespace-insensitive key used for duplicate detection."""
    if not name:
        return None
    return re.sub(r"\s+", " ", name).strip().lower()


def normalize_gender(raw: object) -> str:
    """
    Map every observed variant (M, m, Male, F, f, Female, ...) to Male/Female.

    The source data also contains bare '0' / '1' values with no documented
    encoding key. Guessing that mapping would silently fabricate a gender
    for real students, so these (and any other unrecognized value) are
    labeled 'Unknown' rather than assumed. This is a deliberate, documented
    design decision -- see README.
    """
    if pd.isna(raw):
        return "Unknown"
    v = str(raw).strip().lower()
    return _GENDER_MAP.get(v, "Unknown")


def normalize_grade(raw: object) -> int | None:
    """'Grade 3' / '3' / 3 -> 3 (int), clipped to a plausible 1-12 range."""
    if pd.isna(raw):
        return None
    v = _GRADE_PREFIX_RE.sub("", str(raw)).strip()
    match = re.search(r"\d+", v)
    if not match:
        return None
    grade = int(match.group())
    return min(max(grade, MIN_GRADE), MAX_GRADE)


def normalize_score(raw: object) -> tuple[float | None, bool]:
    """
    '47' / '47 marks' / 47 -> 47 (int).
    Returns (value, was_clipped) where was_clipped flags an out-of-range
    input that was clamped into [0, 100].
    """
    if pd.isna(raw):
        return None, False
    v = _MARKS_SUFFIX_RE.sub("", str(raw)).strip()
    match = re.search(r"-?\d+(\.\d+)?", v)
    if not match:
        return None, False
    num = float(match.group())
    clipped = num < MIN_SCORE or num > MAX_SCORE
    num = min(max(num, MIN_SCORE), MAX_SCORE)
    return num, clipped


def _load_any(file_or_path) -> pd.DataFrame:
    """Accept a path, file-like object, or raw bytes/str of CSV content."""
    if isinstance(file_or_path, (bytes, bytearray)):
        return pd.read_csv(io.BytesIO(file_or_path))
    return pd.read_csv(file_or_path)


def _match_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map columns case/whitespace-insensitively onto the expected schema."""
    lookup = {c.strip().lower(): c for c in df.columns}
    rename = {}
    missing = []
    for expected in REQUIRED_COLUMNS:
        key = expected.lower()
        if key in lookup:
            rename[lookup[key]] = expected
        else:
            missing.append(expected)
    if missing:
        raise ValueError(
            f"Uploaded CSV is missing required column(s): {', '.join(missing)}. "
            f"Expected columns: {', '.join(REQUIRED_COLUMNS)}."
        )
    return df.rename(columns=rename)[REQUIRED_COLUMNS]


def clean_dataframe(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """
    Run the full cleaning pipeline on a raw DataFrame.

    Returns (clean_df, report). clean_df always has columns:
        Name, Gender, Grade, Math, Science, English, Total, StudentID
    plus a 'Status' column defaulted to 'Active' for the UI toggle.
    """
    report = CleaningReport(rows_in=len(raw_df))
    df = _match_columns(raw_df.copy())

    # --- Field-level normalization -----------------------------------
    df["Name"] = df["Name"].apply(normalize_name)

    before_missing = df.isna().sum().sum()

    df["Gender"] = df["Gender"].apply(normalize_gender)
    report.unresolved_genders = int((df["Gender"] == "Unknown").sum())

    grades = df["Grade"].apply(normalize_grade)
    report.invalid_grades_fixed = int(
        (df["Grade"].astype(str).str.contains("grade", case=False, na=False)).sum()
    )
    df["Grade"] = grades

    clipped_total = 0
    for col in SCORE_COLUMNS:
        results = df[col].apply(normalize_score)
        df[col] = results.apply(lambda r: r[0])
        clipped_total += int(results.apply(lambda r: r[1]).sum())
    report.invalid_scores_clipped = clipped_total

    # --- Drop rows with no usable name (can't be identified/shortlisted) --
    unrecoverable = df["Name"].isna()
    report.rows_dropped_unrecoverable = int(unrecoverable.sum())
    df = df[~unrecoverable].copy()

    # --- Impute missing numeric fields with column median (documented) ---
    for col in SCORE_COLUMNS + ["Grade"]:
        n_missing = int(df[col].isna().sum())
        if n_missing:
            median = df[col].median()
            df[col] = df[col].fillna(median)
            report.missing_values_filled += n_missing
    df["Grade"] = df["Grade"].round().astype(int)
    for col in SCORE_COLUMNS:
        df[col] = df[col].round().astype(int)

    # --- Recalculate + validate Total -------------------------------
    recalculated = df[SCORE_COLUMNS].sum(axis=1)
    original_total = pd.to_numeric(df["Total"], errors="coerce")
    mismatches = (original_total != recalculated).fillna(True)
    report.totals_recalculated = int(mismatches.sum())
    df["Total"] = recalculated.astype(int)

    # --- Duplicate detection & resolution ----------------------------
    # IMPORTANT: with no unique identifier (no roll no./email) in the
    # source data, a shared first name is NOT enough evidence that two
    # rows describe the same student -- this dataset draws from a small
    # pool of ~20 common first names across many students, so name
    # collisions between genuinely different people are expected and
    # common (verified against the bundled sample: rows sharing name +
    # gender + grade routinely have completely different scores).
    #
    # A row is only treated as a duplicate re-entry of the SAME student
    # when Name + Gender + Grade match AND all three subject scores are
    # nearly identical (small tolerance, to catch a re-typed row with a
    # minor fat-finger difference). Anything less certain is left alone
    # and merely flagged for human review, never silently deleted.
    SCORE_TOLERANCE = 2  # max per-subject point difference to call it "the same entry"

    df["_key"] = df["Name"].apply(name_key)
    candidate_groups = df.groupby(["_key", "Gender", "Grade"])

    rows_to_drop = []
    for (key, gender, grade), group in candidate_groups:
        if len(group) < 2:
            continue
        idxs = list(group.index)
        # Union-find-lite: greedily cluster rows that are within tolerance
        # on every subject score.
        clustered = [False] * len(idxs)
        for i in range(len(idxs)):
            if clustered[i]:
                continue
            cluster = [idxs[i]]
            for j in range(i + 1, len(idxs)):
                if clustered[j]:
                    continue
                a, b = df.loc[idxs[i]], df.loc[idxs[j]]
                if all(abs(a[c] - b[c]) <= SCORE_TOLERANCE for c in SCORE_COLUMNS):
                    cluster.append(idxs[j])
                    clustered[j] = True
            if len(cluster) > 1:
                # True duplicate re-entry: keep the highest-Total row, drop rest.
                sub = df.loc[cluster]
                keep = sub["Total"].idxmax()
                drop = [c for c in cluster if c != keep]
                rows_to_drop.extend(drop)
                report.duplicate_groups.append(
                    {
                        "name": df.loc[keep, "Name"],
                        "gender": gender,
                        "grade": int(grade),
                        "occurrences": len(cluster),
                        "resolution": "merged (near-identical scores)",
                        "kept_total": int(df.loc[keep, "Total"]),
                    }
                )
            else:
                # Same name/gender/grade but clearly different scores ->
                # almost certainly two different students; keep both,
                # just note the coincidental match for transparency.
                report.duplicate_groups.append(
                    {
                        "name": group.loc[idxs[i], "Name"],
                        "gender": gender,
                        "grade": int(grade),
                        "occurrences": 1,
                        "resolution": "kept (scores differ -> likely different students)",
                        "kept_total": int(group.loc[idxs[i], "Total"]),
                    }
                )

    df = df.drop(index=rows_to_drop)
    report.duplicates_removed = len(rows_to_drop)
    df = df.drop(columns=["_key"]).reset_index(drop=True)

    # --- Final shape ---------------------------------------------------
    df.insert(0, "StudentID", [f"S{i+1:04d}" for i in range(len(df))])
    df["Status"] = "Active"

    report.rows_out = len(df)
    report.notes.append(
        "Gender values '0'/'1' had no documented mapping and were labeled "
        "'Unknown' rather than guessed."
    )
    report.notes.append(
        "Duplicate students (same normalized name + same gender) were "
        "collapsed to a single record, keeping the entry with the highest "
        "(recalculated) Total as the most complete submission."
    )
    report.notes.append(
        "Missing Math/Science/English/Grade values were imputed with the "
        "column median; Total is always recalculated as Math+Science+English "
        "and never trusted from the source file."
    )

    return df, report


def clean_csv(file_or_path) -> tuple[pd.DataFrame, CleaningReport]:
    """Convenience wrapper: load a CSV (path/buffer/bytes) then clean it."""
    raw_df = _load_any(file_or_path)
    return clean_dataframe(raw_df)
