import math
import unittest

from helpers import person
import scoring


class DesirabilityTests(unittest.TestCase):
    def test_harrington_anchors_and_direction(self):
        self.assertAlmostEqual(scoring.harrington(1, 1, 2), 0.5)
        self.assertAlmostEqual(scoring.harrington(2, 1, 2), 0.8)
        self.assertGreater(scoring.harrington(3, 1, 2), 0.9)
        self.assertLess(scoring.harrington(0, 1, 2), 0.5)
        # Smaller is better for the age gap: anchors given in reverse.
        self.assertAlmostEqual(scoring.harrington(0.25, 0.25, 0.10), 0.5)
        self.assertAlmostEqual(scoring.harrington(0.10, 0.25, 0.10), 0.8)
        self.assertLess(scoring.harrington(0.4, 0.25, 0.10), 0.5)
        self.assertEqual(scoring.harrington(1e9, 1, 2), math.exp(-math.exp(-30)))

    def test_grades(self):
        self.assertEqual([scoring.grade(d) for d in (0.49, 0.5, 0.64, 0.65, 0.7999999, 0.8, 0.9, 1)], [1, 2, 2, 3, 4, 4, 5, 5])

    def test_age_gap_uses_overlap_then_midpoint(self):
        self.assertEqual(scoring.age_gap((26, 30), [(18, 25), (26, 30)]), 0)
        self.assertEqual(scoring.age_gap((31, 35), []), 0)
        self.assertAlmostEqual(scoring.age_gap((31, 35), [(18, 30)]), 3 / 30)
        self.assertAlmostEqual(scoring.age_gap((18, 20), [(26, 30)]), 7 / 26)
        settings = scoring.default_settings()
        self.assertEqual(scoring.age_desirability((26, 30), [(26, 30)], settings), 1.0)
        self.assertEqual(scoring.grade(scoring.age_desirability((41, 45), [(18, 30)], settings)), 1)

    def test_criteria_and_weighted_product(self):
        settings = scoring.default_settings()
        s = person("S1", wanted_profile=["Native Finn"], languages={"english": 2, "finnish": 1},
                   hobbies=["Cooking and Baking", "Visual Art", "Handicrafts"])
        l = person("L1", "local", profile=["One person"], languages={"english": 3, "finnish": 3},
                   hobbies=["Cooking and Baking", "Visual Art"], wanted_age=[(41, 45)])
        result = scoring.criteria(s, l, settings)
        self.assertAlmostEqual(result["language"]["d"], 0.8)               # English, good
        self.assertAlmostEqual(result["hobbies"]["d"], 0.5)                # 2 shared
        self.assertEqual(result["profile"]["sides"], {"student": 0.25, "local": 1.0})
        self.assertAlmostEqual(result["profile"]["d"], 0.5)
        self.assertEqual(result["profile"]["side_grades"]["student"], 1)
        w = scoring.weights(settings)
        self.assertAlmostEqual(sum(w.values()), 1)
        self.assertEqual(w["language"], 0.4)
        expected = math.prod(result[c]["d"] ** w[c] for c in scoring.CRITERIA)
        self.assertAlmostEqual(scoring.overall(result, settings), expected)

    def test_settings_csv_round_trip_and_validation(self):
        settings = scoring.default_settings()
        settings.update(weight_hobbies=7, age_tolerance=0.3, enforce_pets=False)
        self.assertEqual(scoring.settings_from_csv(scoring.settings_to_csv(settings)), settings)
        self.assertEqual(scoring.settings_from_csv("setting;value\nweight_age;7\nage_tolerance;0,3\n")["age_tolerance"], 0.3)
        for bad in ({"weight_age": 0}, {"weight_age": 11}, {"weight_age": 2.5}, {"enforce_pets": "maybe"},
                    {"language_satisfactory": 1}, {"age_satisfactory": 0.3}, {"typo": 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                scoring.validate_settings(bad)
        with self.assertRaisesRegex(ValueError, "more than once"):
            scoring.settings_from_csv("setting,value\nweight_age,3\nweight_age,4\n")

    def test_gender_and_pets(self):
        self.assertTrue(scoring.gender_check("any", ""))
        self.assertIsNone(scoring.gender_check("female", ""))
        self.assertFalse(scoring.gender_check("female", "male"))
        owner = person("L1", "local", has_pets=True, pet_kinds=["cat"])
        self.assertIn("does not want", scoring.pets_conflict(person(unwanted_pet_kinds=["cat"]), owner))
        self.assertIn("does not want pets", scoring.pets_conflict(person(no_pets_wanted=True), owner))
        self.assertEqual(scoring.pets_conflict(person(unwanted_pet_kinds=["dog"]), owner), "")


if __name__ == "__main__":
    unittest.main()
