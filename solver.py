"""Lexicographic one-to-one matching: most pairs, then the best lowest score, then the best total.

Every pair contains exactly one international, so the first stage matches as many internationals
as the rules allow. Locked pairs are forced into the solution.
"""
from __future__ import annotations

import pulp

TOLERANCE = 1e-7


def solve(scores: dict, locked=(), time_limit: int = 60) -> list:
    """scores maps (student_id, local_id) -> optimization score in [0, 1]; returns the chosen pairs."""
    if not scores:
        return []
    problem = pulp.LpProblem("matching", pulp.LpMaximize)
    # Numeric names avoid collisions when IDs contain characters PuLP would rewrite.
    choose = {pair: pulp.LpVariable(f"pair_{i}", cat="Binary") for i, pair in enumerate(sorted(scores))}
    for side in (0, 1):
        members = {}
        for pair, var in choose.items():
            members.setdefault(pair[side], []).append(var)
        for variables in members.values():
            problem += pulp.lpSum(variables) <= 1
    for pair in locked:
        problem += choose[pair] == 1

    def stage(label):
        problem.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit, gapRel=0))
        if problem.status != pulp.LpStatusOptimal or problem.sol_status != pulp.LpSolutionOptimal:
            raise RuntimeError(f"The solver could not finish '{label}' optimally. "
                               "Increase solver_time_limit_seconds and compute again.")

    count = pulp.lpSum(choose.values())
    problem.setObjective(count)
    stage("number of pairs")
    best = int(round(pulp.value(count) or 0))
    if best == 0:
        return []
    problem += count == best
    lowest = pulp.LpVariable("lowest_score", lowBound=0, upBound=1)
    for pair, var in choose.items():
        problem += lowest <= scores[pair] + (1 - var)
    problem.setObjective(lowest + 0)
    stage("lowest pair score")
    floor = min(scores[pair] for pair, var in choose.items() if var.value() > 0.5)
    for pair, var in choose.items():
        if scores[pair] < floor - TOLERANCE and pair not in locked:
            problem += var == 0
    problem.setObjective(pulp.lpSum(scores[pair] * var for pair, var in choose.items()))
    stage("total score")
    return sorted(pair for pair, var in choose.items() if var.value() > 0.5)


def competing_groups(pairs, chosen, locked=()) -> list:
    """For unmatched internationals with eligible partners: the group competing for too few locals.

    Following eligible locals and the internationals placed with them reaches only taken locals,
    because the selection has the maximum number of pairs. Each group therefore has fewer eligible
    locals than internationals (Hall's theorem). Locked internationals cannot move, so the search
    stops at them. Returns (internationals, locals) set pairs.
    """
    partners = {}
    for s, l in pairs:
        partners.setdefault(s, set()).add(l)
    taken_by = {l: s for s, l in chosen}
    fixed = {s for s, _ in locked}
    matched = set(taken_by.values())
    groups = []
    for root in partners:
        if root in matched:
            continue
        students, locals_, queue = {root}, set(), [root]
        while queue:
            for l in partners[queue.pop()] - locals_:
                locals_.add(l)
                if l not in taken_by:
                    raise RuntimeError("Internal check failed: the selected pairs are not a maximum matching.")
                if taken_by[l] not in students and taken_by[l] not in fixed:
                    students.add(taken_by[l])
                    queue.append(taken_by[l])
        for other in [g for g in groups if g[0] & students]:
            groups.remove(other)
            students |= other[0]
            locals_ |= other[1]
        groups.append((students, locals_))
    return groups
