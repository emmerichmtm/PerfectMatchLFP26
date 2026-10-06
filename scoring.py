"""Desirability scoring: Harrington desirabilities per criterion, combined as a weighted product.

Each soft criterion is mapped to a desirability d between 0 and 1 by a Harrington curve
d = exp(-exp(-z)), with z linear in the measured value and calibrated by two anchors:
the "just acceptable" value gives d = 0.5 and the "fully satisfactory" value gives d = 0.8.
Weights 1-10 become exponents (normalized to sum to 1), so the overall desirability is the
weighted geometric mean D = prod(d_c ** (w_c / sum(w))). A single insufficient criterion pulls
D down sharply, which a weighted sum would hide.
"""
from __future__ import annotations

import csv
import io
import math

Z_ACCEPTABLE = -math.log(math.log(2))      # d = 0.5
Z_SATISFACTORY = -math.log(-math.log(0.8))  # d = 0.8
LEVELS = {1: "basic", 2: "good", 3: "native/very good"}
SIDE = {"student": "international", "local": "local"}
GRADES = {1: "insufficient", 2: "barely satisfying", 3: "ok / solid", 4: "very good", 5: "perfect"}
GRADE_FLOORS = ((0.9, 5), (0.8, 4), (0.65, 3), (0.5, 2))
CRITERIA = {
    "language": "Languages",
    "profile": "Profile fit",
    "age": "Age fit",
    "hobbies": "Hobbies",
}
# name: (default, type, minimum, maximum, description)
SETTINGS = {
    "weight_language": (8, int, 1, 10, "Weight 1-10 of the best shared language level"),
    "weight_profile": (5, int, 1, 10, "Weight 1-10 of each person's profile wishes"),
    "weight_age": (5, int, 1, 10, "Weight 1-10 of each person's age wishes"),
    "weight_hobbies": (2, int, 1, 10, "Weight 1-10 of shared hobby categories"),
    "language_acceptable": (1, float, 0, 3, "Shared language level that is just acceptable (1 basic, 2 good, 3 native)"),
    "language_satisfactory": (2, float, 0, 3, "Shared language level that is fully satisfactory"),
    "hobbies_acceptable": (2, float, 0, 20, "Number of shared hobby categories that is just acceptable"),
    "hobbies_satisfactory": (4, float, 0, 20, "Number of shared hobby categories that is fully satisfactory"),
    "age_satisfactory": (0.10, float, 0, 1, "Age outside the wished range by this share is still fully satisfactory"),
    "age_tolerance": (0.25, float, 0, 1, "Age outside the wished range by this share is just acceptable; beyond is insufficient"),
    "profile_missed": (0.25, float, 0.01, 1, "Desirability when a person's profile wish is not met"),
    "enforce_gender": (True, bool, None, None, "Respect both people's gender wishes"),
    "enforce_pets": (True, bool, None, None, "Never pair pet owners with people who do not want those pets"),
    "require_shared_language": (True, bool, None, None, "Require at least one shared language"),
    "max_missing_answers": (2, int, 0, 8, "Exclude rows missing more than this many of the 8 key answers"),
    "solver_time_limit_seconds": (60, int, 1, 86400, "Time limit for each of the three solving stages"),
}


def default_settings() -> dict:
    return {name: spec[0] for name, spec in SETTINGS.items()}


def validate_settings(values: dict) -> dict:
    settings = default_settings()
    for name, value in values.items():
        if name not in SETTINGS:
            raise ValueError(f"Unknown setting '{name}'.")
        default, kind, low, high, _ = SETTINGS[name]
        if kind is bool:
            if isinstance(value, str):
                if value.strip().lower() not in ("true", "false"):
                    raise ValueError(f"{name}: use TRUE or FALSE.")
                value = value.strip().lower() == "true"
            settings[name] = bool(value)
            continue
        try:
            number = float(str(value).replace(",", ".")) if isinstance(value, str) else float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name}: enter a number.") from exc
        if not math.isfinite(number) or not low <= number <= high:
            raise ValueError(f"{name}: use a number from {low:g} to {high:g}.")
        if kind is int and number != int(number):
            raise ValueError(f"{name}: use a whole number.")
        settings[name] = int(number) if kind is int else number
    for criterion in ("language", "hobbies"):
        if settings[f"{criterion}_satisfactory"] <= settings[f"{criterion}_acceptable"]:
            raise ValueError(f"{criterion}_satisfactory must be greater than {criterion}_acceptable.")
    if settings["age_satisfactory"] >= settings["age_tolerance"]:
        raise ValueError("age_satisfactory must be smaller than age_tolerance.")
    return settings


def settings_to_csv(settings: dict) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["setting", "value", "description"])
    for name, (_, kind, _, _, description) in SETTINGS.items():
        value = settings[name]
        writer.writerow([name, str(value).upper() if kind is bool else f"{value:g}", description])
    return out.getvalue()


