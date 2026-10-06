# PerfectMatchLFP26

Suggests one-to-one pairs of international JYU degree students and local friends from the
**2026 Local Friendship Programme survey export**. It is the 2026 edition of
[PerfectMatchJYU](https://github.com/emmerichmtm/PerfectMatchJYU), rebuilt for the new survey
questions and for an interactive way of working: **interact → compute → review → iterate → save**.

Every international gets a partner whenever the rules allow it; leftover locals are expected.
Programme staff review every suggestion before confirming it.

## Start

On Windows with Python 3.11 or newer (3.12 recommended):

1. Double-click `setup_windows.bat` once (needs internet to install PuLP and its bundled CBC solver).
2. Double-click `start.bat`. The browser opens at **http://localhost:8766** (or another free local port).
3. Choose the survey CSV, or click **Try fictional example**.

From a terminal: `python -m venv .venv`, `.venv\Scripts\python -m pip install -r requirements.txt`,
`.venv\Scripts\python app.py` (`--no-browser`, `--port 9000` are optional).

"Localhost" means your own computer. The app binds only to the loopback interface, accepts only
its own page (Host and Origin checks plus a random session token), and processes data in memory.
Nothing is uploaded anywhere. **Never commit survey exports:** `.gitignore` excludes every CSV
except the fictional example.

## Working with the page

**Left panel - interact**

1. **Survey data.** The raw export, as saved by Excel: semicolon or comma separated, UTF-8 or the
   Windows code page, with both heading rows (question, then option). Columns are found by their
   wording, so a reordered export still works. The data check lists excluded rows and flags.
2. **Weights** 1-10 for the four soft criteria (defaults: languages 8, profile fit 5, age fit 5,
   hobbies 2 = 40/25/25/10 %). *Desirability scales and hard rules* holds the anchors of each
   desirability scale and the switches for the hard rules. **Load / Save** read and write
   `settings.csv`.
3. **Must-haves.** One card per rule, proposed from each person's own words, with the survey
   wording, the rule, and how many people on the other side meet it ("no locals meet this" is
   shown in red before you compute). Edit, mark checked, remove or add rules. **Load / Save**
   read and write `must_haves.csv`.
4. **Locked and forbidden pairs**, set from the pairs table.

**Compute** runs the next iteration. Any change afterwards marks the results as out of date.

**Right panel - review**

- Iteration chips (matched internationals, lowest grade, average, pairs changed since the previous
  iteration). Older iterations can be viewed and their settings restored.
- Tiles: internationals matched, lowest and average pair, locals matched, staff checks, blank
  genders to resolve. A red banner explains any unmatched international.
- **Criteria achievement:** grade distribution per criterion and overall (hover for the pairs).
- **Constraints in this solution:** gender wishes, pets, shared language, must-haves met, staff checks.
- **Pairs:** grade per criterion; click a pair for both profiles side by side, the reasoning per
  criterion and each must-have result. **Lock** keeps a pair in the next iteration, **Forbid**
  excludes it.
- **Save result.csv** and **Save report.txt** for the iteration on screen.

In the fictional example, S9 insists on a family with children aged 5-15 and no local is one, so
iteration 1 matches 19 of 20 and names the blocking rule. Turn S9's rule into a staff check and
compute again: all 20 are matched.

## Scoring

Each soft criterion becomes a **Harrington desirability** d = exp(-exp(-z)), with z linear in the
measured value and calibrated by two anchors: the *just acceptable* value scores **0.50**, the
*fully satisfactory* value **0.80**. The overall desirability is the weighted product
D = Π d<sub>c</sub><sup>w<sub>c</sub>/Σw</sup> (a weighted geometric mean), so one insufficient
criterion pulls a pair down instead of being averaged away.

| Criterion | Measured value | Just acceptable (0.50) | Fully satisfactory (0.80) |
|---|---|---|---|
| Languages | best language both speak, at the lower of the two levels (1 basic, 2 good, 3 native/very good) | basic | good |
| Profile fit | does the partner's profile meet each person's "friend's profile" wish | - | met = 1.00; a missed wish counts 0.25 |
| Age fit | partner's age bracket (midpoint) outside each person's wished ranges, relative to the nearest boundary | 25 % outside | 10 % outside; inside = 1.00 |
| Hobbies | number of shared hobby categories | 2 | 4 |

Profile and age are scored from both sides and combined as a geometric mean; the pair details show
each side. All anchors are adjustable on the page and in `settings.csv`.

**Grades** (the language of the breakdown and its colours): 1 insufficient (< 0.50) ·
2 barely satisfying (0.50+) · 3 ok/solid (0.65+) · 4 very good (0.80+) · 5 perfect (0.90+).
Colours run red → grey → blue so they stay distinguishable with common colour-vision deficiencies;
the grade digit is always shown.

## Rules

**Hard rules** (each can be switched off): both people's gender wishes; no pet conflicts (a pet
owner and someone who wants no pets at visits, or a named kind such as cats); at least one
shared language.

