"""Must-have rules: one person's hard requirement on their partner.

The survey asks for one must-match criterion plus free text. propose_rules() turns that text into
checkable rules where the wording is clear and into a "staff check" otherwise. Staff review and edit
the rules on the page; a rules CSV saves and reloads them.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
import io
import re

import scoring
from survey import LEVEL_NAMES, age_range, clean, norm, pet_kinds, range_text

KINDS = {
    "partner_gender": "Partner's gender is",
    "partner_language": "Partner speaks",
    "shared_language": "A shared language at level",
    "partner_hobby": "Partner has hobby",
    "shared_hobbies": "Shared hobby categories, at least",
    "partner_profile": "Partner's profile is",
    "partner_age": "Partner's age within",
    "partner_country": "Partner's country of origin",
    "partner_no_pet": "Partner has no",
    "staff_check": "Staff check",
}
KNOWN_LANGUAGES = ("english", "finnish", "swedish", "german", "spanish", "french", "italian", "portuguese",
                   "russian", "estonian", "latvian", "danish", "norwegian", "dutch", "hungarian", "czech",
                   "polish", "chinese", "cantonese", "japanese", "korean", "arabic", "persian", "turkish",
                   "hindi", "urdu", "bengali", "nepali", "indonesian", "vietnamese", "ukrainian")
HOBBY_WORDS = {  # word fragment -> start of the survey category
    "sport": "Sports", "outdoor activit": "Sports", "music": "Music enjoying", "sing": "Music playing",
    "instrument": "Music playing", "read": "Reading", "writ": "Reading", "cook": "Cooking", "bak": "Cooking",
    "nature": "Nature", "hik": "Nature", "travel": "Travelling", "adventure": "Travelling",
    "social": "Socializing", "entertain": "Socializing", "personal development": "Personal Development",
    "learn": "Personal Development", "animal": "Animal", "craft": "Handicrafts", "diy": "Handicrafts",
    "knit": "Handicrafts", "visual art": "Visual Art", "paint": "Visual Art", "draw": "Visual Art",
    "cultur": "Cultural heritage", "heritage": "Cultural heritage",
}
COUNTRIES = {"korea": "Korea", "japan": "Japan", "china": "China", "chinese": "China", "india": "India",
             "iran": "Iran", "pakistan": "Pakistan", "indonesia": "Indonesia", "vietnam": "Vietnam",
             "nepal": "Nepal", "bangladesh": "Bangladesh", "sri lanka": "Sri Lanka", "nigeria": "Nigeria",
             "namibia": "Namibia", "france": "France", "germany": "Germany", "spain": "Spain", "italy": "Italy",
             "hungar": "Hungary", "romania": "Romania", "czech": "Czech", "usa": "USA", "america": "USA",
             "brazil": "Brazil", "mexic": "Mexico", "turk": "Turkey", "ukrain": "Ukraine", "russia": "Russia"}


@dataclass
class Rule:
    id: str
    kind: str
    values: list = field(default_factory=list)
    level: int = 1
    count: int = 1
    status: str = "proposed"
    note: str = ""
    text: str = ""

    def describe(self) -> str:
        values = ", ".join(self.values)
        if self.kind == "partner_language":
            return f"Partner speaks {values or '?'} (at least {LEVEL_NAMES[self.level]})"
        if self.kind == "shared_language":
            return f"A shared language at least {LEVEL_NAMES[self.level]}"
        if self.kind == "partner_hobby":
            return f"Partner has {'any' if self.count == 1 else f'at least {self.count}'} of: {values or '?'}"
        if self.kind == "shared_hobbies":
            return f"At least {self.count} shared hobby categor{'y' if self.count == 1 else 'ies'}"
        if self.kind == "partner_no_pet":
            return "Partner has no pets" if "any" in self.values else f"Partner has no {values or '?'}"
        if self.kind == "staff_check":
            return "Staff check: " + (self.note or self.text or "see survey answer")
        return f"{KINDS.get(self.kind, self.kind)} {values or '?'}"


def check(rule: Rule, me, partner):
    """True when the partner meets the rule, False when not, None when it must be resolved by staff."""
    kind, values = rule.kind, [norm(v) for v in rule.values]
    if kind == "partner_gender":
        return None if not partner.gender else partner.gender in values
    if kind == "partner_language":
        return any(partner.languages.get(v, 0) >= rule.level for v in values)
    if kind == "shared_language":
        return scoring.best_shared_language(me, partner)[0] >= rule.level
    if kind == "partner_hobby":
        return len({norm(h) for h in partner.hobbies} & set(values)) >= rule.count
    if kind == "shared_hobbies":
        return len(scoring.shared_hobbies(me, partner)) >= rule.count
    if kind == "partner_profile":
        return bool({norm(p) for p in partner.profile} & set(values))
    if kind == "partner_age":
        ranges = [r for r in (age_range(v) for v in values) if r]
        return partner.age is not None and any(partner.age[0] <= b and partner.age[1] >= a for a, b in ranges)
    if kind == "partner_country":
        return any(v in norm(partner.country) for v in values)
    if kind == "partner_no_pet":
        if "any" in values:
            return not partner.has_pets
        return not (partner.has_pets and set(partner.pet_kinds) & set(values))
    return True  # staff_check is never enforced automatically


def _find_hobbies(text: str, categories: list) -> list:
    found = []
    for category in categories:
        if norm(category) in text:
            found.append(category)
    for fragment, start in HOBBY_WORDS.items():
        if re.search(r"\b" + re.escape(fragment), text):
            found += [c for c in categories if c.startswith(start)]
    return list(dict.fromkeys(found))


def _level(text: str) -> int:
    if re.search(r"native|mother tongue|primary", text):
        return 3
    if re.search(r"fluent|conversation|without (the use of )?translat|very good|\bgood\b", text):
        return 2
    return 1


def propose_rules(p, options: dict) -> list:
    """Interpret one person's must-match choice and free text; every result starts as 'proposed'."""
    criterion, raw = norm(p.must_criterion), clean(p.must_text)
    text = norm(raw)
    rule = lambda kind, note, **kw: Rule(p.id, kind, text=raw, note=note, **kw)
    if not criterion:
        return []
    if criterion.startswith("gender"):
        if re.search(r"female|wom[ae]n|girl|\bno (men|males?)\b|\bnot? (a )?m[ae]n\b", text):
            return [rule("partner_gender", "from the wording", values=["female"])]
        if re.search(r"\bmales?\b|\bm[ae]n\b", text):
            return [rule("partner_gender", "from the wording", values=["male"])]
        if p.wanted_gender != "any":
            return [rule("partner_gender", "from the friend's gender answer", values=[p.wanted_gender])]
        return [rule("staff_check", "gender wish is unclear")]
    if criterion.startswith("language"):
        # A language the person is still learning is not a requirement on the partner.
        text = re.sub(r"\b(working on|learning|learn|studying|improving)\s+((my|some|the|a bit of)\s+)?\w+", " ", text)
        text = re.sub(r"\bnot (very )?good\b", " ", text)
        languages = [name for name in KNOWN_LANGUAGES + tuple(options.get("languages", ()))
                     if re.search(r"\b" + re.escape(name), text) or (name == "finnish" and "suomi" in text)]
        languages = list(dict.fromkeys(languages))
        if languages:
            return [rule("partner_language", "languages named in the answer", values=languages, level=_level(text))]
        if text:
            return [rule("shared_language", "no language named; a shared language is required", level=_level(text))]
        return [rule("shared_language", "no specification; a shared language is required", level=1)]
    if criterion.startswith("hobbies"):
        found = _find_hobbies(text, options.get("hobbies", []))
        if found:
            return [rule("partner_hobby", "hobby categories named in the answer", values=found)]
        return [rule("shared_hobbies", "no category named; at least one shared category", count=1)]
    if criterion.startswith("profile"):
        families = []
        if re.search(r"kid|child|famil", text):
            ages = [int(n) for n in re.findall(r"\d{1,2}", text)]
            for name, test in (("Family, children under 5", lambda a: a < 5),
                               ("Family, children 5-15", lambda a: 5 <= a <= 15),
                               ("Family, children over 15", lambda a: a > 15)):
                if not ages or any(test(a) for a in ages):
                    families.append(name)
        named = [o for o in options.get("profiles", []) if norm(o) in text]
        if families or named:
            return [rule("partner_profile", "profile named in the answer", values=list(dict.fromkeys(families + named)))]
        if not text and p.wanted_profile:
            return [rule("partner_profile", "from the friend's profile answer", values=list(p.wanted_profile))]
        return [rule("staff_check", "profile wish cannot be checked from the survey data")]
    if criterion.startswith("age"):
        ranges = [f"{a}-{b}" for a, b in re.findall(r"(\d{2})\s*-\s*(\d{2})", text)]
        if ranges:
            return [rule("partner_age", "age range in the answer", values=ranges)]
        if p.wanted_age:
            return [rule("partner_age", "from the friend's age answer", values=[range_text(r) for r in p.wanted_age])]
        return [rule("staff_check", "age wish is unclear")]
    if criterion.startswith("field"):
        return [rule("staff_check", "fields of study are not in the survey data")]
    # "Other": take what can be checked and leave the rest to staff.
    found = []
    countries = list(dict.fromkeys(name for word, name in COUNTRIES.items() if word in text))
    if countries:
        found.append(rule("partner_country", "country named in the answer", values=countries))
    kinds = pet_kinds(text)
    if kinds:
        found.append(rule("partner_no_pet", "pet named in the answer", values=kinds))
    if re.search(r"hobb|interest", text):
        found.append(rule("shared_hobbies", "hobbies mentioned; at least one shared category", count=1))
    if not found or re.search(r"apprecia|facult|department|field|religio|smok", text):
        found.append(rule("staff_check", "part of the wish cannot be checked automatically"))
    return found


