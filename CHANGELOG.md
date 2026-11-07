# Changelog

## Unreleased

- Fixed `main.py` import so the CLI runs.
- Made quiz intro and ending counts follow the selected question count.
- Added question-bank and history validation, plus atomic history writes.
- Added per-Part output directories for scripts, subtitles, video, and thumbnail placeholders.
- Added SRT subtitle export.
- Added audio-duration measurement for Kokoro TTS and audio-aware HyperFrames composition timing.
- Added TTS caching and clearer TTS connection errors.
- Made HyperFrames compositions conformant to the installed runtime contract.
- Added `--start-part` and `--total-parts` CLI options.
- Added synchronized countdown ticking and a distinct "time's up" sound effect to HyperFrames compositions.
- Added free locally generated SFX assets under `assets/sfx/`.
- Added GitHub Actions workflows for validation, manual video generation, scheduled video generation, and MP4 artifact validation.
- Added environment overrides for Kokoro TTS configuration.
- Documented cloud execution using native Ubuntu runner and local Kokoro HTTP service.