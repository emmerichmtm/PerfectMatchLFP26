"""Write examples/survey_example.csv: a fictional survey export in the real two-heading-row format.

No real participants. Headings and fixed statements are the survey form's own wording.
Run: python tools/make_example_survey.py
"""
HEADINGS = ['', 'My status', 'Have you participated in the Local Friendship Programme before?', 'The Programme', 'The Principles', 'By submitting the data, I agree to the processing of the information provided in this form for the purpose of matching local friends and students. (Data Protection Act and Regulation)', 'All participants of the Local Freindship Programme are responsible for their own activities and insurance, and are not liable to each other for any damage caused by each other. The University of Jyväskylä is not liable for any damage caused by the activities of the Local Friendship Programme.', '', 'My/Our Profile', '', '', '', '', '', '', '', '', '', '', "Your future friend's profile", '', '', '', '', '', '', '', '', '', '', 'Please, name the language(s) you can speak and add your proficiency level in each:', '', '', '', 'Please, name the language(s) you can speak and add your proficiency level in each: Open text answers', '', 'Languages and levels of your associates:', 'Hobbies and interests I/we appreaciate (Original)', '', '', '', '', '', '', '', '', '', '', '', '', '', 'Hobbies and interests I/we appreaciate (Original) Open text answers', 'My gender identity', "Friend's gender identity", 'My age\xa0This is asked to help matching in cases when age is relevant.', "Friend's age . \xa0Note1: This is asked to help match people where age is the most important matching criteria for you. Note 2: By selecting a narrow age scale, you are strongly limiting your chances of finding a friend. We cannot guarantee that there will be a friend available to match your age request.\xa0 ", '', '', '', '', '', '', '', '', '', '', 'Pet allergies and your preferences', '', '', '', '', 'Pet allergies and your preferences Open text answers', '', 'Please, tell us what motivates you to participate in the programme.', 'Things you appreciate in a friend. Please, take into account the Principlces of the programme.', 'Additional information Please provide any additional information that can assist us in matching you with a student/local friend.', 'The must match criteria', 'Specs for your criteria: Fields of studies', 'Specs for your criteria: Language', 'Specs for your criteria:\xa0Hobbies and interests', 'Specs for your criteria: Profile type', 'Specs for your criteria: Gender identity', 'Specs for your criteria:\xa0Age', 'Specs for your criteria: Other']
OPTIONS = ['ID', '-', '-', '-', '-', '-', '-', 'Country of Origin\xa0', 'one person', 'a couple', 'a pair of friends', 'a small group of friends (3-4 people)', 'a family with children under 5 years', 'a family with children of 5 to 15 years', 'a family with children over 15 years', 'an empty nester(s) (i.e. an individual or a couple whose children have grown up and moved away)', 'a Finnish JYU degree student interested in becoming a local friend', 'a native Finn', 'someone who is not originally from Finland but has made Finland their new home', 'one person', 'a couple', 'a pair of friends', 'a small group of friends (3-4 people)', 'a family with children under 5 years', 'a family with children of 5 to 15 years', 'a family with children over 15 years', 'an empty nester(s) (i.e. an individual or a couple whose children have grown up and moved away)', 'a Finnish JYU degree student interested in becoming a local friend', 'a native Finn', 'someone who is not originally from Finland but has made Finland their new home', 'English', 'Suomi', 'Language 1:', 'Language 2:', 'Language 1: Open text answers', 'Language 2: Open text answers', '-', 'Sports and Outdoor Activities |\xa0This category includes activities such as basketball, volleyball, football, swimming, hiking, mountain-climbing, skiing, snowboarding, canoeing, rowing, and cycling.', 'Music enjoying | This category includes activities such as listening to music, going to concerts.', 'Music playing | This category includes activities such as singing, playing an instrument(s) (piano, guitar, flute, cello, base etc.); which one(s)', 'Reading and Writing | This category includes activities such as literature, writing stories, blogging,', 'Cooking and Baking | This category includes activities such as cooking a particular type of a cuisine, wine tasting, making cocktails/mocktails, baking and decorating cakes, and trying new cuisines.', 'Nature and Outdoor Exploration | This category includes activities such as berry or mushroom picking, hiking/trekking, tenting, having a picnic, roasting marshmallows on a campfire, fishing, hunting, exploring nature, and visiting natural attractions.', 'Travelling and adventure | This category includes activities such as visiting new places and exploring new (sub)cultures.', 'Socializing and Entertainment | This category includes activities such as going to cafes or pubs, watching movies and shows together, playing video/board games, partying and dancing.', 'Personal Development and Learning | This category includes activities such as discussing science and technology, society, history, philosophy, and recent news.', 'Animal and Nature-Related Interests | This category includes activities such as liking and being interested in pets (particularly cats and dogs) and/or wild animals, plants, or home gardening.', 'Handicrafts | This category includes activities such as making DIY crafts, jewelry, crochet/knitting, wood-work, and forging workshops.', 'Visual Art | This category includes activities such as drawing, painting, photography, architecture, and illustration and design.', 'Cultural heritage | This category includes activities for sharing and exploring cultural features and traditions,such as manners, communication, history, traditional festivals and social behaviour. In Finland, for example, this includes sauna and summerhouse culture.', 'Other:', 'Other: Open text answers', '-', '-', '-', 'All ages are fine ', '18 - 25', '26 - 30', '31 - 35', '36 - 40', '41 - 45', '46 - 50', '51- 55', '56 - 60', '61 - 65', 'Over 65', 'I/we do have a pet(s):', "I/we don't have any pets.", 'All pets are welcome.', 'I/We do not want any pets to be part of the visits.', 'I/we do not want a particlular kind of pet(s) to be part of the visits, due to allergies or other reasons (e.g. dog(s)):', 'I/we do have a pet(s): Open text answers', 'I/we do not want a particlular kind of pet(s) to be part of the visits, due to allergies or other reasons (e.g. dog(s)): Open text answers', '-', '-', '-', '-', 'Please specify:', 'Please specify:', 'Please specify:', 'Please specify:', 'Please specify:', 'Please specify:', 'Please specify:']
STATUS = {'local': 'I am a local resident applying to become a local friend for an\xa0international JYU\xa0degree student(s).', 'international': 'I am a international JYU degree student applying to become a student friend for a local person(s).'}
STATEMENTS = ['I am familiar with the\xa0Local Friendship Programme.', 'I appreciate the principles of the Local Friendship Programme, which are all about inclusivity, respect and understanding.', 'I agree.', 'I agree.']

