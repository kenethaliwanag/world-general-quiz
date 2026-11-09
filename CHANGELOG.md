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
- Recorded questions only after a Part completes successfully and added git-tracked authoritative question history with per-Part workflow commits.
- Updated history normalization and validation tests.
- Added `--start-part` and `--total-parts` CLI options.
- Added synchronized countdown ticking and a distinct "time's up" sound effect to HyperFrames compositions.
- Added Phase 1 Facebook Reels dry-run publisher, publication-history manager, preflight validation, documentation, and tests.
- Added guarded Phase 2 Meta Graph API live-publish skeleton, duplicate-history handling, API error redaction, ffprobe validation, and Phase 2 unit tests.
- Added same-Part Reel rendering (`--render-reels`) with 3-to-5 eligible questions.
- Added separate Reel output, composition, and subtitle paths.
- Updated scheduled generation to twice daily and include Reel rendering and Facebook publication dry-runs.
- Added dedicated `facebook/reels` output, Reel subtitles, separate composition project, and ffprobe-backed full-video validation.
- Added daily scheduled generation cron conversion and publication dry-run workflow support.
- Added free locally generated SFX assets under `assets/sfx/`.
- Added GitHub Actions workflows for validation, manual video generation, scheduled video generation, and MP4 artifact validation.
- Added environment overrides for Kokoro TTS configuration.
- Documented cloud execution using native Ubuntu runner and local Kokoro HTTP service.
- Generated Facebook Reel narration independently for its configured 5-question intro and outro.
- Added progressive word-by-word display for HyperFrames intro and outro text only.
- Added separate 10-question Facebook Page Video format at `output/part_XXX/facebook/videos/..._10_questions.mp4`.
- Added a persistent numbered answer tracker to the 10-question HyperFrames composition.
