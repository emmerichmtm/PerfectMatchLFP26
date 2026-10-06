import unittest

from helpers import person
import rules

OPTIONS = {"hobbies": ["Sports and Outdoor Activities", "Music enjoying", "Reading and Writing", "Cooking and Baking",
                       "Nature and Outdoor Exploration", "Travelling and adventure", "Cultural heritage"],
           "profiles": ["One person", "Couple", "Family, children 5-15"], "languages": ["english", "finnish", "german"]}


def propose(criterion, text, **fields):
    return [(r.kind, r.values, r.level, r.count) for r in
            rules.propose_rules(person(must_criterion=criterion, must_text=text, **fields), OPTIONS)]


class ProposalTests(unittest.TestCase):
    # Invented wording in the style of survey answers.
    def test_gender(self):
        self.assertEqual(propose("Gender identity", "Only women, please"), [("partner_gender", ["female"], 1, 1)])
        self.assertEqual(propose("Gender identity", "No men"), [("partner_gender", ["female"], 1, 1)])
        self.assertEqual(propose("Gender identity", "A man would be best"), [("partner_gender", ["male"], 1, 1)])
        self.assertEqual(propose("Gender identity", "", wanted_gender="female"), [("partner_gender", ["female"], 1, 1)])

    def test_language(self):
        self.assertEqual(propose("Language", "German or Spanish"), [("partner_language", ["german", "spanish"], 1, 1)])
        self.assertEqual(propose("Language", "Suomi, native level"), [("partner_language", ["finnish"], 3, 1)])
        self.assertEqual(propose("Language", "Able to hold a conversation in English"), [("partner_language", ["english"], 2, 1)])
        self.assertEqual(propose("Language", "English for now, I am learning Finnish but it is not very good"),
                         [("partner_language", ["english"], 1, 1)])
        self.assertEqual(propose("Language", "We should share a mother tongue"), [("shared_language", [], 3, 1)])
        self.assertEqual(propose("Language", "Some common language"), [("shared_language", [], 1, 1)])

    def test_hobbies(self):
        self.assertEqual(propose("Hobbies and interests", "Cooking, travelling, sauna"),
                         [("partner_hobby", ["Cooking and Baking", "Travelling and adventure"], 1, 1)])
        self.assertEqual(propose("Hobbies and interests", "Cultural heritage, Reading and Writing"),
                         [("partner_hobby", ["Reading and Writing", "Cultural heritage"], 1, 1)])
        self.assertEqual(propose("Hobbies and interests", "Some common interests"), [("shared_hobbies", [], 1, 1)])

    def test_profile_age_fields_and_other(self):
        self.assertEqual(propose("Profile type", "Family with kids aged 8 and 11"), [("partner_profile", ["Family, children 5-15"], 1, 1)])
        self.assertEqual(propose("Profile type", "", wanted_profile=["Couple"]), [("partner_profile", ["Couple"], 1, 1)])
        self.assertEqual(propose("Profile type", "Someone with a university degree"), [("staff_check", [], 1, 1)])
        self.assertEqual(propose("Age category", "Between 20-30 please"), [("partner_age", ["20-30"], 1, 1)])
        self.assertEqual(propose("Age category", "The range I chose", wanted_age=[(18, 25), (26, 30)]),
                         [("partner_age", ["18-25", "26-30"], 1, 1)])
        self.assertEqual(propose("Fields of studies", "Physics"), [("staff_check", [], 1, 1)])
        self.assertEqual(propose("Other", "Someone from Korea"), [("partner_country", ["Korea"], 1, 1)])
        self.assertEqual(propose("Other", "No cat owners, allergy"), [("partner_no_pet", ["cat"], 1, 1)])
        self.assertEqual(propose("Other", "Shared hobbies and what I appreciate in a friend"),
                         [("shared_hobbies", [], 1, 1), ("staff_check", [], 1, 1)])
        self.assertEqual(propose("", "anything"), [])


class CheckTests(unittest.TestCase):
    def test_checks(self):
        me = person("L1", "local", hobbies=["Cooking and Baking", "Cultural heritage"], languages={"english": 3, "finnish": 3})
        partner = person("S1", gender="", languages={"english": 2, "german": 1}, hobbies=["Cultural heritage"],
                         country="Republic of Korea (South Korea)", has_pets=True, pet_kinds=["cat"], age=(21, 25))
        rule = lambda kind, values=(), **kw: rules.Rule("L1", kind, list(values), **kw)
        self.assertIsNone(rules.check(rule("partner_gender", ["female"]), me, partner))
        self.assertTrue(rules.check(rule("partner_language", ["German"]), me, partner))
        self.assertFalse(rules.check(rule("partner_language", ["english"], level=3), me, partner))
        self.assertTrue(rules.check(rule("shared_language", level=2), me, partner))
        self.assertTrue(rules.check(rule("partner_hobby", ["Cultural heritage", "Music enjoying"]), me, partner))
        self.assertFalse(rules.check(rule("partner_hobby", ["Cultural heritage", "Music enjoying"], count=2), me, partner))
        self.assertFalse(rules.check(rule("shared_hobbies", count=2), me, partner))
        self.assertTrue(rules.check(rule("partner_country", ["Korea"]), me, partner))
        self.assertFalse(rules.check(rule("partner_no_pet", ["cat"]), me, partner))
        self.assertTrue(rules.check(rule("partner_no_pet", ["dog"]), me, partner))
        self.assertFalse(rules.check(rule("partner_no_pet", ["any"]), me, partner))
        self.assertTrue(rules.check(rule("partner_age", ["18-25"]), me, partner))
        self.assertFalse(rules.check(rule("partner_age", ["26-30"]), me, partner))
        self.assertTrue(rules.check(rule("staff_check"), me, partner))

    def test_csv_round_trip_and_validation(self):
        original = [rules.Rule("S1", "partner_language", ["german", "spanish"], 2, 1, "confirmed", "note", 'German; "or" Spanish'),
                    rules.Rule("L2", "shared_hobbies", [], 1, 2)]
        loaded = rules.rules_from_csv(rules.rules_to_csv(original), {"S1", "L2"})
        self.assertEqual(loaded, original)
        with self.assertRaisesRegex(ValueError, "no participant"):
            rules.rules_from_csv(rules.rules_to_csv(original), {"S1"})
        with self.assertRaisesRegex(ValueError, "unknown kind"):
            rules.from_dict({"id": "S1", "kind": "favourite_colour"})
        with self.assertRaisesRegex(ValueError, "at least one value"):
            rules.from_dict({"id": "S1", "kind": "partner_country", "values": ""})


if __name__ == "__main__":
    unittest.main()
