import csv
import io
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import engine
from helpers import ROOT, example_text, person
import rules as rulebook
import scoring
import solver


def proposed():
    return engine.analyse(example_text(), scoring.default_settings())["rules"]


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = scoring.default_settings()
        cls.first = engine.compute(example_text(), cls.settings, None)

    def test_example_blocks_one_international_and_explains_it(self):
        s = self.first["summary"]
        self.assertEqual((s["internationals"], s["matched"], s["unmatched_internationals"]), (20, 19, 1))
        (unmatched,) = self.first["unmatched"]["internationals"]
        self.assertEqual(unmatched["id"], "S9")
        self.assertIn("own must-have 28", unmatched["reason"])
        self.assertIn("ATTENTION: 1 of 20 internationals", self.first["report"])

    def test_relaxing_the_rule_matches_every_international(self):
        rules = [dict(r, kind="staff_check", values=[]) if r["id"] == "S9" else r for r in proposed()]
        result = engine.compute(example_text(), self.settings, rules, iteration=2)
        self.assertEqual(result["summary"]["unmatched_internationals"], 0)
        self.assertIn("All 20 internationals are matched.", result["report"])
        self.assertIn("Iteration: 2", result["report"])
        rows = list(csv.DictReader(io.StringIO(result["result_csv"])))
        self.assertEqual(len(rows), 20)
        self.assertEqual(list(rows[0]), engine.RESULT_COLUMNS)
        self.assertTrue(any("staff check (S9)" in p for row in rows for p in [row["notes"]]))

    def test_every_pair_respects_hard_rules_and_must_haves(self):
        for p in self.first["pairs"]:
            self.assertTrue(all(r["result"] in ("met", "staff") for r in p["rules"]), p)
            self.assertGreaterEqual(p["score"], self.first["summary"]["lowest"])
            self.assertNotIn("no shared language", p["criteria"]["language"]["detail"])

    def test_locks_and_forbids(self):
        rules = proposed()
        free = next(pair for pair in self.first["pairs"])
        target = (free["student"], self.first["unmatched"]["locals"][0]["id"])
        evaluation = engine.evaluate(*[engine.load(example_text(), self.settings, rules)[1][x] for x in target],
                                     self.settings, {})
        result = engine.compute(example_text(), self.settings, rules, locks=[target] if evaluation["eligible"] else [],
                                forbids=[(free["student"], free["local"])])
        chosen = {(p["student"], p["local"]) for p in result["pairs"]}
        self.assertNotIn((free["student"], free["local"]), chosen)
        if evaluation["eligible"]:
            self.assertIn(target, chosen)
        dropped = engine.compute(example_text(), self.settings, rules, locks=[("S9", "L1")])
        self.assertIn("Lock S9-L1 was dropped", dropped["warnings"][0])

    def test_blank_gender_is_scored_as_min_max_average(self):
        s = person("S1", gender="")
        l = person("L1", "local", wanted_gender="female", languages={"english": 3, "finnish": 3})
        e = engine.evaluate(s, l, self.settings, {})
        self.assertTrue(e["eligible"])
        self.assertEqual(e["score_min"], 0)
        self.assertAlmostEqual(e["score"], e["score_max"] / 2)
        self.assertEqual(len(e["uncertain"]), 1)
        rule = {"L1": [rulebook.Rule("L1", "partner_gender", ["female"])]}
        self.assertEqual(engine.evaluate(s, person("L1", "local"), self.settings, rule)["score_min"], 0)
        self.assertEqual(engine.evaluate(person("S1"), l, self.settings, {})["score_min"],
                         engine.evaluate(person("S1"), l, self.settings, {})["score_max"])

    def test_switching_off_hard_rules(self):
        s = person("S1", wanted_gender="male", languages={"german": 3})
        l = person("L1", "local", gender="female", languages={"finnish": 3}, has_pets=True)
        self.assertEqual(set(engine.evaluate(s, l, self.settings, {})["failures"]), {"gender", "language"})
        relaxed = dict(self.settings, enforce_gender=False, require_shared_language=False)
        self.assertTrue(engine.evaluate(s, l, relaxed, {})["eligible"])

    def test_impact_counts_partners_meeting_each_rule(self):
        rules = proposed()
        counts = engine.impact(example_text(), self.settings, rules)
        by_id = {r["id"]: c for r, c in zip(rules, counts)}
        self.assertEqual(by_id["S9"], 0)
        self.assertIsNone(by_id["S16"])          # staff check

    def test_cli_writes_result_and_report(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "settings.csv").write_text(scoring.settings_to_csv(dict(self.settings, weight_age=9)), encoding="utf-8")
            (folder / "rules.csv").write_text(rulebook.rules_to_csv([rulebook.from_dict(r) for r in proposed() if r["id"] != "S9"]),
                                              encoding="utf-8")
            command = [sys.executable, str(ROOT / "run_matching.py"), "--survey", str(ROOT / "examples" / "survey_example.csv"),
                       "--settings", str(folder / "settings.csv"), "--rules", str(folder / "rules.csv"),
                       "--result", str(folder / "result.csv"), "--report", str(folder / "report.txt")]
            done = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("SUCCESS: 20 pairs", done.stdout)
            self.assertIn("age fit 9 (", (folder / "report.txt").read_text(encoding="utf-8"))
            bad = subprocess.run(command[:-2] + ["--report", str(folder / "rules.csv")], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)
            self.assertNotIn("Traceback", bad.stderr)


class SolverTests(unittest.TestCase):
    def test_lexicographic_order(self):
        # (S1,L1)=0.99 tempts a higher total, but a better lowest pair must win.
        scores = {("S1", "L1"): 0.99, ("S1", "L2"): 0.7, ("S2", "L1"): 0.7, ("S2", "L2"): 0.6}
        self.assertEqual(solver.solve(scores), [("S1", "L2"), ("S2", "L1")])
        self.assertEqual(solver.solve(scores, locked=[("S1", "L1")]), [("S1", "L1"), ("S2", "L2")])
        self.assertEqual(solver.solve({}), [])

    def test_competing_groups_have_fewer_locals_than_internationals(self):
        rnd = random.Random(7)
        for _ in range(8):
            scores = {(f"S{i}", f"L{j}"): rnd.random() for i in range(6) for j in range(5) if rnd.random() < 0.3}
            chosen = solver.solve(scores)
            stranded = {s for s, _ in scores} - {s for s, _ in chosen}
            groups = solver.competing_groups(list(scores), chosen)
            explained = [s for group, _ in groups for s in group]
            self.assertEqual(len(explained), len(set(explained)))
            self.assertLessEqual(stranded, set(explained))
            for group, options in groups:
                self.assertEqual({l for s, l in scores if s in group}, options)
                self.assertEqual(len(options), len(group) - len(group & stranded))


if __name__ == "__main__":
    unittest.main()
