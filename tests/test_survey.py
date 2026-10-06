import unittest

from helpers import column, example_rows, example_text, to_text
from survey import decode, profile_name, read_survey


class SurveyReaderTests(unittest.TestCase):
    def test_example_export_is_read(self):
        survey = read_survey(example_text())
        self.assertEqual((survey.rows, len(survey.internationals), len(survey.locals)), (48, 20, 28))
        self.assertEqual(survey.excluded, [])
        self.assertEqual(len(survey.options["hobbies"]), 13)
        self.assertIn("Family, children 5-15", survey.options["profiles"])
        s1 = survey.by_id()["S1"]
        self.assertEqual(s1.side, "international")
        self.assertEqual(s1.languages["english"] >= 2 and s1.languages["finnish"] >= 1, True)
        self.assertTrue(s1.hobbies)
        self.assertIn("own gender is blank - to be resolved", survey.by_id()["S4"].flags)

    def test_code_page_and_utf8_and_comma_exports_give_the_same_people(self):
        rows = example_rows()
        rows[3][column(rows, "Additional information")] = "Jyväskylä café"
        cp1252 = to_text(rows).encode("cp1252")
        utf8_comma = ("﻿" + to_text(rows, ",")).encode("utf-8")
        a, b = read_survey(decode(cp1252)), read_survey(decode(utf8_comma))
        self.assertEqual([p.public() for p in a.people], [p.public() for p in b.people])
        self.assertEqual(a.by_id()["S2"].additional, "Jyväskylä café")

    def test_missing_question_is_named(self):
        rows = example_rows()
        rows[0][column(rows, "My gender identity")] = "Something else"
        with self.assertRaisesRegex(ValueError, "missing these questions: gender"):
            read_survey(to_text(rows))
        with self.assertRaisesRegex(ValueError, "My status"):
            read_survey("id,name\n1,2\n")

    def test_unclear_and_incomplete_rows_are_excluded_with_reasons(self):
        rows = example_rows()
        rows[2][column(rows, "The Principles")] = ""                       # S1: no consent
        rows[3][column(rows, "My status")] = "Visitor"                     # S2: unclear side
        rows[4][0] = "S4"                                                  # S3 takes S4's ID
        for question in ("My/Our Profile", "Your future friend's profile", "Hobbies and interests I/we"):
            start = column(rows, question)
            end = next(i for i in range(start + 1, len(rows[0])) if rows[0][i])
            for i in range(start, end):
                rows[7][i] = ""                                            # S6: 3 key answers missing
        rows.append(rows[10][:-3])                                         # damaged row
        survey = read_survey(to_text(rows))
        reasons = {e["id"]: " ".join(e["reasons"]) for e in survey.excluded}
        self.assertIn("consent", reasons["S1"])
        self.assertIn("status", reasons["S2"])
        self.assertIn("more than once", reasons["S4"])
        self.assertIn("3 key answers missing", reasons["S6"])
        self.assertIn("cells instead of", reasons["S9"])
        self.assertNotIn("S1", survey.by_id())
        self.assertEqual(len(read_survey(to_text(rows), max_missing=3).by_id()["S6"].missing), 3)

    def test_profile_options_are_mapped(self):
        self.assertEqual(profile_name("an empty nester(s) (i.e. an individual or a couple whose children have moved)"),
                         "Empty nester")
        self.assertEqual(profile_name("a couple"), "Couple")
        self.assertEqual(profile_name("a family with children of 5 to 15 years"), "Family, children 5-15")


if __name__ == "__main__":
    unittest.main()