**Blank own gender** is flagged *to be resolved*. Where it matters for the partner's gender wish,
the pair is reported with a minimum (0: the pair would be invalid) and a maximum (gender fits);
the optimization uses their average.

**Must-haves** come from the survey's one must-match choice plus free text. Rule types: partner's
gender, partner speaks a language (minimum level), shared language level, partner has a hobby
category, number of shared hobbies, partner's profile, partner's age range, partner's country of
origin, partner has no (kind of) pet, and **staff check** for wishes the data cannot answer
(education, faculty, "what I appreciate"). Proposed rules apply until changed; editing marks a rule
as checked.

**Data check:** rows are excluded (and listed) when the ID is missing or repeated, the status is
not clearly local or international, a consent statement is not accepted, the row is damaged, or
more than 2 of the 8 key answers are missing (profile, wanted profile, languages, hobbies, age,
wanted age, wanted gender, pets; the limit is a setting).

## Optimization

Three successive optimal solves with the bundled CBC solver: (1) the most pairs (each pair has one
international, so the most internationals matched), (2) the highest lowest pair desirability,
(3) the highest total. Locked pairs are forced in; forbidden pairs are removed. An international
left unmatched is explained either by the checks that rule out every local, or by the group of
internationals competing for too few allowed locals.

## Files

| File | Direction | Content |
|---|---|---|
| survey export CSV | in | the raw survey results |
| `settings.csv` | in/out | `setting,value,description`: weights, anchors, hard rules, limits |
| `must_haves.csv` | in/out | `id,kind,values,level,count,status,note,survey_text` |
| `result.csv` | out | one row per pair: overall desirability (and min/max), grade, desirability and grade per criterion, lock, notes |
| `report.txt` | out | summary, criteria achievement, pairs, unmatched with reasons, excluded rows, review notes, settings, must-haves |

Command line, same calculation:

```bash
.venv\Scripts\python run_matching.py --survey export.csv --settings settings.csv --rules must_haves.csv --result output/result.csv --report output/report.txt
```

`--settings` and `--rules` are optional (defaults and proposed rules).

## Staff manual and Windows package

`manual.pdf` is the illustrated A4 staff manual, linked at the top of the page and included in
the package. Its source is `manual.tex` with screenshots of the fictional example in `manual/`;
compile it with `pdflatex manual.tex` twice (standard LaTeX packages only).

The ready-to-run ZIP needs no Python on the staff computer. Build it on 64-bit Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller==6.22.3
.\build_windows.ps1
```

This creates `dist/PerfectMatchLFP26-Windows.zip` with `PerfectMatchLFP26.exe`, its `_internal`
folder (Python runtime, PuLP and the CBC solver), `START HERE.txt`, `manual.pdf`, templates
(default `settings.csv` and the fictional survey) and third-party notices.
`PerfectMatchLFP26.spec` controls the build; `package_files.py` adds the staff files. The
executable is unsigned; organisations that block unsigned programs need IT to review it.

## Development

```bash
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python tools\make_example_survey.py   # rebuild the fictional example
```

`survey.py` reads the export, `rules.py` proposes and checks must-haves, `scoring.py` holds the
desirability functions and settings, `solver.py` the lexicographic matching, `engine.py` ties
them together and writes the report, `app.py` serves `static/` on localhost.
