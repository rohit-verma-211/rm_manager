# RM Student Data Pipeline & UI

A data-cleaning pipeline + Streamlit UI built for the DTU **Career Development and
Industry Engagement (CDIE) Office** Recruitment Manager (RM) Portal technical
assessment.

**Live demo:** _add your deployed Streamlit Cloud URL here_
**Video walkthrough (≤90s):** _add your video link here (Loom / YouTube unlisted / Drive)_

---

## 1. What it does

1. **Upload** a raw student CSV (or use the bundled sample dataset).
2. **Auto-clean** it: fixes typos/quoting in names, normalizes gender and grade
   values, strips `" marks"` suffixes from scores, clips out-of-range scores,
   imputes missing numeric values, and **recalculates `Total`** from
   `Math + Science + English` rather than trusting the source column.
3. **Detects duplicates** conservatively (see [§4](#4-duplicate-detection-logic)
   for why this needed real thought, not a one-liner).
4. Displays the cleaned roster in an editable table with a live
   **Active / Debarred** status toggle per student — debarred students are
   removed from the shortlist immediately, no page reload.
5. A **minimum Total Score slider** produces a live shortlist with summary
   stats (count, avg/min/max Total).
6. The current shortlist can be **exported as CSV** with one click.

---

## 2. Setup & run locally

**Requirements:** Python 3.10+

```bash
git clone <this-repo-url>
cd rm-student-pipeline
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

streamlit run app.py
```

The app opens at `http://localhost:8501`. Click **"Use bundled sample dataset"**
in the sidebar to try it instantly, or upload your own CSV with columns:

```
Name, Gender, Grade, Math, Science, English, Total
```

(Column names are matched case/whitespace-insensitively; column order doesn't matter.)

### Run tests

```bash
pytest tests/ -v
```

14 unit tests cover name/gender/grade/score normalization, Total recalculation,
and both duplicate-handling branches (true re-entry vs. coincidental name match).

---

## 3. Architecture

```
rm-student-pipeline/
├── app.py                  # Streamlit UI (upload, editor, filter, export)
├── src/
│   └── cleaning.py         # Pure-pandas cleaning pipeline (no Streamlit dependency)
├── tests/
│   └── test_cleaning.py    # pytest unit tests
├── data/
│   └── sample_students_raw.csv   # bundled sample/demo dataset
├── requirements.txt
└── .streamlit/config.toml  # theming
```

The cleaning logic lives entirely in `src/cleaning.py`, independent of
Streamlit, so it's unit-testable and reusable (CLI script, another UI, a
scheduled batch job, etc.) without pulling in the whole app.

**Performance:** the pipeline is pure vectorized pandas (no row-wise Python
loops except within the small duplicate-clustering step, which only runs on
rows that already collide on name+gender+grade — a tiny subset). Cleaning
99 rows completes in well under 50ms; the in-app report shows the actual
measured run time for whatever file you upload.

---

## 4. Data-cleaning logic

### Name
- Strips wrapping quotes (`"Aarav"` → `Aarav`) and stray trailing apostrophes
  (`Navya'` → `Navya`), then title-cases for consistent display
  (`ROHAN` / `rohan` → `Rohan`).

### Gender
- Case-insensitive mapping: `M`/`Male`/`m`/`male` → `Male`,
  `F`/`Female`/`f`/`female` → `Female`.
- The source data also contains bare `0` / `1` values with **no documented
  encoding**. Guessing `0 = Male` (or the reverse) would silently fabricate a
  gender for a real student with no evidence. These are labeled **`Unknown`**
  instead — a deliberate, conservative choice over a plausible-looking but
  unverifiable guess.

### Grade
- Handles both `"Grade 3"` and plain `3`, extracts the digits, and clamps to
  a sane `1–12` range.

### Math / Science / English
- Strips a trailing `" marks"` suffix (`"47 marks"` → `47`) and parses to a
  number; values outside `0–100` are clipped into range and counted in the
  cleaning report.

### Total
- **Always recalculated** as `Math + Science + English` after cleaning the
  three subject columns, and the original `Total` value is never trusted.
  The cleaning report shows how many rows had a `Total` that didn't match
  the recalculated value.

### Missing values
- Missing numeric fields (`Grade`/`Math`/`Science`/`English`) are imputed
  with the column median. Rows with no usable `Name` at all are dropped
  (they can't be identified or shortlisted) and counted in the report.

### 4. Duplicate detection logic

This is the part that deserved the most care. The source data has **no
unique student identifier** (no roll number, no email) — only first name,
gender, grade, and three scores. The bundled sample dataset draws its names
from a pool of only ~20 common first names across 99 students, so **the same
first name recurs constantly by coincidence**, not because of duplicate data
entry.

A naive "same name → duplicate" rule is actively harmful here: on the sample
dataset it would incorrectly delete over half the (real, distinct) students.
Verified example from the sample data — two rows both named "Aditi", gender
`m`, grade `1`, with scores `68` and `256` respectively. Those are two
different boys named Aditi in the same grade, not one student entered twice.

So the pipeline instead requires **strong evidence** before merging two rows:

> A row is only treated as a duplicate re-entry of the same student when
> `Name` + `Gender` + `Grade` all match **and** all three subject scores are
> within a small tolerance (±2 points) of each other — consistent with the
> same submission being re-typed with a minor slip, not two different people.

- **Strong match** (name+gender+grade+near-identical scores): rows are
  merged, keeping the one with the higher (recalculated) `Total` as the more
  complete record.
- **Weak match** (name+gender+grade match but scores differ meaningfully):
  both rows are **kept** — they're almost certainly different students — and
  the coincidence is logged in the cleaning report for transparency, not
  hidden.

This trades a slightly more complex rule for a pipeline that doesn't quietly
destroy real applicant data, which matters a lot more in a recruitment
context.

---

## 5. Active / Debarred status

Status isn't part of the source CSV — it's tracked live in the app. Every
student defaults to **Active**. Toggling a row to **Debarred** in the table
immediately removes them from the shortlist below (no separate "apply"
step), and the debarred count is shown alongside the shortlist stats.

---

## 6. Deployment (bonus)

The app deploys as-is on [Streamlit Community Cloud](https://streamlit.io/cloud):

1. Push this repo to GitHub.
2. On share.streamlit.io, create a new app pointing at `app.py` on your
   `main` branch.
3. No secrets/config needed — it just needs `requirements.txt`, which is
   already in the repo.

---

## 7. Known limitations / next steps

- Without a unique student ID in the source data, duplicate detection is
  necessarily probabilistic (see §4) — adding a roll number or email column
  upstream would make this exact instead of heuristic.
- Status (Active/Debarred) is session-local; a production version would
  persist it (e.g., to a database or back into the exported CSV) so it
  survives a page refresh.
"# rm_manager" 
