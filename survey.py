"""Read the Local Friendship Programme survey export.

The export has two heading rows: the question, then the option label. Every checkbox option is
its own column and a ticked cell contains the option text. Columns are found by their question
and option wording, not by position, so a reordered export still works.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
import io
import re

LEVEL_NAMES = {1: "basic", 2: "good", 3: "native/very good"}
KEY_ANSWERS = ("profile", "wanted profile", "languages", "hobbies", "age", "wanted age",
               "wanted gender", "pets")
# (keyword in the survey option, short name used in rules, reports and the page). Checked in this
# order: the empty-nester option also mentions "a couple".
PROFILES = [
    ("empty nester", "Empty nester"),
    ("children under 5", "Family, children under 5"),
    ("children of 5 to 15", "Family, children 5-15"),
    ("children over 15", "Family, children over 15"),
    ("jyu degree student", "Finnish JYU student"),
    ("native finn", "Native Finn"),
    ("not originally from finland", "Settled in Finland"),
    ("small group", "Small group of friends"),
    ("pair of friends", "Pair of friends"),
    ("a couple", "Couple"),
    ("one person", "One person"),
]
LANGUAGE_ALIASES = {"suomi": "finnish", "englanti": "english", "ruotsi": "swedish", "svenska": "swedish",
                    "saksa": "german", "deutsch": "german", "espanja": "spanish", "ranska": "french",
                    "farsi": "persian", "venäjä": "russian", "mandarin": "chinese"}
PET_KINDS = {"cat": r"\bcats?\b|kissa", "dog": r"\bdogs?\b|koira", "rabbit": r"\brabbits?\b|\bbunn",
             "bird": r"\bbirds?\b|parrot", "rodent": r"hamster|guinea|\brats?\b|\bmice\b|\bmouse\b|rodent",
             "reptile": r"snake|lizard|reptile", "horse": r"\bhorses?\b"}
SINGLE_LABELS = {"-", "id", "please specify:"}


def clean(value) -> str:
    text = str(value or "").replace("\xa0", " ").replace("’", "'").replace("–", "-")
    return re.sub(r"\s+", " ", text).strip()


def norm(value) -> str:
    return clean(value).lower()


def decode(data: bytes) -> str:
    """Excel saves 'CSV UTF-8' or a Windows code page; accept both."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def age_range(label: str):
    text = norm(label)
    if m := re.search(r"(\d{1,3})\s*-\s*(\d{1,3})", text):
        a, b = int(m[1]), int(m[2])
        return (min(a, b), max(a, b))
    if m := re.search(r"over\s*(\d{1,3})", text):
        return (int(m[1]) + 1, int(m[1]) + 15)
    return None


def range_text(r) -> str:
    return f"{r[0]}-{r[1]}"


def pet_kinds(text: str) -> list[str]:
    return [kind for kind, pattern in PET_KINDS.items() if re.search(pattern, norm(text))]


def language_names(text: str) -> list[str]:
    names = []
    for part in re.split(r"[/,;&+]| and ", norm(text)):
        part = part.strip(" .:")
        if part:
            names.append(LANGUAGE_ALIASES.get(part, part))
    return names


def language_level(text: str) -> int:
    t = norm(text)
    if t.startswith("native") or "very good" in t:
        return 3
    return {"good": 2, "basic": 1}.get(t, 0)


def profile_name(label: str) -> str:
    text = norm(label)
    for keyword, name in PROFILES:
        if keyword in text:
            return name
    return clean(label.split("(")[0])


def hobby_name(label: str) -> str:
    return clean(label.split("|")[0]).rstrip(":").strip()


@dataclass
class Person:
    id: str
    side: str
    line: int
    country: str = ""
    profile: list = field(default_factory=list)
    wanted_profile: list = field(default_factory=list)
    languages: dict = field(default_factory=dict)
    associates: str = ""
    hobbies: list = field(default_factory=list)
    hobbies_other: str = ""
    gender: str = ""
    wanted_gender: str = "any"
    age: tuple | None = None
    age_label: str = ""
    wanted_age: list = field(default_factory=list)
    wanted_age_labels: list = field(default_factory=list)
    has_pets: bool = False
    no_pets_at_home: bool = False
    pets_welcome: bool = False
    no_pets_wanted: bool = False
    pet_text: str = ""
    unwanted_pet_text: str = ""
    pet_kinds: list = field(default_factory=list)
    unwanted_pet_kinds: list = field(default_factory=list)
    motivation: str = ""
    appreciate: str = ""
    additional: str = ""
    must_criterion: str = ""
    must_text: str = ""
    previously: str = ""
    missing: list = field(default_factory=list)
    flags: list = field(default_factory=list)

    @property
    def international(self) -> bool:
        return self.side == "international"

    def public(self) -> dict:
        data = asdict(self)
        data["age"] = list(self.age) if self.age else None
        data["wanted_age"] = [list(r) for r in self.wanted_age]
        return data