import csv
from pathlib import Path
import random

OUT = Path(__file__).resolve().parents[1] / "examples" / "survey_example.csv"


def columns(prefix, label=None):
    """Indices of the columns under the question starting with prefix (optionally one option)."""
    start = next(i for i, q in enumerate(HEADINGS) if q.replace("\xa0", " ").lower().startswith(prefix.lower()))
    end = next((i for i in range(start + 1, len(HEADINGS)) if HEADINGS[i]), len(HEADINGS))
    found = list(range(start, end))
    if label is not None:
        found = [i for i in found if OPTIONS[i].lower().startswith(label.lower())]
    return found


HOBBIES = [i for i in columns("Hobbies and interests I/we appreaciate (Original)") if not OPTIONS[i].startswith("Other")]
MY_PROFILE, FRIEND_PROFILE = columns("My/Our Profile"), columns("Your future friend's profile")
FRIEND_AGE, PETS = columns("Friend's age"), columns("Pet allergies and your preferences")
LANGS = columns("Please, name the language(s)")
LANG_NAMES = columns("Please, name the language(s) you can speak and add your proficiency level in each: Open text answers")
AGES = ["18 - 20", "21 - 25", "26 - 30", "31 - 35", "36 - 40", "41 - 45", "46 - 50", "56 - 60", "61 - 65", "Over 65"]
SPECS = {name: columns(f"Specs for your criteria: {name}") or columns(f"Specs for your criteria:\xa0{name}")
         for name in ("Fields of studies", "Language", "Hobbies and interests", "Profile type", "Gender identity", "Age", "Other")}
COUNTRIES = ["India", "Iran", "Japan", "Nigeria", "Vietnam", "Brazil", "Germany", "Nepal", "China", "Ghana",
             "Mexico", "Bangladesh", "Indonesia", "Ukraine", "Kenya", "Peru", "Turkey", "Korea", "Spain", "Egypt"]
NATIVE = {"India": "Hindi", "Iran": "Persian", "Japan": "Japanese", "Nigeria": "Yoruba", "Vietnam": "Vietnamese",
          "Brazil": "Portuguese", "Germany": "German", "Nepal": "Nepali", "China": "Chinese", "Ghana": "Twi",
          "Mexico": "Spanish", "Bangladesh": "Bengali", "Indonesia": "Indonesian", "Ukraine": "Ukrainian",
          "Kenya": "Swahili", "Peru": "Spanish", "Turkey": "Turkish", "Korea": "Korean", "Spain": "Spanish",
          "Egypt": "Arabic"}
# (criterion, specification) - invented wording in the style of real answers
STUDENT_MUSTS = {2: ("Gender identity", "A female friend, please"), 5: ("Language", "My friend must speak English well enough for a real conversation"),
                 7: ("Hobbies and interests", "Sports and nature"), 9: ("Profile type", "A family with a child aged 6-12"),
                 11: ("Language", "Finnish, native level - I want to practise"), 14: ("Other", "Hobbies and what I appreciate in a friend matter most"),
                 16: ("Profile type", "Someone with a university degree"), 18: ("Gender identity", "")}
