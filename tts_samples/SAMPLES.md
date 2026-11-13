# TTS voice samples — World General Knowledge Quiz

Four voices, the **same ten production lines**, so you can judge them side by side.
Every file is a single narration clip, exactly as the pipeline generates it
(one clip per on-screen line).

| Folder                                   | Engine                                        | Voice                  | Rate                | Note                                                                                                 |
| ---------------------------------------- | --------------------------------------------- | ---------------------- | ------------------- | ---------------------------------------------------------------------------------------------------- |
| `production_server_af_bella/speed_0_92/` | **Kokoro-FastAPI v0.9.2 (production server)** | `af_bella`             | `speed=0.92`        | Generated through `integrations/kokoro_tts.py` against the real server the workflows run             |
| `production_server_af_bella/speed_1_00/` | **Kokoro-FastAPI v0.9.2 (production server)** | `af_bella`             | `speed=1.00`        | Same voice at engine speed, for comparison                                                           |
| `kokoro_af_heart_1.00/`                  | Kokoro-82M (FastAPI, PyTorch)                 | `af_heart`             | `speed=1.00`        | Previous production voice. Real files taken from the published Part 004 artifact, not re-synthesised |
| `kokoro_af_bella_0.92/`                  | Kokoro-82M (ONNX export)                      | `af_bella`             | `speed=0.92`        | ONNX comparison sample; production uses Kokoro-FastAPI v0.9.2                                        |
| `piper_libritts_high/`                   | Piper 1.8.0 (ONNX)                            | `en_US-libritts-high`  | `length_scale=1.08` | Highest quality Piper English voice, commercially safe                                               |
| `piper_kristin_medium/`                  | Piper 1.8.0 (ONNX)                            | `en_US-kristin-medium` | `length_scale=1.08` | Second Piper voice, public domain dataset                                                            |

## The lines

| File           | Spoken text                                                      |
| -------------- | ---------------------------------------------------------------- |
| `intro_1.mp3`  | Welcome to the World General Knowledge Quiz!                     |
| `intro_2.mp3`  | How well do you know these 10 world general knowledge questions? |
| `intro_3.mp3`  | This is Part 4. If you answer 10 out of 10, you are exceptional! |
| `intro_4.mp3`  | Can you get all 10 correct?                                      |
| `q01.mp3`      | Question 1, easy. What is the chemical symbol for gold?          |
| `a01.mp3`      | Au is the correct answer.                                        |
| `ending_1.mp3` | How did you do?                                                  |
| `ending_2.mp3` | How many did you get right?                                      |
| `ending_3.mp3` | Comment your score out of 10!                                    |
| `ending_4.mp3` | Share with friends and follow for more quizzes!                  |

## Durations (seconds)

| Line      | af_heart 1.00 | af_bella 0.92 | libritts-high | kristin-medium |
| --------- | ------------- | ------------- | ------------- | -------------- |
| intro_1   | 2.568         | 2.667         | 2.601         | 2.740          |
| intro_2   | 3.432         | 3.691         | 3.251         | 3.611          |
| intro_3   | 4.176         | 4.117         | 4.052         | 4.586          |
| intro_4   | 1.800         | 1.451         | 1.474         | 1.614          |
| q01       | 3.792         | 4.096         | 2.995         | 3.866          |
| a01       | 1.680         | 1.408         | 1.614         | 1.463          |
| ending_1  | 1.248         | 1.003         | 0.987         | 1.068          |
| ending_2  | 1.728         | 1.429         | 1.335         | 1.474          |
| ending_3  | 1.752         | 1.643         | 1.521         | 1.834          |
| ending_4  | 2.664         | 2.773         | 2.125         | 3.506          |
| **total** | **24.84**     | **24.28**     | **21.95**     | **25.76**      |

Slower speech stretches the video: the 10-question Page Video was 159.6 s with
`af_heart @ 1.00`; expect roughly 165–170 s at 0.92. The Reel keeps 1.00 to help
meet Meta's 90-second limit; its actual rendered duration still needs validation.

## Licensing

- **Kokoro-82M** — Apache-2.0 weights. `af_heart` and `af_bella` are the upstream v1.0 voice packs.
- **Piper** — the engine is GPL-3.0 (used here as a build tool, the repo does not ship it).
  `en_US-libritts-high` is **CC BY 4.0** (attribution required), `en_US-kristin-medium` is
  **public domain**. Do **not** use `lessac`/`ryan`/`amy`/`hfc_*`: they descend from the
  Blizzard corpus, which is research-only and excludes commercial use.
- Both are free, run on CPU, and need no paid service.

## Regenerating

```powershell
# Piper voices (137 MB + 64 MB)
python -m piper.download_voices --download-dir <voices-dir> en_US-libritts-high en_US-kristin-medium

# Piper synthesis
python -m piper -m <voices-dir>/en_US-libritts-high.onnx -f out.wav -- "Welcome to the World General Knowledge Quiz!"

# Kokoro ONNX (onnxruntime only, no torch)
pip install kokoro-onnx
# model: https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/onnx/model.onnx
# voice: https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/voices/af_bella.bin
```

## Level note

The Piper files peak near 0.95 while the Kokoro files peak around 0.37–0.59. If Piper is
adopted, the narration level has to be matched (or loudness-normalised) before publishing.

**`af_bella` at `speed=0.92` is the production narrator.** The Reel uses `speed=1.00`
to help meet Meta's 90-second limit; actual rendered duration still needs validation.

## Production-server verification

`production_server_af_bella/` was generated against a real **Kokoro-FastAPI v0.9.2** server
(the exact tag the workflows clone, `VOICES_DIR=src/voices/v1_0`), using this project's
`integrations/kokoro_tts.py` client:

- `/v1/audio/voices` → **72 voices, `af_bella` listed**
- `POST /v1/audio/speech` with `voice=af_bella`, `speed=0.92`, `response_format=mp3` → valid 24 kHz mono MP3
- the same request at `speed=1.00` is consistently shorter, so the rate is applied:

| Line     | af_bella 0.92 | af_bella 1.00 | difference |
| -------- | ------------- | ------------- | ---------- |
| intro_1  | 2.808 s       | 2.616 s       | +0.192 s   |
| q01      | 4.368 s       | 4.104 s       | +0.264 s   |
| a01      | 1.728 s       | 1.656 s       | +0.072 s   |
| ending_1 | 1.296 s       | 1.176 s       | +0.120 s   |

The `[pause:0.25s]` tag is accepted by the server and adds audible separation
(4.368 s with the tag vs 4.296 s without, same text and speed).