@dataclass
class Survey:
    people: list
    excluded: list
    options: dict
    rows: int

    def by_id(self) -> dict:
        return {p.id: p for p in self.people}

    @property
    def internationals(self):
        return [p for p in self.people if p.international]

    @property
    def locals(self):
        return [p for p in self.people if not p.international]


def _rows(text: str):
    text = text.lstrip("﻿")
    if not text.strip():
        raise ValueError("The survey file is empty.")
    for delimiter in (";", ",", "\t"):
        try:
            rows = list(csv.reader(io.StringIO(text), delimiter=delimiter, strict=True))
        except csv.Error:
            continue
        if rows and any(norm(cell).startswith("my status") for cell in rows[0]):
            return rows
    raise ValueError("This does not look like the survey export: the heading 'My status' was not found. "
                     "Export the survey results again as CSV, keeping both heading rows.")


def _groups(questions, labels):
    """Group columns under their question; a blank question after a single-answer column starts a new field."""
    groups = []
    for col, (question, label) in enumerate(zip(questions, labels)):
        question, label = clean(question), clean(label)
        if question or not groups or norm(groups[-1][1][-1][1]) in SINGLE_LABELS:
            groups.append([norm(question or label), [(col, label)]])
        else:
            groups[-1][1].append((col, label))
    return groups


FIELDS = {
    "id": lambda q: q == "id",
    "status": lambda q: q.startswith("my status"),
    "previously": lambda q: q.startswith("have you participated"),
    "country": lambda q: q.startswith("country of origin"),
    "profile": lambda q: q.startswith("my/our profile") or q.startswith("my profile"),
    "wanted_profile": lambda q: q.startswith("your future friend's profile"),
    "languages": lambda q: q.startswith("please, name the language") and "open text" not in q,
    "language_names": lambda q: q.startswith("please, name the language") and "open text" in q,
    "associates": lambda q: q.startswith("languages and levels of your associates"),
    "hobbies": lambda q: q.startswith("hobbies and interests") and "open text" not in q,
    "hobbies_text": lambda q: q.startswith("hobbies and interests") and "open text" in q,
    "gender": lambda q: q.startswith("my gender"),
    "wanted_gender": lambda q: q.startswith("friend's gender"),
    "age": lambda q: q.startswith("my age"),
    "wanted_age": lambda q: q.startswith("friend's age"),
    "pets": lambda q: q.startswith("pet allergies") and "open text" not in q,
    "pets_text": lambda q: q.startswith("pet allergies") and "open text" in q,
    "motivation": lambda q: "motivates you" in q,
    "appreciate": lambda q: q.startswith("things you appreciate"),
    "additional": lambda q: q.startswith("additional information"),
    "must": lambda q: q.startswith("the must match criteria"),
}
REQUIRED = ("id", "status", "profile", "wanted_profile", "languages", "hobbies", "gender",
            "wanted_gender", "age", "wanted_age", "pets", "must")
CONSENT = (lambda q: q == "the programme", lambda q: q == "the principles",
           lambda q: q.startswith("by submitting the data"), lambda q: q.startswith("all participants of the local"))


