# Architecture

## Responsibilities

- `main.py`: CLI entry point and orchestration.
- `core/question_manager.py`: loads, filters and selects unique questions.
- `core/history_manager.py`: persists used IDs and the latest Part number. Successful Parts are recorded after generation and rendering, then persisted to the repository by the generation workflows.
- `core/quiz_generator.py`: builds a structured quiz object and readable script.
- `core/script_exporter.py`: exports TXT, JSON, and SRT into per-Part directories.
- `integrations/kokoro_tts.py`: calls a local KokoroTTS HTTP endpoint.
- `integrations/hyperframes.py`: writes a vertical HTML composition and invokes the HyperFrames CLI.
- `data/questions.json`: editable question bank.
- `data/used_questions.json`: persistent no-repeat history.

## Data flow

1. CLI arguments are parsed.
2. Questions are loaded and filtered.
3. History is consulted; unused IDs are preferred.
4. A quiz object is built and exported.
5. Optional TTS generates audio segments.
6. Optional HyperFrames integration builds HTML and renders MP4.

## Design notes

The question bank and generated quiz JSON are separate. This allows future web dashboards, alternative renderers, analytics, and publishing integrations without changing question selection logic.
