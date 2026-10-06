import csv
import io
from pathlib import Path

from survey import Person, decode

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "survey_example.csv"


def example_text() -> str:
    return decode(EXAMPLE.read_bytes())


def example_rows() -> list:
    return list(csv.reader(io.StringIO(example_text()), delimiter=";"))


def to_text(rows, delimiter=";") -> str:
    out = io.StringIO()
    csv.writer(out, delimiter=delimiter, lineterminator="\r\n").writerows(rows)
    return out.getvalue()


def column(rows, question, option=None) -> int:
    """Index of the first column under a question (optionally the given option)."""
    start = next(i for i, q in enumerate(rows[0]) if q.replace("\xa0", " ").lower().startswith(question.lower()))
    if option is None:
        return start
    return next(i for i in range(start, len(rows[0])) if rows[1][i].lower().startswith(option.lower()))


def person(pid="S1", side="international", **fields) -> Person:
    base = dict(profile=["One person"], wanted_profile=[], languages={"english": 3}, hobbies=["Cooking and Baking"],
                gender="female", wanted_gender="any", age=(26, 30), age_label="26 - 30", wanted_age=[])
    base.update(fields)
    return Person(id=pid, side=side, line=3, **base)
