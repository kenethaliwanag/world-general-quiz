# End-to-End Validation and Quality Assurance Report

## 1. Overall project status

The World General Knowledge Quiz pipeline now runs end to end without the previously blocking import error. It can select unique questions, create per-Part outputs, generate SRT subtitles, build a HyperFrames composition, and render a 1080×1920, 30 FPS MP4.

Core rendering was verified in this environment. Actual Kokoro narration has **not** been verified in this environment because no Kokoro server was available.

## 2. Components successfully verified

- Python module compilation and entry-point import.
- Question loading, filtering, and validation.
- Cross-Part duplicate prevention and part numbering.
- TXT and JSON export.
- SRT subtitle export.
- HyperFrames composition generation.
- HyperFrames 0.9.20 `check`: 0 lint errors, 0 runtime errors, 0 layout issues, contrast passes.
- MP4 render at 1080×1920, 30 FPS, correct duration and no audio track when TTS is not used.
- Audio duration probing via ffprobe.
- Windows `npx` executable discovery and invocation.

## 3. Components not yet tested

- Actual Kokoro TTS server connectivity and response parsing in this environment.
- Real narration pronunciation, pacing, and pronunciation of names/places.
- Audio/video synchronization with real speech durations.
- Subtitle timing against real narration.
- Subjective visual quality, because screenshot review was performed only by the renderer and not by human inspection.

## 4. Implementation issues discovered and status

Resolved:
- `main.py` imported `record_part` from the wrong module.
- HyperFrames composition lacked timeline registration and a root duration.
- Audio elements lacked required `id` attributes.
- Narration slots were fixed and could cut off speech; they now use measured durations where available.
- Render invocation could not resolve `npx` on Windows.
- Output directories did not match the required per-Part layout.

Remaining, non-blocking:
- `hyperframes check` reports creative warnings only: `film_silent`, `dead_stretch`, and `audio_none` because no music or audio is included when TTS is not used.
- Timed elements do not have stable `id` attributes for HyperFrames Studio editing; this is a warning, not a render blocker.
- If TTS fails partway, cached partial files may remain. Re-running `--tts` overwrites them.
- The in-repository question bank does not include `explanation` or `source/reference` fields yet.

## 5. Kokoro TTS integration requirements

### Current integration

- Endpoint used: `{KOKORO_BASE_URL}/v1/audio/speech`
- Default: `http://localhost:7860/v1/audio/speech`
- Request fields: `model`, `input`, `voice`, `response_format`, `speed`
- Defaults in `config.py`: model `kokoro`, voice `af_bella`, format `mp3`, speed `0.92` (`1.00` for the Reel).
- Timeout: 180 seconds.
- Cache: existing valid, non-empty, ffprobe-readable audio is reused.
- Duration measurement: ffprobe JSON `format.duration`.

### Starting a local Kokoro server

The Hangry Labs KokoroTTS server is provided as Docker software and was not installed in this environment. To test real TTS locally, install Docker Desktop, then run:

```powershell
docker run --name kokorotts --restart unless-stopped -p 7860:7860 --gpus all -e CUDA_VISIBLE_DEVICES=0 -v kokorotts_data:/app/persistent hangrylabs/kokorotts:latest
```

For CPU-only machines, remove `--gpus all` and the CUDA environment variable if Docker/WSL cannot expose a GPU.

Then verify:

```powershell
curl http://localhost:7860/health
python main.py --tts --count 1
```

The server is documented as OpenAI-compatible and defaults to MP3, matching the current integration.

## 6. Real audio/video synchronization test procedure

Once Kokoro is running, execute:

```powershell
python main.py --part 1 --count 15 --tts --render
```

Then verify:
- Each `output/part_001/narration` file is readable and longer than zero bytes.
- FFprobe durations in `output/part_001/hyperframes` are finite.
- The composition duration changes based on measured speech, not only on countdowns.
- Question text remains visible through the five-second countdown.
- Answer reveal occurs immediately after countdown and stays visible for at least the answer narration duration plus padding.
- Rendered video duration equals `meta.json.duration_seconds`.
- SRT timestamps align with the spoken content.

## 7. Visual quality findings

Automated check results show the layout and contrast pass. Human or vision-based QA should still review:
- Mobile legibility of question text.
- Safe margins on 1080×1920.
- Countdown visibility.
- Answer reveal emphasis.
- Pacing during silent periods.
- Whether background music or sound effects are needed before publishing, since current no-TTS renders are silent.

Recommended visual changes:
- Add a subtle entrance animation to question cards if publishing with audio.
- Verify font size on physical phone devices.
- Add background music only if licensed and low enough not to mask narration.
- Consider shortening dead stretches by beginning countdown immediately after narration ends.

## 8. Question bank findings

- Total questions: 121.
- No duplicate normalized questions.
- No duplicate IDs.
- Categories: science 27, geography 25, history 24, culture 15, technology 11, sports 10, nature 9.
- Difficulty: easy 68, medium 48, hard 5.
- One answer has six words (`q117`), acceptable but slightly long.
- One question exceeds 90 characters (`q053`), acceptable but should be checked for readability.
- Master-spec categories call for `World Culture`, `Nature and Animals`, and `General Knowledge`; the current bank uses `culture`, `nature`, and has no general-knowledge category.

Recommended question-bank corrections:
- Increase hard-question coverage to reduce category skew.
- Add optional `explanation` and `source` fields only before larger-scale validation.
- Map or rename categories only after the intended taxonomy is finalized. Do not rename IDs after publishing.

## 9. Recommended implementation sequence

1. Install and run Kokoro using the documented Docker command.
2. Generate one narrated Part and inspect every audio file.
3. Run `hyperframes check` and `hyperframes snapshot` on the narrated project.
4. Render and measure final MP4 timing.
5. Review question accuracy and difficulty distribution.
6. Add music/effects only after narration sync is accepted.

## 10. Final acceptance criteria

- `python main.py --count 15 --tts --render` completes without manual intervention.
- All 15 questions are unique within the Part.
- Previously used questions are not reused until the filtered bank is exhausted.
- All generated audio files are valid and measurable.
- MP4 resolution is 1080×1920 at 30 FPS.
- No narration is cut off.
- Countdown, answer reveal, and ending narration are synchronized.
- SRT subtitles are generated and timed for the Part.
- Rendered video is acceptable for Facebook Reels publication.