def settings_from_csv(text: str) -> dict:
    text = text.lstrip("﻿")
    delimiter = ";" if text.split("\n", 1)[0].count(";") > text.split("\n", 1)[0].count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if not rows or [c.strip().lower() for c in rows[0][:2]] != ["setting", "value"]:
        raise ValueError("Settings CSV: the first row must be setting,value,description.")
    values = {}
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        name = row[0].strip()
        if name in values:
            raise ValueError(f"Settings CSV: '{name}' appears more than once.")
        values[name] = row[1].strip() if len(row) > 1 else ""
    return validate_settings(values)


def harrington(value: float, acceptable: float, satisfactory: float) -> float:
    z = Z_ACCEPTABLE + (value - acceptable) * (Z_SATISFACTORY - Z_ACCEPTABLE) / (satisfactory - acceptable)
    return math.exp(-math.exp(-max(-30.0, min(30.0, z))))


def grade(d: float) -> int:
    d = round(d, 6)
    return next((g for floor, g in GRADE_FLOORS if d >= floor), 1)


def best_shared_language(a, b):
    """(level, language) of the best language both speak, at the lower of the two levels."""
    shared = [(min(level, b.languages[name]), name) for name, level in a.languages.items() if name in b.languages]
    return max(shared, default=(0, ""))


def shared_hobbies(a, b) -> list:
    return [h for h in a.hobbies if h in set(b.hobbies)]


def age_gap(age, wanted) -> float:
    """Distance of a partner's age bracket outside the wished ranges, relative to the nearest boundary.

    Uses the bracket midpoint (a typical age); 0 when the brackets overlap or there is no wish.
    """
    if not wanted or age is None:
        return 0.0
    lo, hi = age
    if any(lo <= b and hi >= a for a, b in wanted):
        return 0.0
    middle = (lo + hi) / 2
    return min((a - middle) / a if middle < a else (middle - b) / b for a, b in wanted)


def age_desirability(age, wanted, settings) -> float:
    gap = age_gap(age, wanted)
    if gap == 0:
        return 1.0
    return harrington(gap, settings["age_tolerance"], settings["age_satisfactory"])


def profile_desirability(partner_profile, wanted, settings) -> float:
    if not wanted or set(partner_profile) & set(wanted):
        return 1.0
    return settings["profile_missed"]


def criteria(s, l, settings) -> dict:
    """Desirability, grade and explanation for each soft criterion of the pair (student s, local l)."""
    level, language = best_shared_language(s, l)
    hobbies = shared_hobbies(s, l)
    profile = {"student": profile_desirability(l.profile, s.wanted_profile, settings),
               "local": profile_desirability(s.profile, l.wanted_profile, settings)}
    age = {"student": age_desirability(l.age, s.wanted_age, settings),
           "local": age_desirability(s.age, l.wanted_age, settings)}
    gaps = {"student": age_gap(l.age, s.wanted_age), "local": age_gap(s.age, l.wanted_age)}
    result = {
        "language": {"d": harrington(level, settings["language_acceptable"], settings["language_satisfactory"]),
                     "detail": f"{language.title()}, {LEVELS.get(level, 'none')}" if language else "no shared language"},
        "hobbies": {"d": harrington(len(hobbies), settings["hobbies_acceptable"], settings["hobbies_satisfactory"]),
                    "detail": f"{len(hobbies)} shared: " + ", ".join(hobbies) if hobbies else "no shared categories",
                    "shared": hobbies},
        "profile": {"d": math.sqrt(profile["student"] * profile["local"]), "sides": profile,
                    "detail": "; ".join(f"{SIDE[side]}'s wish {'met' if d == 1 else 'missed'}" for side, d in profile.items())},
        "age": {"d": math.sqrt(age["student"] * age["local"]), "sides": age,
                "detail": "; ".join(f"{SIDE[side]}'s wish " + ("met" if gaps[side] == 0 else f"missed by {gaps[side]:.0%}")
                                    for side in ("student", "local"))},
    }
    for value in result.values():
        value["grade"] = grade(value["d"])
        for side, d in value.get("sides", {}).items():
            value.setdefault("side_grades", {})[side] = grade(d)
    return result



def weights(settings) -> dict:
    total = sum(settings[f"weight_{c}"] for c in CRITERIA)
    return {c: settings[f"weight_{c}"] / total for c in CRITERIA}


def overall(result: dict, settings) -> float:
    return math.prod(result[c]["d"] ** w for c, w in weights(settings).items())


def gender_check(wanted: str, partner_gender: str):
    """True/False, or None when the partner's own gender is blank and must be resolved."""
    if wanted == "any":
        return True
    if not partner_gender:
        return None
    return wanted == partner_gender


def pets_conflict(a, b):
    for x, y in ((a, b), (b, a)):
        if x.has_pets and y.no_pets_wanted:
            return f"{x.id} has pets; {y.id} does not want pets at visits"
        clash = set(x.pet_kinds) & set(y.unwanted_pet_kinds)
        if x.has_pets and clash:
            return f"{x.id} has {'/'.join(sorted(clash))}; {y.id} does not want them"
    return ""
