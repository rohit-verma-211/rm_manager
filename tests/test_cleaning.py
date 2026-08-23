import pandas as pd
import pytest

from src.cleaning import (
    clean_dataframe,
    name_key,
    normalize_gender,
    normalize_grade,
    normalize_name,
    normalize_score,
)


def test_normalize_name_strips_quotes_and_apostrophes():
    assert normalize_name('"Aarav"') == "Aarav"
    assert normalize_name("Navya'") == "Navya"
    assert normalize_name("  rohan  ") == "Rohan"


def test_name_key_case_insensitive():
    assert name_key("Rohan") == name_key("ROHAN") == name_key("rohan ")


@pytest.mark.parametrize(
    "raw,expected",
    [("M", "Male"), ("male", "Male"), ("F", "Female"), ("Female", "Female")],
)
def test_normalize_gender_known_values(raw, expected):
    assert normalize_gender(raw) == expected


def test_normalize_gender_unknown_is_not_guessed():
    assert normalize_gender("0") == "Unknown"
    assert normalize_gender("1") == "Unknown"


def test_normalize_grade_handles_prefix_and_range():
    assert normalize_grade("Grade 3") == 3
    assert normalize_grade("7") == 7
    assert normalize_grade(15) == 12  # clipped to max


def test_normalize_score_strips_marks_suffix():
    value, clipped = normalize_score("47 marks")
    assert value == 47
    assert clipped is False


def test_normalize_score_clips_out_of_range():
    value, clipped = normalize_score("150")
    assert value == 100
    assert clipped is True


def test_clean_dataframe_recalculates_total():
    raw = pd.DataFrame(
        [{"Name": "Test", "Gender": "M", "Grade": "5", "Math": "10 marks",
          "Science": "20", "English": "30", "Total": 999}]
    )
    clean, report = clean_dataframe(raw)
    assert clean.loc[0, "Total"] == 60
    assert report.totals_recalculated == 1


def test_clean_dataframe_merges_near_identical_reentry():
    # Same name/gender/grade AND near-identical scores -> true duplicate re-entry.
    raw = pd.DataFrame(
        [
            {"Name": "Myra", "Gender": "Male", "Grade": "7", "Math": 74, "Science": 12, "English": 72, "Total": 158},
            {"Name": "MYRA", "Gender": "male", "Grade": "7", "Math": 75, "Science": 13, "English": 73, "Total": 161},
        ]
    )
    clean, report = clean_dataframe(raw)
    assert len(clean) == 1
    assert clean.loc[0, "Total"] == 161  # kept the higher-total (more complete) record
    assert report.duplicates_removed == 1


def test_clean_dataframe_keeps_same_name_different_scores():
    # Same name/gender/grade but very different scores -> two different
    # students who happen to share a name; must NOT be collapsed.
    raw = pd.DataFrame(
        [
            {"Name": "Myra", "Gender": "Male", "Grade": "7", "Math": 74, "Science": 12, "English": 72, "Total": 158},
            {"Name": "MYRA", "Gender": "male", "Grade": "7", "Math": 10, "Science": 90, "English": 5, "Total": 105},
        ]
    )
    clean, report = clean_dataframe(raw)
    assert len(clean) == 2
    assert report.duplicates_removed == 0


def test_clean_dataframe_adds_status_column_defaulting_active():
    raw = pd.DataFrame(
        [{"Name": "A", "Gender": "F", "Grade": "1", "Math": 1, "Science": 1, "English": 1, "Total": 3}]
    )
    clean, _ = clean_dataframe(raw)
    assert (clean["Status"] == "Active").all()
