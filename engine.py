"""Evaluate pairs, solve, and describe the solution for the page, the report and the result CSV."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import re

import rules as rulebook
import scoring
import solver
from survey import read_survey

RESULT_COLUMNS = (["student_id", "local_id", "score", "score_min", "score_max", "grade", "grade_name"]
                  + [f"{c}_{k}" for c in scoring.CRITERIA for k in ("desirability", "grade")]
                  + ["locked", "notes"])
CHECK_NAMES = {"gender": "gender wishes", "pets": "pets", "language": "no shared language",
               "own_rule": "own must-have", "partner_rule": "partner's must-have", "forbidden": "forbidden by staff"}


def natural(text: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def load(survey_text: str, settings: dict, rule_dicts=None):
    survey = read_survey(survey_text, settings["max_missing_answers"])
    people = survey.by_id()
    if rule_dicts is None:
        rule_list = [r for p in survey.people for r in rulebook.propose_rules(p, survey.options)]
    else:
        rule_list = [rulebook.from_dict(r, set(people)) for r in rule_dicts]
    return survey, people, rule_list


def evaluate(s, l, settings, rules_by_id) -> dict:
    """Hard checks and soft desirability of one pair; uncertain checks are those needing staff (blank gender)."""
    checks = []
    if settings["enforce_gender"]:
        checks.append(("gender", scoring.gender_check(s.wanted_gender, l.gender),
                       f"{s.id} wishes for {s.wanted_gender}; {l.id}'s gender is {l.gender or 'blank'}"))
        checks.append(("gender", scoring.gender_check(l.wanted_gender, s.gender),
                       f"{l.id} wishes for {l.wanted_gender}; {s.id}'s gender is {s.gender or 'blank'}"))
    if settings["enforce_pets"]:
        conflict = scoring.pets_conflict(s, l)
        checks.append(("pets", not conflict, conflict))
    if settings["require_shared_language"]:
        checks.append(("language", scoring.best_shared_language(s, l)[0] >= 1, "no shared language"))
    rule_results = []
    for owner, partner, kind in ((s, l, "own_rule"), (l, s, "partner_rule")):
        for rule in rules_by_id.get(owner.id, []):
            if rule.kind == "staff_check":
                rule_results.append({"owner": owner.id, "label": rule.describe(), "result": "staff"})
                continue
            result = rulebook.check(rule, owner, partner)
            checks.append((kind, result, f"{owner.id}: {rule.describe()}"))
            rule_results.append({"owner": owner.id, "label": rule.describe(),
                                 "result": {True: "met", False: "not met", None: "to resolve"}[result]})
    failures = [name for name, result, _ in checks if result is False]
    uncertain = [text for _, result, text in checks if result is None]
    crit = scoring.criteria(s, l, settings)
    best = scoring.overall(crit, settings)
    worst = 0.0 if uncertain else best  # if the blank gender turns out not to fit, the pair is invalid
    return {"eligible": not failures, "failures": failures, "uncertain": uncertain, "criteria": crit,
            "score_max": best, "score_min": worst, "score": (best + worst) / 2, "rules": rule_results}


def impact(survey_text: str, settings: dict, rule_dicts: list) -> list:
    """For each rule: how many people on the other side meet it (uncertain counts as possible)."""
    survey, people, rule_list = load(survey_text, settings, rule_dicts)
    counts = []
    for rule in rule_list:
        me = people[rule.id]
        others = [p for p in survey.people if p.international != me.international]
        counts.append(None if rule.kind == "staff_check" else
                      sum(rulebook.check(rule, me, other) is not False for other in others))
    return counts


def analyse(survey_text: str, settings: dict, rule_dicts=None) -> dict:
    survey, people, rule_list = load(survey_text, settings, rule_dicts)
    return {"people": {pid: p.public() for pid, p in people.items()},
            "excluded": survey.excluded, "rows": survey.rows, "options": survey.options,
            "counts": {"internationals": len(survey.internationals), "locals": len(survey.locals)},
            "rules": [rulebook.to_dict(r) for r in rule_list],
            "impact": impact(survey_text, settings, [rulebook.to_dict(r) for r in rule_list])}


def compute(survey_text: str, settings: dict, rule_dicts, locks=(), forbids=(), *, iteration=1,
            survey_name="survey.csv") -> dict:
    survey, people, rule_list = load(survey_text, settings, rule_dicts)
    rules_by_id = {}
    for rule in rule_list:
        rules_by_id.setdefault(rule.id, []).append(rule)
    students = sorted(survey.internationals, key=lambda p: natural(p.id))
    locals_ = sorted(survey.locals, key=lambda p: natural(p.id))
    forbidden = {tuple(pair) for pair in forbids}
    evaluations, scores, failures = {}, {}, {s.id: {} for s in students}
    for s in students:
        for l in locals_:
            e = evaluate(s, l, settings, rules_by_id)
            if (s.id, l.id) in forbidden:
                e["eligible"], e["failures"] = False, e["failures"] + ["forbidden"]
            evaluations[(s.id, l.id)] = e
            for name in set(e["failures"]):
                failures[s.id][name] = failures[s.id].get(name, 0) + 1
            if e["eligible"]:
                scores[(s.id, l.id)] = e["score"]
    warnings, locked = [], []
    for pair in [tuple(p) for p in locks]:
        if pair not in scores:
            warnings.append(f"Lock {pair[0]}-{pair[1]} was dropped: the pair is not allowed under the current rules.")
        elif any(pair[0] == s or pair[1] == l for s, l in locked):
            warnings.append(f"Lock {pair[0]}-{pair[1]} was dropped: one of them is already locked to someone else.")
        else:
            locked.append(pair)
    chosen = sorted(solver.solve(scores, locked, settings["solver_time_limit_seconds"]),
                    key=lambda pair: natural(pair[0]))
    pairs = []
    for s_id, l_id in chosen:
        e = evaluations[(s_id, l_id)]
        notes = [f"to resolve: {text}" for text in e["uncertain"]]
        notes += [f"staff check ({r['owner']}): {r['label'].removeprefix('Staff check: ')}"
                  for r in e["rules"] if r["result"] == "staff"]
        for pid in (s_id, l_id):
            notes += [f"{pid}: {flag}" for flag in people[pid].flags if "gender is blank" not in flag]
        pairs.append({"student": s_id, "local": l_id, "score": e["score"], "score_min": e["score_min"],
                      "score_max": e["score_max"], "uncertain": bool(e["uncertain"]), "grade": scoring.grade(e["score"]),
                      "grade_max": scoring.grade(e["score_max"]), "criteria": e["criteria"], "rules": e["rules"],
                      "notes": notes, "locked": (s_id, l_id) in locked})
    matched_s, matched_l = {p["student"] for p in pairs}, {p["local"] for p in pairs}
    groups = solver.competing_groups(list(scores), chosen, locked)
    unmatched_s = []
    for s in students:
        if s.id in matched_s:
            continue
        if not any(pair[0] == s.id for pair in scores):
            counts = sorted(failures[s.id].items(), key=lambda kv: -kv[1])
            reason = (f"no allowed partner among {len(locals_)} locals; failed checks: "
                      + ", ".join(f"{CHECK_NAMES[k]} {v}" for k, v in counts))
        else:
            group, options = next(g for g in groups if s.id in g[0])
            taken = sorted((l for l in options if any(p == (x, l) for x in matched_s for p in locked)), key=natural)
            reason = (f"competes with {', '.join(sorted(group - {s.id}, key=natural)) or 'no one'} for "
                      f"{', '.join(sorted(options, key=natural))}; these {len(group)} internationals have only "
                      f"{len(options)} allowed locals between them")
            if taken:
                reason += f" ({', '.join(taken)} locked to others)"
        unmatched_s.append({"id": s.id, "reason": reason})
    unmatched_l = [{"id": l.id, "reason": "no allowed partner under these rules"
                    if not any(pair[1] == l.id for pair in scores) else "allowed partners were all placed with others"}
                   for l in locals_ if l.id not in matched_l]
    summary = _summary(students, locals_, survey, pairs, scores, locked, unmatched_s, unmatched_l)
    distribution = {c: [sum(p["criteria"][c]["grade"] == g for p in pairs) for g in range(1, 6)] for c in scoring.CRITERIA}
    distribution["overall"] = [sum(p["grade"] == g for p in pairs) for g in range(1, 6)]
    means = {c: (sum(p["criteria"][c]["d"] for p in pairs) / len(pairs) if pairs else None) for c in scoring.CRITERIA}
    constraints = _constraints(settings, rule_list, pairs, people)
    result = {"iteration": iteration, "summary": summary, "pairs": pairs, "distribution": distribution,
              "means": means, "constraints": constraints, "warnings": warnings,
              "unmatched": {"internationals": unmatched_s, "locals": unmatched_l},
              "excluded": survey.excluded, "people": {pid: p.public() for pid, p in people.items()},
              "weights": scoring.weights(settings),
              "rules": [rulebook.to_dict(r) for r in rule_list]}
    result["result_csv"] = result_csv(pairs)
    result["settings_csv"] = scoring.settings_to_csv(settings)
    result["rules_csv"] = rulebook.rules_to_csv(rule_list)
    result["report"] = make_report(result, settings, rule_list, survey_text, survey_name, locked, forbidden)
    return result


def _summary(students, locals_, survey, pairs, scores, locked, unmatched_s, unmatched_l):
    values = [p["score"] for p in pairs]
    return {"internationals": len(students), "locals": len(locals_), "matched": len(pairs),
            "unmatched_internationals": len(unmatched_s), "unmatched_locals": len(unmatched_l),
            "excluded": len(survey.excluded), "eligible_pairs": len(scores),
            "possible_pairs": len(students) * len(locals_),
            "lowest": min(values, default=None), "average": sum(values) / len(values) if values else None,
            "highest": max(values, default=None),
            "lowest_grade": scoring.grade(min(values)) if values else None,
            "average_grade": scoring.grade(sum(values) / len(values)) if values else None,
            "staff_checks": sum(any(r["result"] == "staff" for r in p["rules"]) for p in pairs),
            "to_resolve": sum(p["uncertain"] for p in pairs), "locked": len(locked)}


def _constraints(settings, rule_list, pairs, people):
    in_pairs = {pid for p in pairs for pid in (p["student"], p["local"])}
    wishes = sum(people[p["student"]].wanted_gender != "any" or people[p["local"]].wanted_gender != "any" for p in pairs)
    pets = sum(people[p["student"]].has_pets or people[p["local"]].has_pets for p in pairs)
    active = [r for r in rule_list if r.id in in_pairs and r.kind != "staff_check"]
    results = [r for p in pairs for r in p["rules"]]
    levels = [p["criteria"]["language"]["detail"] for p in pairs]
    return [
        {"name": "Gender wishes", "enabled": settings["enforce_gender"], "status": "ok",
         "text": f"respected in all pairs; {wishes} pairs include a specific gender wish"},
        {"name": "Pets", "enabled": settings["enforce_pets"], "status": "ok",
         "text": f"no pet conflicts; {pets} pairs include a pet owner"},
        {"name": "Shared language", "enabled": settings["require_shared_language"], "status": "ok",
         "text": f"every pair shares a language; {sum('native' in t for t in levels)} at native level, "
                 f"{sum(', good' in t for t in levels)} good, {sum(', basic' in t for t in levels)} basic"},
        {"name": "Must-have rules", "enabled": True,
         "status": "warn" if any(r["result"] == "to resolve" for r in results) else "ok",
         "text": f"{sum(r['result'] == 'met' for r in results)} of {len(active)} checkable rules met by the assigned "
                 f"partner; {sum(r['result'] == 'to resolve' for r in results)} to resolve (blank gender)"},
        {"name": "Staff checks", "enabled": True,
         "status": "warn" if any(r["result"] == "staff" for r in results) else "ok",
         "text": f"{sum(r['result'] == 'staff' for r in results)} wishes in this solution need a manual check"},
    ]


def result_csv(pairs) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(RESULT_COLUMNS)
    for p in pairs:
        row = [p["student"], p["local"], f"{p['score']:.4f}", f"{p['score_min']:.4f}", f"{p['score_max']:.4f}",
               p["grade"], scoring.GRADES[p["grade"]]]
        for c in scoring.CRITERIA:
            row += [f"{p['criteria'][c]['d']:.4f}", p["criteria"][c]["grade"]]
        writer.writerow(row + ["yes" if p["locked"] else "", " | ".join(p["notes"])])
    return out.getvalue()


def _grade(d):
    return f"{d:.2f} (grade {scoring.grade(d)}, {scoring.GRADES[scoring.grade(d)]})"


def make_report(result, settings, rule_list, survey_text, survey_name, locked, forbidden) -> str:
    s = result["summary"]
    lines = ["PERFECTMATCH LFP26 - MATCHING REPORT", "Status: SUCCESS",
             f"Iteration: {result['iteration']}",
             f"Run time (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
             f"Survey file: {survey_name}",
             f"Survey SHA-256 (processed text): {hashlib.sha256(survey_text.encode('utf-8')).hexdigest()}", "",
             "SUMMARY",
             f"Internationals: {s['internationals']}; locals: {s['locals']}; excluded rows: {s['excluded']}"]
    if s["unmatched_internationals"]:
        lines.append(f"ATTENTION: {s['unmatched_internationals']} of {s['internationals']} internationals could not "
                     "be matched under these rules. See UNMATCHED.")
    elif s["internationals"]:
        lines.append(f"All {s['internationals']} internationals are matched.")
    lines += [f"Selected pairs: {s['matched']}; unmatched locals: {s['unmatched_locals']}",
              f"Allowed pairs: {s['eligible_pairs']} of {s['possible_pairs']}"]
    if result["pairs"]:
        lines.append(f"Overall desirability lowest / average / highest: {_grade(s['lowest'])} / "
                     f"{_grade(s['average'])} / {_grade(s['highest'])}")
    lines += ["", "CRITERIA ACHIEVEMENT (number of pairs per grade 1-5; mean desirability)"]
    for c, label in [*scoring.CRITERIA.items(), ("overall", "Overall")]:
        mean = result["means"].get(c)
        lines.append(f"  {label:<12} " + "  ".join(f"{g}:{n:>2}" for g, n in zip(range(1, 6), result["distribution"][c]))
                     + (f"   mean {mean:.2f}" if mean is not None else ""))
    lines += ["", "SELECTED PAIRS (desirability; grades: languages / profile / age / hobbies)"]
    for p in result["pairs"]:
        score = (f"{p['score']:.2f} (min {p['score_min']:.2f}, max {p['score_max']:.2f})" if p["uncertain"]
                 else f"{p['score']:.2f}")
        grades = " / ".join(str(p["criteria"][c]["grade"]) for c in scoring.CRITERIA)
        lines.append(f"  {p['student']:<6} - {p['local']:<6} {score:<32} grade {p['grade']}  [{grades}]"
                     + ("  LOCKED" if p["locked"] else ""))
    lines += ["", "UNMATCHED"]
    lines += [f"  {u['id']}: {u['reason']}" for u in result["unmatched"]["internationals"]]
    if result["unmatched"]["internationals"]:
        lines.append("  To match every international: relax a must-have, gender or pets rule for someone named "
                     "above, remove a lock or forbidden pair, or add a suitable local.")
    lines += [f"  {u['id']}: {u['reason']}" for u in result["unmatched"]["locals"]] or ["  None."]
    lines += ["", "EXCLUDED ROWS (not analysed)"]
    lines += [f"  {e['id']} (line {e['line']}): {'; '.join(e['reasons'])}" for e in result["excluded"]] or ["  None."]
    notes = [f"  {p['student']}-{p['local']}: {n}" for p in result["pairs"] for n in p["notes"]]
    lines += ["", "REVIEW NOTES"] + (notes or ["  None."])
    lines += [f"  {w}" for w in result["warnings"]]
    w = scoring.weights(settings)
    lines += ["", "SETTINGS USED",
              "Weights 1-10 (exponent share): " + "; ".join(
                  f"{scoring.CRITERIA[c].lower()} {settings[f'weight_{c}']} ({w[c]:.0%})" for c in scoring.CRITERIA),
              f"Languages: level {settings['language_acceptable']:g} just acceptable, "
              f"{settings['language_satisfactory']:g} fully satisfactory (1 basic, 2 good, 3 native)",
              f"Hobbies: {settings['hobbies_acceptable']:g} shared categories just acceptable, "
              f"{settings['hobbies_satisfactory']:g} fully satisfactory",
              f"Age wishes: {settings['age_satisfactory']:.0%} outside the wished range fully satisfactory, "
              f"{settings['age_tolerance']:.0%} just acceptable, beyond insufficient",
              f"Profile wishes: a missed wish counts {settings['profile_missed']:.0%}"]
    for key in ("enforce_gender", "enforce_pets", "require_shared_language"):
        lines.append(f"{key}: {str(settings[key]).upper()}")
    lines += [f"Locked pairs: {', '.join(f'{a}-{b}' for a, b in locked) or 'none'}",
              f"Forbidden pairs: {', '.join(f'{a}-{b}' for a, b in sorted(forbidden)) or 'none'}",
              "", "MUST-HAVE RULES"]
    lines += [f"  {r.id}: {r.describe()} [{r.status}]" for r in sorted(rule_list, key=lambda r: natural(r.id))] or ["  None."]
    lines += ["", "HOW TO READ THIS RUN",
              "Each person appears in at most one pair. The solver first matches as many internationals as",
              "possible, then raises the lowest pair desirability, then the total.",
              "Each criterion is a Harrington desirability: 0.50 is just acceptable, 0.80 fully satisfactory.",
              "Grades: 1 insufficient (<0.50), 2 barely satisfying, 3 ok/solid (0.65+), 4 very good (0.80+),",
              "5 perfect (0.90+). Overall desirability is the weighted geometric mean of the criteria.",
              "A blank own gender is reported as min-max: 0 if it does not fit the partner's wish; the",
              "solver uses the average. Programme staff should review every pair before confirming it."]
    return "\n".join(lines) + "\n"