def read_survey(text: str, max_missing: int = 2) -> Survey:
    rows = _rows(text)
    if len(rows) < 2:
        raise ValueError("The survey export needs both heading rows (questions and options).")
    groups = _groups(rows[0], rows[1])
    found = {}
    for name, matches in FIELDS.items():
        found[name] = next((cols for question, cols in groups if matches(question)), None)
    missing = [name for name in REQUIRED if not found[name]]
    if missing:
        raise ValueError("The survey export is missing these questions: " + ", ".join(missing).replace("_", " ")
                         + ". Export all questions with both heading rows.")
    consent_groups = [next((cols for question, cols in groups if matches(question)), None) for matches in CONSENT]
    specs = {norm(question.split(":", 1)[1]).split(" ")[0]: cols[0][0]
             for question, cols in groups if question.startswith("specs for your criteria") and ":" in question}

    hobby_options = [hobby_name(label) for _, label in found["hobbies"] if not norm(label).startswith("other")]
    options = {
        "profiles": [profile_name(label) for _, label in found["profile"]],
        "hobbies": hobby_options,
        "wanted_ages": [clean(label) for _, label in found["wanted_age"] if age_range(label)],
        "genders": [],
        "languages": [],
        "pet_kinds": list(PET_KINDS) + ["any"],
        "countries": [],
    }
    people, excluded, seen = [], [], {}
    width = len(rows[0])
    for number, row in enumerate(rows[2:], start=3):
        if not any(cell.strip() for cell in row):
            continue
        cell = lambda col: clean(row[col]) if col < len(row) else ""
        first = lambda name: cell(found[name][0][0]) if found.get(name) else ""
        pid = first("id")
        reasons = []
        if len(row) != width:
            reasons.append(f"row has {len(row)} cells instead of {width}; the export may be damaged")
        if not pid:
            reasons.append("ID is missing")
        status = norm(first("status"))
        side = "local" if "local resident" in status or status == "local" else (
            "international" if "international" in status or status == "student" else "")
        if not side:
            reasons.append("status is not clearly local resident or international student")
        if any(group and not cell(group[0][0]) for group in consent_groups):
            reasons.append("consent or programme statements were not all accepted")
        p = Person(id=pid, side=side, line=number, country=first("country"))
        ticked = lambda name: [label for col, label in found[name] if cell(col)] if found.get(name) else []
        p.profile = [profile_name(label) for label in ticked("profile")]
        p.wanted_profile = [profile_name(label) for label in ticked("wanted_profile")]
        names = {norm(label).split(":")[0]: cell(col) for col, label in (found["language_names"] or [])}
        for col, label in found["languages"]:
            level, key = language_level(cell(col)), norm(label).rstrip(":")
            spoken = language_names(names.get(key, "")) if key.startswith("language") else language_names(label)
            if level and spoken:
                for name in spoken:
                    p.languages[name] = max(level, p.languages.get(name, 0))
            elif key.startswith("language") and (level or names.get(key)):
                p.flags.append(f"{label.rstrip(':')}: give both the language and its level")
        p.associates = first("associates")
        p.hobbies = [hobby_name(label) for label in ticked("hobbies") if not norm(label).startswith("other")]
        p.hobbies_other = first("hobbies_text")
        p.gender = norm(first("gender"))
        wanted = norm(first("wanted_gender"))
        p.wanted_gender = "any" if not wanted or "all" in wanted or "no preference" in wanted else wanted
        p.age_label = first("age")
        p.age = age_range(p.age_label)
        wanted_ages = ticked("wanted_age")
        p.wanted_age_labels = [clean(label) for label in wanted_ages]
        if not any("all ages" in norm(label) for label in wanted_ages):
            p.wanted_age = [r for r in (age_range(label) for label in wanted_ages) if r]
        pet_answers = [norm(label) for label in ticked("pets")]
        p.has_pets = any("do have a pet" in a for a in pet_answers)
        p.no_pets_at_home = any("don't have any pets" in a or "do not have any pets" in a for a in pet_answers)
        p.pets_welcome = any("all pets are welcome" in a for a in pet_answers)
        p.no_pets_wanted = any("do not want any pets" in a for a in pet_answers)
        for col, label in found["pets_text"] or []:
            if "have a pet" in norm(label):
                p.pet_text = cell(col)
            elif "kind" in norm(label):
                p.unwanted_pet_text = cell(col)
        p.pet_kinds = pet_kinds(p.pet_text)
        p.unwanted_pet_kinds = pet_kinds(p.unwanted_pet_text)
        p.motivation, p.appreciate, p.additional = first("motivation"), first("appreciate"), first("additional")
        p.must_criterion = first("must")
        criterion = norm(p.must_criterion).split(" ")[0] if p.must_criterion else ""
        if criterion in specs:
            p.must_text = cell(specs[criterion])
        if not p.must_text and p.must_criterion:
            p.must_text = " / ".join(cell(col) for col in specs.values() if cell(col))
        p.previously = first("previously")

        answered = {"profile": p.profile, "wanted profile": p.wanted_profile, "languages": p.languages,
                    "hobbies": p.hobbies, "age": p.age, "wanted age": wanted_ages,
                    "wanted gender": first("wanted_gender"), "pets": pet_answers}
        p.missing = [name for name in KEY_ANSWERS if not answered[name]]
        if len(p.missing) > max_missing:
            reasons.append(f"{len(p.missing)} key answers missing ({', '.join(p.missing)}); "
                           f"the limit is {max_missing}")
        elif p.missing:
            p.flags.append("missing answers: " + ", ".join(p.missing))
        if not p.gender:
            p.flags.append("own gender is blank - to be resolved")
        if p.has_pets and p.no_pets_at_home:
            p.flags.append("pet answers contradict each other (has pets and has no pets)")
        if p.has_pets and not p.pet_kinds:
            p.flags.append("has pets, but the kind of pet is not clear")
        if p.unwanted_pet_text and not p.unwanted_pet_kinds:
            p.flags.append("pet restriction without a recognised kind of pet: " + p.unwanted_pet_text)
        if p.must_criterion and not p.must_text:
            p.flags.append(f"must-have '{p.must_criterion}' chosen without a specification")
        if reasons:
            excluded.append({"id": pid or f"(line {number})", "line": number, "side": side, "reasons": reasons})
        else:
            people.append(p)
        if pid:
            seen.setdefault(pid, []).append(number)
    duplicates = {pid for pid, lines in seen.items() if len(lines) > 1}
    if duplicates:
        for p in [p for p in people if p.id in duplicates]:
            people.remove(p)
            excluded.append({"id": p.id, "line": p.line, "side": p.side, "reasons": ["ID appears more than once"]})
    excluded.sort(key=lambda e: e["line"])
    languages = {}
    for p in people:
        for name in p.languages:
            languages[name] = languages.get(name, 0) + 1
    options["languages"] = sorted(languages, key=lambda n: (-languages[n], n))
    options["genders"] = sorted({p.gender for p in people if p.gender})
    options["countries"] = sorted({p.country for p in people if p.country and p.international})
    return Survey(people, excluded, options, len(rows) - 2)
