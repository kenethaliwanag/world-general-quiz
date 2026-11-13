"""Build a large question bank from curated seed data.

`data/questions.json` holds the hand written questions. The CSV files under
`data/seeds/` hold verified facts, and the templates below turn each fact into
questions and each pair of comparable facts into a comparison question, so the
bank holds far more questions than a Part history can ever exhaust.

Everything is deterministic: the same seeds always produce the same IDs, which
keeps the question history meaningful across runs.
"""
import csv
from itertools import combinations
from pathlib import Path

from config import DATA_DIR

SEED_DIR = DATA_DIR / "seeds"


def _rows(name):
    with (SEED_DIR / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _slug(value):
    return "".join(character if character.isalnum() else "-" for character in str(value).lower()).strip("-")


def _question(qid, question, answer, category, difficulty):
    return {
        "id": qid,
        "question": question,
        "answer": answer,
        "category": category,
        "difficulty": difficulty,
    }


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pretty_number(value):
    number = _number(value)
    if number is None:
        return str(value)
    if number == int(number):
        return f"{int(number):,}"
    return f"{number:,}"


def _population(value):
    """A spoken population: small countries read better in thousands."""
    number = _number(value)
    if number is None:
        return str(value)
    if number < 1:
        thousands = number * 1000
        return f"{_pretty_number(round(thousands))} thousand"
    return f"{_pretty_number(number)} million"


def _measurement(unit):
    """The spoken form of a measurement unit."""
    return {
        "km": "kilometres",
        "m": "metres",
        "km²": "square kilometres",
    }.get(unit, unit)


def _with_kind(kind, name):
    """Name a feature the way it reads best: 'the island Cuba', but 'Caribbean Sea'."""
    if kind.lower() in name.lower():
        return name
    return f"the {kind} {name}"


def _unique_by(rows, key):
    """Keep the first row for each key so duplicate seed rows never double up."""
    seen = set()
    kept = []
    for row in rows:
        value = row[key]
        if value in seen:
            continue
        seen.add(value)
        kept.append(row)
    return kept


def _country_questions():
    countries = _rows("countries.csv")
    questions = []
    for row in countries:
        name = row["name"]
        key = _slug(name)
        templates = [
            ("cn-cap", "What is the capital of {name}?", row["capital"], "geography", "easy"),
            ("cn-con", "On which continent is {name} located?", row["continent"], "geography", "easy"),
            ("cn-cur", "Which currency is used in {name}?", row["currency"], "geography", "easy"),
            ("cn-ccd", "What is the three-letter ISO currency code of {name}?", row["currency_code"], "geography", "hard"),
            ("cn-lan", "What is the main language spoken in {name}?", row["language"], "culture", "easy"),
            ("cn-dem", "What are the people of {name} called?", row["demonym"], "culture", "medium"),
            ("cn-lci", "What is the largest city in {name}?", row["largest_city"], "geography", "medium"),
            ("cn-iso", "What is the two-letter ISO country code for {name}?", row["iso_code"], "geography", "hard"),
            ("cn-drv", "In which side of the road do people drive in {name}?", row["driving_side"], "geography", "medium"),
            ("cn-flg", "What are the main colours of the flag of {name}?", row["flag_colors"], "culture", "medium"),
            ("cn-cal", "What is the international dialling code for {name}?", row["calling_code"], "geography", "hard"),
            ("cn-are", "What is the total area of {name} in square kilometres?", _pretty_number(row["area_km2"]), "geography", "hard"),
            ("cn-pop", "Roughly how many people live in {name}?", _population(row["population_m"]), "geography", "medium"),
        ]
        for family, template, answer, category, difficulty in templates:
            # The largest city is only worth asking when it is not the capital.
            if family == "cn-lci" and row["largest_city"].strip().lower() == row["capital"].strip().lower():
                continue
            questions.append(_question(
                f"{family}--{key}", template.format(name=name), answer, category, difficulty))
        seat = row.get("seat_of_government", "").strip()
        if seat:
            questions.append(_question(
                f"cn-gov--{key}",
                f"Which city is the seat of government of {name}?",
                seat, "geography", "hard"))
    return questions


def _country_comparisons():
    countries = _rows("countries.csv")
    questions = []
    comparisons = [
        ("cmp-country-area", "Which country has the larger total area, {a} or {b}?", "area_km2", "geography", "medium"),
        ("cmp-country-pop", "Which country has the larger population, {a} or {b}?", "population_m", "geography", "easy"),
    ]
    for (first, second) in combinations(countries, 2):
        for family, template, field, category, difficulty in comparisons:
            left = _number(first[field])
            right = _number(second[field])
            if left is None or right is None or left == right:
                continue
            answer = first["name"] if left > right else second["name"]
            questions.append(_question(
                f"{family}--{_slug(first['name'])}-{_slug(second['name'])}",
                template.format(a=first["name"], b=second["name"]),
                answer, category, difficulty))
        left_area = _number(first["area_km2"])
        right_area = _number(second["area_km2"])
        left_pop = _number(first["population_m"])
        right_pop = _number(second["population_m"])
        if None in (left_area, right_area, left_pop, right_pop) or not left_area or not right_area:
            continue
        left_density = left_pop / left_area
        right_density = right_pop / right_area
        if left_density == right_density:
            continue
        answer = first["name"] if left_density > right_density else second["name"]
        questions.append(_question(
            f"cmp-country-den--{_slug(first['name'])}-{_slug(second['name'])}",
            f"Which country has the higher population density, {first['name']} or {second['name']}?",
            answer, "geography", "hard"))
    return questions


def _element_questions():
    elements = _rows("elements.csv")
    questions = []
    for row in elements:
        name = row["name"]
        key = _slug(name)
        templates = [
            ("el-sym", "What is the chemical symbol for {name}?", row["symbol"], "science", "easy"),
            ("el-grp", "Which group of the periodic table does {name} belong to?", row["group"], "science", "hard"),
            ("el-per", "In which period of the periodic table is {name} found?", row["period"], "science", "medium"),
            ("el-cat", "What kind of element is {name}?", row["category"], "science", "easy"),
            ("el-mass", "What is the atomic mass of {name}?", row["mass"], "science", "hard"),
            ("el-blk", "Which block of the periodic table does {name} belong to?", row["block"], "science", "hard"),
            ("el-pro", "How many protons does an atom of {name} have?", row["atomic_number"], "science", "easy"),
        ]
        for family, template, answer, category, difficulty in templates:
            if not answer:
                continue
            questions.append(_question(
                f"{family}--{key}", template.format(name=name), answer, category, difficulty))
        questions.append(_question(
            f"el-r-sym--{_slug(row['symbol'])}",
            f"Which element has the chemical symbol {row['symbol']}?", name, "science", "easy"))
    return questions


def _element_comparisons():
    elements = _rows("elements.csv")
    questions = []
    for (first, second) in combinations(elements, 2):
        for family, template, field, category, difficulty in (
            ("cmp-el-mass", "Which element has the greater atomic mass, {a} or {b}?", "mass", "science", "hard"),
            ("cmp-el-num", "Which element has the greater atomic number, {a} or {b}?", "atomic_number", "science", "easy"),
        ):
            left = _number(first[field])
            right = _number(second[field])
            if left is None or right is None or left == right:
                continue
            answer = first["name"] if left > right else second["name"]
            questions.append(_question(
                f"{family}--{_slug(first['name'])}-{_slug(second['name'])}",
                template.format(a=first["name"], b=second["name"]),
                answer, category, difficulty))
    return questions


def _state_questions():
    states = _rows("us_states.csv")
    questions = []
    for row in states:
        name = row["name"]
        key = _slug(name)
        templates = [
            ("us-cap", "What is the capital of the US state {name}?", row["capital"], "geography", "easy"),
            ("us-lci", "What is the largest city in the US state {name}?", row["largest_city"], "geography", "medium"),
            ("us-abb", "What is the two-letter postal abbreviation for {name}?", row["abbreviation"], "geography", "medium"),
            ("us-reg", "In which region of the United States is {name}?", row["region"], "geography", "medium"),
            ("us-yr", "In which year did {name} join the Union?", row["statehood_year"], "history", "medium"),
            ("us-are", "What is the total area of the US state {name} in square kilometres?", _pretty_number(row["area_km2"]), "geography", "hard"),
            ("us-pop", "Roughly how many people live in the US state {name}?", _population(row["population_m"]), "geography", "medium"),
        ]
        for family, template, answer, category, difficulty in templates:
            # The largest city is only worth asking when it is not the capital.
            if family == "us-lci" and row["largest_city"].strip().lower() == row["capital"].strip().lower():
                continue
            questions.append(_question(
                f"{family}--{key}", template.format(name=name), answer, category, difficulty))
    return questions


def _state_comparisons():
    states = _rows("us_states.csv")
    questions = []
    for (first, second) in combinations(states, 2):
        for family, template, field, category, difficulty in (
            ("cmp-us-area", "Which US state has the larger total area, {a} or {b}?", "area_km2", "geography", "medium"),
            ("cmp-us-pop", "Which US state has the larger population, {a} or {b}?", "population_m", "geography", "medium"),
        ):
            left = _number(first[field])
            right = _number(second[field])
            if left is None or right is None or left == right:
                continue
            answer = first["name"] if left > right else second["name"]
            questions.append(_question(
                f"{family}--{_slug(first['name'])}-{_slug(second['name'])}",
                template.format(a=first["name"], b=second["name"]),
                answer, category, difficulty))
    return questions


def _city_questions():
    cities = _rows("cities.csv")
    questions = []
    for row in cities:
        name = row["name"]
        key = _slug(name)
        templates = [
            ("ct-cou", "In which country is the city of {name} located?", row["country"], "geography", "easy"),
            ("ct-con", "On which continent is the city of {name} located?", row["continent"], "geography", "easy"),
            ("ct-lan", "Which famous landmark is in {name}?", row["landmark"], "culture", "medium"),
            ("ct-pop", "Roughly how many people live in the city of {name}?", _population(row["population_m"]), "geography", "medium"),
            ("ct-reg", "In which region is {name} located?", row["region"], "geography", "hard"),
        ]
        for family, template, answer, category, difficulty in templates:
            # A region that repeats the city name answers nothing.
            if family == "ct-reg" and row["region"].strip().lower() == row["name"].strip().lower():
                continue
            questions.append(_question(
                f"{family}--{key}", template.format(name=name), answer, category, difficulty))
    return questions


def _city_comparisons():
    cities = _rows("cities.csv")
    questions = []
    for (first, second) in combinations(cities, 2):
        left = _number(first["population_m"])
        right = _number(second["population_m"])
        if left is None or right is None or left == right:
            continue
        answer = first["name"] if left > right else second["name"]
        questions.append(_question(
            f"cmp-ct-pop--{_slug(first['name'])}-{_slug(second['name'])}",
            f"Which city has the larger population, {first['name']} or {second['name']}?",
            answer, "geography", "easy"))
    return questions


def _nature_questions():
    rows = _rows("nature.csv")
    questions = []
    for row in rows:
        name = row["name"]
        key = _slug(name)
        templates = [
            ("na-kin", "What type of feature is {name}?", row["kind"], "nature", "easy"),
            ("na-con", "On which continent is {feature} located?".format(
                feature=_with_kind(row["kind"], row["name"])),
             row["continent"], "nature", "easy"),
            ("na-cou", "In which country is {feature} located?".format(
                feature=_with_kind(row["kind"], row["name"])),
             row["country"], "nature", "medium"),
            ("na-mea", "What is the {measure_label} of {feature}?".format(
                measure_label=row["measure_label"], feature=_with_kind(row["kind"], row["name"])),
             f"{_pretty_number(row['measure'])} {_measurement(row['measure_unit'])}", "nature", "hard"),
            ("na-det", "Which {kind} is {detail}?".format(kind=row["kind"], detail=row["detail"].lower()),
             name, "nature", "medium"),
        ]
        for family, template, answer, category, difficulty in templates:
            questions.append(_question(
                f"{family}--{key}", template.format(name=name), answer, category, difficulty))
    return questions


def _nature_comparisons():
    rows = _rows("nature.csv")
    questions = []
    # Only compare like with like: a depth is never compared with an area.
    groups = {}
    for row in rows:
        groups.setdefault((row["kind"], row["measure_label"]), []).append(row)
    for (_kind, label), group in groups.items():
        for (first, second) in combinations(group, 2):
            left = _number(first["measure"])
            right = _number(second["measure"])
            if left is None or right is None or left == right:
                continue
            answer = first["name"] if left > right else second["name"]
            questions.append(_question(
                f"cmp-na-mea--{_slug(first['name'])}-{_slug(second['name'])}",
                f"Which has the larger {label}, {first['name']} or {second['name']}?",
                answer, "nature", "hard"))
    return questions


def _fact_questions():
    rows = _rows("facts.csv")
    questions = []
    # A country or a field is only asked when the subject has one answer for it.
    countries_by_subject = {}
    fields_by_subject = {}
    for row in rows:
        countries_by_subject.setdefault(row["subject"], set()).add(row["country"])
        fields_by_subject.setdefault(row["subject"], set()).add(row["field"])
    for row in rows:
        subject = row["subject"]
        fact = row.get("fact", "").strip() or subject
        key = _slug(f"{subject}-{row['year']}")
        templates = [
            ("fa-yr", "In which year was {fact} {verb}?".format(fact=fact, verb=row["year_verb"]),
             row["year"], "history", "medium"),
        ]
        if len(fields_by_subject[subject]) == 1:
            templates.append(
                ("fa-fld", "In which field is {subject} best known?".format(subject=subject),
                 row["field"], "history", "easy"))
        if len(countries_by_subject[subject]) == 1:
            templates.append(
                ("fa-cou", "Which country is {subject} most closely associated with?".format(subject=subject),
                 row["country"], "history", "easy"))
        for family, template, answer, category, difficulty in templates:
            questions.append(_question(f"{family}--{key}", template, answer, category, difficulty))
    return questions


def _fact_comparisons():
    rows = _rows("facts.csv")
    questions = []
    for (first, second) in combinations(rows, 2):
        first_fact = (first.get("fact", "").strip() or first["subject"]).lower()
        second_fact = (second.get("fact", "").strip() or second["subject"]).lower()
        if first_fact == second_fact:
            # A fact can never come before itself.
            continue
        left = _number(first["year"])
        right = _number(second["year"])
        if left is None or right is None or left == right:
            continue
        first_label = first.get("fact", "").strip() or first["subject"]
        second_label = second.get("fact", "").strip() or second["subject"]
        # The verb keeps the two rows of one subject apart in the wording.
        first_label = f"{first_label} ({first['year_verb']})"
        second_label = f"{second_label} ({second['year_verb']})"
        answer = f"{first_label} ({first['year']})" if left < right else f"{second_label} ({second['year']})"
        questions.append(_question(
            f"cmp-fa-yr--{_slug(first['subject'])}-{_slug(first['year'])}-{_slug(second['subject'])}-{_slug(second['year'])}",
            f"Which came first, {first_label} or {second_label}?",
            answer, "history", "medium"))
    return questions


def _language_questions():
    rows = _unique_by(_rows("languages.csv"), "name")
    questions = []
    for row in rows:
        name = row["name"]
        key = _slug(name)
        templates = [
            ("la-fam", "Which language family does {name} belong to?".format(name=name), row["family"], "culture", "medium"),
            ("la-scr", "What script is used to write {name}?".format(name=name), row["script"], "culture", "medium"),
            ("la-reg", "In which region is {name} mainly spoken?".format(name=name), row["region"], "culture", "easy"),
            ("la-spk", "Roughly how many people speak {name}?".format(name=name),
             _population(row["speakers_m"]), "culture", "medium"),
        ]
        for family, template, answer, category, difficulty in templates:
            questions.append(_question(f"{family}--{key}", template, answer, category, difficulty))
    return questions


def _language_comparisons():
    rows = _unique_by(_rows("languages.csv"), "name")
    questions = []
    for (first, second) in combinations(rows, 2):
        left = _number(first["speakers_m"])
        right = _number(second["speakers_m"])
        if left is None or right is None or left == right:
            continue
        answer = first["name"] if left > right else second["name"]
        questions.append(_question(
            f"cmp-la-spk--{_slug(first['name'])}-{_slug(second['name'])}",
            f"Which language has more speakers, {first['name']} or {second['name']}?",
            answer, "culture", "hard"))
    return questions


def _derived_questions():
    """Letter counts and alphabetical positions, both computed from the seeds."""
    questions = []
    groups = []
    for row in _rows("countries.csv"):
        groups.append((row["name"], "cn-len", "How many letters are in the English name of {name}?".format(name=row["name"]), "geography", "easy"))
        groups.append((row["capital"], "cn-len-cap", "How many letters are in the name of the capital of {name}?".format(name=row["name"]), "geography", "easy"))
    for row in _rows("us_states.csv"):
        groups.append((row["name"], "us-len", "How many letters are in the name of the US state {name}?".format(name=row["name"]), "geography", "easy"))
    for row in _rows("elements.csv"):
        groups.append((row["name"], "el-len", "How many letters are in the name of the element {name}?".format(name=row["name"]), "science", "easy"))
    for name, family, template, category, difficulty in groups:
        letters = sum(1 for character in name if character.isalpha())
        questions.append(_question(f"{family}--{_slug(name)}", template, str(letters), category, difficulty))

    # Alphabetical position inside a complete group.  The US states are all
    # there, so their position is a fact; the country list is not complete, so
    # no country position is published.
    states = sorted(row["name"] for row in _rows("us_states.csv"))
    for position, name in enumerate(states, 1):
        questions.append(_question(
            f"us-ord--{_slug(name)}",
            f"In alphabetical order, what position does {name} hold among the US states?",
            str(position), "geography", "hard"))
    return questions


_GENERATED = None


def build_generated_questions():
    """Every generated question, in a stable order. Cached for the process."""
    global _GENERATED
    if _GENERATED is not None:
        return _GENERATED
    questions = []
    for builder in (
        _country_questions,
        _country_comparisons,
        _element_questions,
        _element_comparisons,
        _state_questions,
        _state_comparisons,
        _city_questions,
        _city_comparisons,
        _nature_questions,
        _nature_comparisons,
        _fact_questions,
        _fact_comparisons,
        _language_questions,
        _language_comparisons,
        _derived_questions,
    ):
        questions.extend(builder())

    # A seed row can appear twice (the same subject in two years, a name used
    # for two features); the first question for an ID wins.
    seen = set()
    unique = []
    for question in questions:
        if question["id"] in seen:
            continue
        seen.add(question["id"])
        unique.append(question)
    _GENERATED = unique
    return unique
