# Question Bank

The bank is built in two parts.

## 1. The curated questions

`data/questions.json` holds the hand written questions. Each record has:

- `id`: stable unique identifier (do not reuse IDs).
- `question`: the prompt shown to viewers.
- `answer`: canonical answer to reveal.
- `category`: topic filter.
- `difficulty`: `easy`, `medium`, or `hard`.

## 2. The generated questions

`core/question_bank.py` turns the verified facts in `data/seeds/*.csv` into questions, so the
bank is far larger than any Part history can exhaust.

| Seed file | Rows | Facts it holds | Question families |
|---|---|---|---|
| `countries.csv` | 192 | capital, seat of government, continent, currency, currency code, language, demonym, largest city, ISO code, driving side, flag colours, dialling code, area, population | capital, seat of government, continent, currency, currency code, language, demonym, largest city, ISO code, driving side, flag colours, dialling code, area, population, letter counts, and area / population / density comparisons |
| `elements.csv` | 118 | symbol, atomic number, group, period, category, mass, block | symbol, group, period, category, mass, block, proton count, reverse symbol lookup, letter counts, and mass / atomic number comparisons |
| `us_states.csv` | 50 | capital, largest city, abbreviation, region, statehood year, area, population | capital, largest city, abbreviation, region, statehood year, area, population, letter counts, alphabetical position, and area / population comparisons |
| `cities.csv` | 180 | country, continent, landmark, region, population | country, continent, landmark, population, region, and population comparisons |
| `nature.csv` | 95 | kind, continent, country, measure, measure unit, superlative | type, continent, country, measurement, superlative, and comparisons **within the same kind and unit** |
| `facts.csv` | 196 | subject, the specific fact, kind, field, year, verb, country | year, field (only when unambiguous), country (only when unambiguous), and "which came first" comparisons |
| `languages.csv` | 81 | family, script, region, speakers | family, script, region, speakers, and speaker comparisons |

The Philippines is a full part of the international content through its 192nd country row, a Manila city row, two major languages (Tagalog and Cebuano) **and** 25 added Philippine facts, five natural features and 48 curated questions. The provenance of every new claim is recorded in `docs/PHILIPPINE_CONTENT_SOURCES.md`.

Every generated ID is deterministic (`family--key`), so the question history stays meaningful
across runs. Questions are generated at run time, so the repository never carries a huge JSON
file.

### Seed schema notes

- `countries.csv` has a `seat_of_government` column. It is empty for every country except
  Bolivia, where Sucre is the constitutional capital and La Paz is the seat of government.
  Both facts are asked separately.
- `nature.csv` has a `measure_unit` column (`km`, `m`, `km²`). Every measurement answer
  carries its unit, so no answer is a bare number.
- `facts.csv` has a `fact` column naming the specific fact a row holds. It is the subject
  unless a subject has more than one fact of the same kind, in which case the row names it
  (`the special theory of relativity`, `the American Red Cross`).

## Size and variety

| | |
|---|---|
| Questions in the bank | **116,199** |
| Curated hand written | 169 |
| Generated | 116,030 |
| Template families | 63 |
| Single-entity questions | 6,517 |
| Comparison questions | 109,682 |
| Conflicting question texts | **0** |
| Generation time | under one second |

33 generated questions now repeat a curated or earlier generated text and are dropped. 169 curated questions plus 116,030 generated questions make up the bank.

The Philippine subset measures **4,772** attributable questions — 153 single-entity
questions (2.3 % of the pool) and 4,619 comparisons (908 inherited + 3,711 new). The
Philippines remain well under the share needed to dominate the feed.

## Selection policy

A Part keeps its general-knowledge character. For a 15-question Part:

- **Target: 13 single-entity questions and 2 comparison questions**
  (`COMPARISON_TARGET_PER_PART`).
- **Absolute maximum: 4 comparison questions** (`MAX_COMPARISONS_PER_PART`).

Priority order:

1. **Fresh single-entity questions**, spread across families before a second question is taken
   from any family.
2. **Recycled single-entity questions**, least recently used first, still spread across
   families. This keeps the format instead of filling the Part with comparisons.
3. **Comparison questions**, up to the target. If fewer than two eligible comparisons exist,
   the remaining slots are filled with more single-entity questions.
4. If the Part still cannot be filled, more comparisons are used, never above the maximum. If
   the eligible bank cannot supply 15 distinct questions at all, the run fails loudly instead
   of breaking the policy.

A simulated 900-Part run with isolated history: 13.00 single-entity and 2.00 comparisons
per Part, 14.95 distinct families, 4.61 distinct categories, zero Parts above the PH comp-max.
The single-entity pool of 6,517 questions supports roughly 500 fresh Parts before recycling
is required.

## Recycling behaviour

`data/used_questions.json` holds `used_ids` as a unique list in **recency order**: the first
entry was used longest ago. When a Part reuses a question, that ID moves to the end of the
list, so the next Part recycles a different question instead of the same one. The file format
is unchanged, so existing history files keep working.

In 900 simulated Parts with isolated history, 13.00 single-entity and 2.00 comparisons per
Part were produced with an average 14.95 distinct families and 4.61 distinct categories. 399 of
those 900 Parts recycled at least one question once the fresh single-entity pool was
insufficient. At two Parts a day, a fact comes back roughly every eight months once the pool
turns.

## Editorial quality checklist

Before adding a hand written question:
1. Verify the answer against a reliable reference.
2. Avoid questions with multiple equally valid answers unless the question wording narrows the answer.
3. Prefer concise spoken answers.
4. Keep the question readable on a phone screen.
5. Add a stable new ID and never recycle an old ID for a different question.

Before adding a seed row:
1. Every column must be a fact you can verify; the templates never combine two facts about
   different entities, so a wrong row can only make one wrong question.
2. Comparisons only run between rows that share the same unit (two rivers by length, never a
   depth against an area).
3. A row that would make a question ambiguous must be given its own wording (`fact`) or its
   question must be skipped.
4. A measurement always carries its unit.
5. Keep the spoken answer short enough to read on screen.

The generated questions are derived from a fixed set of verified facts, but they are still a
starter set, not a continuously fact-checked live knowledge base. Review the seed files before
monetized publication.