LOCAL_MUSTS = {1: ("Language", "German or Spanish"), 3: ("Age category", "20-30, close to my own age"),
               5: ("Other", "Someone from Japan would be lovely"), 8: ("Hobbies and interests", "Cooking or baking together"),
               10: ("Other", "No cat owners - I am allergic"), 13: ("Language", "French"),
               15: ("Gender identity", "Women only"), 19: ("Other", "Not a student from my own department"),
               22: ("Hobbies and interests", "Some shared interests"), 25: ("Language", "Any common language is fine")}


def person(rnd, number, international):
    row = [""] * len(HEADINGS)
    side = "international" if international else "local"
    row[0] = f"{'S' if international else 'L'}{number}"
    row[columns("My status")[0]] = STATUS[side]
    row[columns("Have you participated")[0]] = rnd.choice(["No", "No", "Yes", ""]) if international else ""
    for i, statement in zip([columns(q)[0] for q in ("The Programme", "The Principles", "By submitting", "All participants")], STATEMENTS):
        row[i] = statement
    row[OPTIONS.index("Country of Origin\xa0")] = COUNTRIES[number - 1] if international else rnd.choice(["Finland", "Suomi"])
    tick = lambda cols: [row.__setitem__(i, OPTIONS[i]) for i in cols]
    own = [MY_PROFILE[0]] if rnd.random() < 0.8 else [rnd.choice(MY_PROFILE[1:8])]
    if not international:
        own += [MY_PROFILE[9]] + ([MY_PROFILE[8]] if rnd.random() < 0.35 else [])
    tick(own)
    tick(rnd.sample(FRIEND_PROFILE[:9], rnd.randint(2, 6)) + [FRIEND_PROFILE[0]])
    row[LANGS[0]] = rnd.choice(["Native/very good", "Native/very good", "Good"] + (["Basic"] if number == 4 else []))
    row[LANGS[1]] = "Native/very good" if not international else rnd.choice(["Basic"] * 6 + ["Good"])
    if international:
        row[LANG_NAMES[0]], row[LANGS[2]] = NATIVE[COUNTRIES[number - 1]], "Native/very good"
    elif rnd.random() < 0.7:
        row[LANG_NAMES[0]] = rnd.choice(["Swedish", "German", "Spanish", "French", "Japanese"])
        row[LANGS[2]] = rnd.choice(["Basic", "Basic", "Good"])
    tick(rnd.sample(HOBBIES, rnd.randint(3, 10)))
    row[columns("My gender identity")[0]] = "" if number in ((4, 17) if international else (6, 21, 26)) else rnd.choice(["Female"] * 3 + ["Male"] * 2)
    row[columns("Friend's gender identity")[0]] = rnd.choice(["All are fine"] * 4 + ["Female"])
    age = rnd.randint(1, 5) if international else rnd.randint(1, 9)
    row[columns("My age")[0]] = AGES[age]
    if rnd.random() < 0.35:
        tick([FRIEND_AGE[0]])
    else:
        first = max(1, min(age, 7) - rnd.randint(0, 1))
        tick(FRIEND_AGE[first:first + rnd.randint(1, 4)])
    pets = rnd.random()
    if pets < 0.25 and not (international and number % 3):
        tick([PETS[0]])
        row[columns("Pet allergies and your preferences Open text answers")[0]] = rnd.choice(["a cat", "2 dogs", "Cat", "a small dog"])
    elif pets < 0.45:
        tick([PETS[3]])
    else:
        tick([PETS[1], PETS[2]] if rnd.random() < 0.5 else [PETS[2]])
    row[columns("Please, tell us what motivates")[0]] = rnd.choice(["Meeting new people", "Learning about Finland", "Sharing my culture", "Practising languages"])
    row[columns("Things you appreciate")[0]] = rnd.choice(["Honesty and humour", "Open mind", "Reliability", ""])
    musts = STUDENT_MUSTS if international else LOCAL_MUSTS
    if number in musts:
        criterion, text = musts[number]
        row[columns("The must match criteria")[0]] = criterion
        key = {"Age category": "Age"}.get(criterion, criterion)
        row[SPECS[key][0]] = text
        if criterion == "Gender identity":
            row[columns("Friend's gender identity")[0]] = "Female"
    return row


def main():
    rnd = random.Random(2026)
    rows = [HEADINGS, OPTIONS] + [person(rnd, n, True) for n in range(1, 21)] + [person(rnd, n, False) for n in range(1, 29)]
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="cp1252", newline="") as f:
        csv.writer(f, delimiter=";", lineterminator="\r\n").writerows(rows)
    print(f"Wrote {OUT} ({len(rows) - 2} fictional participants)")


if __name__ == "__main__":
    main()
