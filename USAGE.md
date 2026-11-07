# Usage Guide

## 1. Prepare Python

Python 3.10 or newer is recommended. From the project directory:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

The quiz generator itself uses only the Python standard library.

## 2. Generate quiz scripts

```bash
python main.py
```

The program automatically chooses the next Part number, selects 15 questions, and writes:
- `output/part_001/script.txt`
- `output/part_001/script.json`
- `output/part_001/subtitles/part_001.srt`

Subsequent runs generate Part 2, Part 3, and so on.

Useful options:

```bash
python main.py --part 5
python main.py --count 10
python main.py --category history
python main.py --difficulty hard
python main.py --category geography --difficulty easy
python main.py --seed 123
python main.py --reset-history
```

Available categories in the included bank include geography, science, history, culture, sports, nature and technology. The JSON file is editable; add questions using the same fields: `id`, `question`, `answer`, `category`, and `difficulty`.

## 3. Avoiding repeats

`data/used_questions.json` stores the IDs already selected. New runs avoid those IDs. If the remaining unused questions in the selected category are insufficient for the requested count, the generator starts a new cycle for that filtered pool and prints a notice.

For a clean restart:

```bash
python main.py --reset-history
```

This clears the history and resets automatic Part numbering. It does not delete previously exported scripts or videos.

## 4. Kokoro voice-over

This project integrates with the KokoroTTS server's OpenAI-compatible endpoint.

1. Install and start a KokoroTTS server following its official documentation.
2. Confirm the server is reachable at `http://localhost:7860`.
3. Change `KOKORO_BASE_URL` and `KOKORO_VOICE` in `config.py` if needed.
4. Run:

```bash
python main.py --tts
```

The project requests MP3 narration for the intro, each question, each answer and the ending. Audio files are stored under `output/audio/`.

Example voices include `af_heart`, `af_sarah`, `am_adam`, and `am_michael`; availability depends on the Kokoro server/model package you install.

## 5. HyperFrames video rendering

Install Node.js and make sure `npx` works. HyperFrames also requires its rendering dependencies; run its diagnostics from a HyperFrames project if troubleshooting:

```bash
npx hyperframes doctor
```

Generate voice-over and render:

```bash
python main.py --tts --render
```

The integration writes a HyperFrames project to `output/hyperframes/part_XXX/` and renders to `output/part_XXX/video/`. It then invokes:

```bash
npx hyperframes render --output <path-to-mp4> --fps 30
```

Rendered MP4 files are saved in `output/videos/`.

You can preview a generated composition by opening a terminal in its project directory and running:

```bash
npx hyperframes preview
```

## 6. Important timing note

The current template uses a fixed narration slot for each spoken question, followed by a five-second on-screen countdown and an answer reveal. Review the first rendered video and adjust timing/layout in `integrations/hyperframes.py` and `config.py` to match the actual selected voice's speaking speed. The five-second answer timer is a fixed visual interval; narration timing is not automatically measured in this starter version.

## 7. Troubleshooting

- **Connection refused during `--tts`:** KokoroTTS server is not running or `KOKORO_BASE_URL` is incorrect.
- **Unknown voice:** choose a voice supported by your installed Kokoro model.
- **`npx` not found:** install Node.js and reopen the terminal.
- **HyperFrames render fails:** run `npx hyperframes doctor`; verify FFmpeg/Chrome prerequisites.
- **Question filter has too few matches:** choose `--category all`, `--difficulty all`, or reduce `--count`.

## Official references

- HyperFrames documentation: https://hyperframes.app/docs/
- HyperFrames rendering: https://hyperframes.app/docs/3-guides/4-rendering
- KokoroTTS documentation: https://hangry-labs.github.io/kokoroTTS/docs/
- KokoroTTS API examples: https://github.com/hangry-labs/kokoroTTS
