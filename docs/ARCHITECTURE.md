# Architecture

## Responsibilities

- `main.py`: CLI entry point and orchestration.
- `core/question_manager.py`: loads, filters and selects unique questions.
- `core/question_bank.py`: builds the generated questions from the verified seed facts in `data/seeds/`.
- `core/history_manager.py`: persists used IDs and the latest Part number. Successful Parts are recorded after generation and rendering, then persisted to the repository by the generation workflows.
- `core/quiz_generator.py`: builds a structured quiz object and readable script.
- `core/script_exporter.py`: exports TXT, JSON, and SRT into per-Part directories.
- `integrations/kokoro_tts.py`: calls a local KokoroTTS HTTP endpoint.
- `integrations/hyperframes.py`: writes a vertical HTML composition and invokes the HyperFrames CLI.
- `data/questions.json`: hand written question bank.
- `data/seeds/*.csv`: verified facts that the generated questions are built from.
- `data/used_questions.json`: persistent no-repeat history.

## Data flow

1. CLI arguments are parsed.
2. Questions are loaded (curated plus generated) and filtered.
3. History is consulted; unused IDs are preferred, and the questions used longest ago are
   recycled if the unused pool cannot fill the Part.
4. A quiz object is built and exported.
5. Optional TTS generates audio segments.
6. Optional HyperFrames integration builds HTML and renders MP4.

## Design notes

The question bank and generated quiz JSON are separate. This allows future web dashboards, alternative renderers, analytics, and publishing integrations without changing question selection logic.

The bank holds roughly 112,000 questions: the hand written set plus questions generated from
the seed facts at run time. Generation is deterministic, so the IDs in the history stay
meaningful, and it costs under a second, so no large data file has to be committed.

A Part keeps its general-knowledge character: the target is 13 single-entity questions and 2
comparison questions, and a Part never carries more than 4 comparisons. When the fresh
single-entity questions run out, the questions used longest ago are recycled rather than
replaced by comparisons. `data/used_questions.json` keeps `used_ids` in recency order, so a
reused question moves to the end and the next Part recycles a different one.