RULE_COLUMNS = ["id", "kind", "values", "level", "count", "status", "note", "survey_text"]


def rules_to_csv(rules: list) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(RULE_COLUMNS)
    for r in rules:
        writer.writerow([r.id, r.kind, "; ".join(r.values), r.level, r.count, r.status, r.note, r.text])
    return out.getvalue()


def from_dict(data: dict, ids=None) -> Rule:
    kind = str(data.get("kind", "")).strip()
    pid = str(data.get("id", "")).strip()
    if kind not in KINDS:
        raise ValueError(f"Rule for {pid or '?'}: unknown kind '{kind}'. Use one of: {', '.join(KINDS)}.")
    if ids is not None and pid not in ids:
        raise ValueError(f"Rule for '{pid}': no participant with this ID in the survey (or the row was excluded).")
    values = data.get("values", [])
    if isinstance(values, str):
        values = [v.strip() for v in values.split(";") if v.strip()]
    try:
        level, count = int(data.get("level") or 1), int(data.get("count") or 1)
    except ValueError as exc:
        raise ValueError(f"Rule for {pid}: level and count must be whole numbers.") from exc
    if not 1 <= level <= 3 or not 1 <= count <= 20:
        raise ValueError(f"Rule for {pid}: level must be 1-3 and count 1-20.")
    if kind not in ("shared_language", "shared_hobbies", "staff_check") and not values:
        raise ValueError(f"Rule for {pid} ({kind}): choose at least one value.")
    status = str(data.get("status") or "proposed").strip().lower()
    return Rule(pid, kind, [str(v) for v in values], level, count,
                status if status in ("proposed", "confirmed") else "proposed",
                str(data.get("note") or ""), str(data.get("text", data.get("survey_text", "")) or ""))


def rules_from_csv(text: str, ids=None) -> list:
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if rows and set(RULE_COLUMNS[:2]) - set(rows[0]):
        raise ValueError("Rules CSV: the first row must contain " + ",".join(RULE_COLUMNS) + ".")
    return [from_dict(row, ids) for row in rows if any((v or "").strip() for v in row.values())]


def to_dict(rule: Rule) -> dict:
    return {**asdict(rule), "label": rule.describe()}
