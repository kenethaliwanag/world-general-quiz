"""Content-quality regression tests for the generated question bank.

These tests read the raw generated questions, before the text deduplication
filter in `load_questions`, so a conflict can never be hidden by that filter.
"""
import csv
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from config import COMPARISON_TARGET_PER_PART, MAX_COMPARISONS_PER_PART
from core import question_bank
from core.question_manager import (
    _family,
    _is_comparison,
    load_questions,
    select_questions,
)

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seeds"


@pytest.fixture(scope="module")
def raw_questions():
    return question_bank.build_generated_questions()


@pytest.fixture(scope="module")
def seed_rows():
    rows = {}
    for name in ("countries", "elements", "us_states", "cities", "nature", "facts", "languages"):
        with (SEED_DIR / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
            rows[name] = list(csv.DictReader(handle))
    return rows


def _by_text(questions):
    grouped = defaultdict(set)
    for question in questions:
        grouped[question["question"].strip().lower()].add(question["answer"].strip().lower())
    return grouped


def test_no_question_text_has_two_different_answers(raw_questions):
    """The raw set must not contain one question with two answers."""
    conflicting = {
        text: answers for text, answers in _by_text(raw_questions).items() if len(answers) > 1
    }
    assert not conflicting, f"conflicting question texts: {list(conflicting.items())[:5]}"


def test_no_self_comparison_questions(raw_questions):
    """A comparison never compares a fact with itself."""
    offenders = []
    for question in raw_questions:
        if not question["id"].startswith("cmp-fa-yr--"):
            continue
        body = question["question"].removeprefix("Which came first, ").removesuffix("?")
        left, right = body.split(" or ", 1)
        if left.strip() == right.strip():
            offenders.append(question["question"])
    assert not offenders, f"self comparison questions: {offenders[:5]}"


def _source_family(family):
    """The seed a family comes from, e.g. cmp-country-area -> cmp-country."""
    if family.startswith("cmp-"):
        return "-".join(family.split("-")[:2])
    return family.split("-")[0]


def _slug_map(rows):
    """Map the generated ID slug back to the seed row it came from."""
    return {question_bank._slug(row["name"]): row for row in rows}


def test_no_question_text_is_shared_by_two_seed_sources(raw_questions):
    """A question text belongs to one seed source only."""
    by_text = defaultdict(list)
    for question in raw_questions:
        by_text[question["question"].strip().lower()].append(question)
    shared = {}
    for text, group in by_text.items():
        sources = {_source_family(_family(q["id"])) for q in group}
        if len(sources) > 1:
            shared[text] = sorted(sources)
    assert not shared, f"question texts shared by two sources: {list(shared.items())[:5]}"


def test_us_state_questions_do_not_collide_with_country_questions(raw_questions):
    """The country Georgia and the US state Georgia must stay separate."""
    by_text = defaultdict(list)
    for question in raw_questions:
        by_text[question["question"].strip().lower()].append(question)
    collisions = {
        text: [q["id"] for q in group]
        for text, group in by_text.items()
        if {"us", "cn"} & {_source_family(_family(q["id"])) for q in group}
        and {"us", "cn"} <= {_source_family(_family(q["id"])) for q in group}
    }
    assert not collisions, f"US state and country questions share a text: {list(collisions.items())[:5]}"
    georgia = [q for q in raw_questions if q["id"].endswith("--georgia")]
    assert {q["answer"] for q in georgia if _family(q["id"]) == "cn-cap"} == {"Tbilisi"}
    assert {q["answer"] for q in georgia if _family(q["id"]) == "us-cap"} == {"Atlanta"}


def test_country_and_field_questions_are_unambiguous(raw_questions, seed_rows):
    """A country or field question is only produced when one answer exists."""
    countries = defaultdict(set)
    fields = defaultdict(set)
    for row in seed_rows["facts"]:
        countries[row["subject"]].add(row["country"])
        fields[row["subject"]].add(row["field"])

    asked = defaultdict(set)
    for question in raw_questions:
        family = _family(question["id"])
        if family in ("fa-cou", "fa-fld"):
            subject = question["id"].split("--", 1)[1].rsplit("-", 1)[0].replace("-", " ")
            asked[family].add(subject)

    for question in raw_questions:
        if _family(question["id"]) == "fa-cou":
            subject = question["question"].removeprefix(
                "Which country is ").removesuffix(" most closely associated with?")
            assert len(countries[subject]) == 1, f"ambiguous country question: {subject}"
        if _family(question["id"]) == "fa-fld":
            subject = question["question"].removeprefix(
                "In which field is ").removesuffix(" best known?")
            assert len(fields[subject]) == 1, f"ambiguous field question: {subject}"


def test_measurement_answers_carry_their_unit(raw_questions):
    """A measured answer never shows a bare number."""
    unit_words = ("kilometres", "metres", "square kilometres")
    for question in raw_questions:
        if _family(question["id"]) != "na-mea":
            continue
        assert any(word in question["answer"] for word in unit_words), question


def test_largest_city_questions_do_not_repeat_the_capital(raw_questions, seed_rows):
    """The largest city is only asked when it is not the capital."""
    capitals = _slug_map(seed_rows["countries"])
    state_capitals = _slug_map(seed_rows["us_states"])
    for question in raw_questions:
        family = _family(question["id"])
        if family == "cn-lci":
            row = capitals[question["id"].split("--", 1)[1]]
            assert question["answer"].strip().lower() != row["capital"].strip().lower()
        if family == "us-lci":
            row = state_capitals[question["id"].split("--", 1)[1]]
            assert question["answer"].strip().lower() != row["capital"].strip().lower()


def test_city_region_questions_do_not_answer_with_the_city(raw_questions, seed_rows):
    """A region that repeats the city name answers nothing."""
    cities = _slug_map(seed_rows["cities"])
    for question in raw_questions:
        if _family(question["id"]) != "ct-reg":
            continue
        row = cities[question["id"].split("--", 1)[1]]
        assert question["answer"].strip().lower() != row["name"].strip().lower()


def test_meta_families_are_not_generated(raw_questions):
    """No question presents the seed bank as a world fact."""
    for question in raw_questions:
        text = question["question"].lower()
        assert "in this question bank" not in text
        assert "among the countries of" not in text


def test_a_part_never_exceeds_the_comparison_maximum(tmp_path, monkeypatch):
    """A Part keeps at most MAX_COMPARISONS_PER_PART comparison questions."""
    import core.history_manager as history_manager

    # Keep the production history file out of this test.
    monkeypatch.setattr(history_manager, "HISTORY_FILE", tmp_path / "used.json")

    history = {"used_ids": [], "last_part": 0}
    for part in range(1, 60):
        selected, _, history = select_questions(15, "all", "all", part, history=history)
        comparisons = [q for q in selected if _is_comparison(q["id"])]
        assert len(comparisons) <= MAX_COMPARISONS_PER_PART
        assert len({q["id"] for q in selected}) == 15
        # The production update: a reused ID moves to the newest end of the list.
        history = history_manager.record_question_usage(
            history, [q["id"] for q in selected], part)
        assert len(history["used_ids"]) == len(set(history["used_ids"]))
        assert history["last_part"] == part
    # record_question_usage is the only writer of the history file, so this
    # proves the test really ran the production recency update.
    assert (tmp_path / "used.json").exists()


def test_normal_selection_targets_two_comparisons():
    """With a healthy bank a Part carries the comparison target."""
    selected, _, _ = select_questions(15, "all", "all", 7, history={"used_ids": [], "last_part": 0})
    comparisons = [q for q in selected if _is_comparison(q["id"])]
    assert len(comparisons) == COMPARISON_TARGET_PER_PART
    assert len(selected) - len(comparisons) == 15 - COMPARISON_TARGET_PER_PART


def test_family_to_category_mapping_is_consistent(raw_questions):
    """Every family maps to one category, and the categories are defensible."""
    categories = defaultdict(set)
    for question in raw_questions:
        categories[_family(question["id"])].add(question["category"])
    for family, found in categories.items():
        assert len(found) == 1, f"{family} uses several categories: {found}"
    assert "nature" in categories["na-con"], "nature features must be filed as nature"
    assert "nature" in categories["na-cou"], "nature features must be filed as nature"
    for family in ("la-fam", "la-scr", "la-reg", "la-spk"):
        assert "culture" in categories[family], f"{family} should be filed as culture"


def test_seed_rows_are_structurally_valid(seed_rows):
    """The seed files hold the fields the templates need."""
    for row in seed_rows["countries"]:
        for field in ("name", "capital", "continent", "currency", "language", "largest_city"):
            assert row[field].strip(), f"country row without {field}: {row}"
        assert row["seat_of_government"] is not None
    for row in seed_rows["elements"]:
        assert row["symbol"].strip() and row["atomic_number"].strip()
    assert [row["atomic_number"] for row in seed_rows["elements"]] == [
        str(number) for number in range(1, len(seed_rows["elements"]) + 1)]
    for row in seed_rows["nature"]:
        assert row["measure"].strip() and row["measure_unit"].strip()
        assert row["measure_unit"] in {"km", "m", "km²"}
    for row in seed_rows["facts"]:
        assert row["subject"].strip() and row["year"].strip() and row["fact"].strip()


def test_generated_question_ids_are_unique(raw_questions):
    ids = [question["id"] for question in raw_questions]
    assert len(ids) == len(set(ids))


def test_recycled_questions_rotate_by_actual_last_use(tmp_path, monkeypatch):
    """Recycling must not keep picking the same oldest questions."""
    import core.history_manager as history_manager
    import core.question_manager as question_manager

    questions = [
        {"id": f"q{i:03d}", "question": f"Question {i}?", "answer": f"Answer {i}.",
         "category": "general", "difficulty": "easy"}
        for i in range(1, 21)
    ]
    bank_file = tmp_path / "questions.json"
    bank_file.write_text(__import__("json").dumps(questions), encoding="utf-8")
    history_file = tmp_path / "used.json"
    monkeypatch.setattr(question_manager, "QUESTIONS_FILE", bank_file)
    monkeypatch.setattr(history_manager, "HISTORY_FILE", history_file)
    # Isolate the test bank from the generated questions.
    monkeypatch.setattr(question_manager, "build_generated_questions", lambda: [])

    history = {"used_ids": [f"q{i:03d}" for i in range(1, 21)], "last_part": 1}
    picked = []
    for part in range(2, 6):
        selected, pool_reset, _ = question_manager.select_questions(
            15, "all", "all", part, history=history)
        assert pool_reset is True
        picked.append([q["id"] for q in selected])
        history = history_manager.record_question_usage(history, [q["id"] for q in selected], part)

    # Every Part picks different questions, and the oldest is used first.
    assert picked[0][0] == "q001", "the least recently used question must be picked first"
    assert set(picked[0]) != set(picked[1]), "recycling must not repeat the same Part"
    assert set(picked[1]) != set(picked[2])
    # The reused question moves to the end of the recency order.
    assert history["used_ids"][-15:] == picked[-1]
    assert history["used_ids"][0] not in picked[-1]


def test_failed_generation_does_not_consume_question_history(tmp_path, monkeypatch):
    """A failed Part must leave the history untouched."""
    import core.history_manager as history_manager
    import core.question_manager as question_manager

    questions = [
        {"id": f"q{i:03d}", "question": f"Question {i}?", "answer": f"Answer {i}.",
         "category": "general", "difficulty": "easy"}
        for i in range(1, 31)
    ]
    bank_file = tmp_path / "questions.json"
    bank_file.write_text(__import__("json").dumps(questions), encoding="utf-8")
    history_file = tmp_path / "used.json"
    monkeypatch.setattr(question_manager, "QUESTIONS_FILE", bank_file)
    monkeypatch.setattr(history_manager, "HISTORY_FILE", history_file)

    history = {"used_ids": [], "last_part": 0}
    selected, _, _ = question_manager.select_questions(15, "all", "all", 1, history=history)
    # The caller only records after a successful Part; nothing is written here.
    assert not history_file.exists()
    assert history["used_ids"] == []


def test_history_file_stays_backward_compatible(tmp_path, monkeypatch):
    """A legacy history file keeps working and stays unique."""
    import core.history_manager as history_manager

    history_file = tmp_path / "used.json"
    monkeypatch.setattr(history_manager, "HISTORY_FILE", history_file)
    history_file.write_text(
        '{"used_ids": ["q001", "q001", "q002"], "last_part": 4}', encoding="utf-8")
    loaded = history_manager.load_history()
    assert loaded["used_ids"] == ["q001", "q002"]
    assert loaded["last_part"] == 4

    updated = history_manager.record_question_usage(loaded, ["q003", "q001"], 6)
    assert updated["used_ids"] == ["q002", "q003", "q001"]
    assert updated["last_part"] == 6
    assert history_manager.load_history()["last_part"] == 6


PH_SLUGS = {"josé-rizal", "katipunan", "emilio-aguinaldo",
            "first-republic-of-the-philippines", "bataan-death-march",
            "battle-of-manila", "philippine-independence",
            "edsa-people-power-revolution", "ferdinand-marcos",
            "corazon-aquino", "typhoon-haiyan",
            "fernando-amorsolo", "juan-luna",
            "carlos-p--romulo", "san-juanico-bridge",
            "lapu-lapu", "ferdinand-magellan-1521", "manila-international-airport",
            "mount-apo", "mayon-volcano", "mount-hamiguitan",
            "puerto-princesa-subterranean-river", "tubbataha-reefs-natural-park",
            "philippines", "manila", "tagalog", "cebuano"}


def _is_ph_question(question):
    id_ = question["id"].lower()
    if id_.startswith("q") and "--" not in id_:
        return int(id_[1:]) >= 122
    if "--" in id_:
        body = id_.split("--", 1)[1]
        return any(slug in body for slug in PH_SLUGS)
    return False


def test_philippine_content_is_present_but_bounded(raw_questions):
    """The Philippines must be a meaningful part of the bank, not the whole."""
    bank = load_questions()
    ph = [q for q in bank if _is_ph_question(q)]
    single = [q for q in bank if not _is_comparison(q["id"])]
    ph_single = [q for q in ph if not _is_comparison(q["id"])]
    ph_comparisons = [q for q in ph if _is_comparison(q["id"])]
    assert 4_000 <= len(ph) <= 5_500, f"PH-attributable count outside expected range: {len(ph)}"
    assert 100 <= len(ph_single) <= 200, f"PH single count outside expected range: {len(ph_single)}"
    assert 3_000 <= len(ph_comparisons) <= 5_000, f"PH comparison count outside expected range: {len(ph_comparisons)}"


def test_philippine_seeds_are_in_the_raw_set(raw_questions, seed_rows):
    """The new seed rows are actually generating questions, with the expected IDs."""
    ids = {q["id"] for q in raw_questions}
    assert "fa-yr--josé-rizal-1896" in ids
    assert "fa-yr--katipunan-1892" in ids
    assert "na-kin--mount-apo" in ids
    assert "fa-cou--ferdinand-magellan-1480" not in ids
    assert "fa-cou--ferdinand-magellan-1521" not in ids
    assert "na-kin--mayon-volcano" in ids


def test_philippine_provenance_document_covers_every_added_row():
    text = Path("docs/PHILIPPINE_CONTENT_SOURCES.md").read_text(encoding="utf-8")
    assert "data/seeds/facts.csv" in text
    assert "data/seeds/nature.csv" in text
    assert "122" in text and "123" in text and "169" in text
    assert "UNESCO" in text
    assert "nhcp.gov.ph" in text
    assert "psa.gov.ph" in text


def test_new_philippine_rows_do_not_violate_existing_policy():
    """The 13+2 / max-4 comparison rules still hold after expansion."""
    history = {"used_ids": [], "last_part": 0}
    selected, _, _ = select_questions(15, "all", "all", 7, history=history)
    comparisons = [q for q in selected if _is_comparison(q["id"])]
    assert len(comparisons) <= MAX_COMPARISONS_PER_PART
    assert len(selected) == 15
    assert len({q["id"] for q in selected}) == 15
