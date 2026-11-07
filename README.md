# World General Knowledge Quiz

A Python-first content pipeline for generating sequential general-knowledge quiz scripts and vertical Facebook Reels videos.

## What it does

- Selects unique questions from a JSON question bank (100+ included).
- Remembers used question IDs between runs to avoid repeats across Parts.
- Generates sequential Part numbers automatically.
- Exports each quiz as TXT and JSON.
- Optionally generates voice-over using a running KokoroTTS server.
- Optionally creates a HyperFrames composition and renders an MP4.

## Requirements

- Python 3.10+
- Node.js/npm for HyperFrames rendering
- FFmpeg and a supported Chrome/Chromium runtime as required by HyperFrames
- Optional: a running KokoroTTS server for voice generation

## Quick start

```bash
python main.py
```

This creates the next Part, selects 15 questions, prints the script, and saves TXT/JSON files under `output/scripts/`.

Generate a specific Part:

```bash
python main.py --part 1
```

Generate with a category or difficulty:

```bash
python main.py --category geography
python main.py --difficulty hard
python main.py --category science --difficulty medium
```

Generate narration and a video:

```bash
python main.py --tts --render
```

See [USAGE.md](USAGE.md) for setup details and all options.

## Cloud generation

GitHub Actions workflows are included under `.github/workflows` for validation, manual video generation, and scheduled generation. The scheduled workflow stays disabled until it is enabled in GitHub, and generated videos are uploaded as workflow artifacts rather than committed to the repository.

## Facebook Reels Publishing - Phase 1

A local dry-run is available through python main.py --publish-dry-run --part <PART>.
No Meta API request, credential operation, or publication occurs in Phase 1.

## Facebook Reels Publishing - Phase 2

Phase 2 adds a guarded live Meta Graph API skeleton and unit-test coverage for the guarded live path.

Dry run only:

`ash
python main.py --publish-dry-run --part 1
`

No live Meta upload occurs unless all of these are set:

`	ext
FACEBOOK_PUBLISH_ENABLED=true
FACEBOOK_PUBLISH_DRY_RUN=false
META_PAGE_ID=<page-id>
META_PAGE_ACCESS_TOKEN=<page-access-token>
`

Live publishing remains explicitly disabled by default.
