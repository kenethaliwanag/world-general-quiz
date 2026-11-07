# Facebook Reels Publishing — Phase 1 Foundation

This document describes the local Phase 1 Facebook Reels publishing helper. Phase 1 performs **dry-run only**. No Meta Graph API upload or publish request is sent.

## Architecture

The Facebook publisher is separate from question generation, TTS, and HyperFrames rendering.

Components:

- `integrations/facebook_publisher.py` — preflight validation, payload preparation, and redacted status reporting.
- `core/publish_manager.py` — publication-history storage and duplicate-content detection.
- `data/facebook_publish_history.json` — local publication state.
- `main.py --publish-dry-run` — CLI entry point for validation and planning.

## CLI dry run

Generate an MP4 and then run:

```powershell
python main.py --publish-dry-run --part 1
```

The command:
1. Locates `output/part_001/video/world_general_knowledge_quiz_part_001.mp4`.
2. Validates the MP4 against the Facebook Reels preflight profile.
3. Calculates the MP4 SHA-256 digest.
4. Determines whether the video was previously recorded in publication history.
5. Builds a redacted publishing payload.
6. Writes `output/part_001/video/publish/facebook_reels_dry_run.json`.
7. Updates `data/facebook_publish_history.json` with a `dry_run` record.
8. Prints a readable summary.

## Facebook Reels preflight profile

The preflight helper checks:
- file exists and is non-empty
- resolution is 1080 x 1920
- frame rate is 30/1
- video codec is `h264`
- audio codec is `aac`
- audio sample rate is `48000` Hz
- audio channel count is stereo
- audio bitrate is at least `128000`
- video duration is positive

## Publication history

The JSON file stores:
- Part number
- video file name
- content SHA-256
- title and description
- status
- Meta Graph API version
- Meta video ID (nullable)
- Meta post ID (nullable)
- upload phase
- errors
- created and published timestamps

Example empty history:

```json
{
  "schema_version": 1,
  "records": []
}
```

History writes are atomic. A malformed JSON file is reported rather than silently reset.

## Duplicate prevention

Before a real publication is attempted in a later phase, Phase 1 supports:
- checking the same content SHA-256 and Part number
- detecting an existing publication record
- preserving prior records

Real Facebook API calls are not implemented in Phase 1.

## Configuration

Environment variables:
- `META_GRAPH_API_VERSION` — defaults to `v26.0`
- `META_PUBLISH_TIMEOUT_SECONDS` — defaults to `120`
- `FACEBOOK_PUBLISH_ENABLED` — defaults to `false`
- `FACEBOOK_PUBLISH_DRY_RUN` — defaults to `true`
- `META_PAGE_ID` — optional in dry-run mode
- `META_PAGE_ACCESS_TOKEN` — optional in dry-run mode

Do not add credentials to tracked files. Store credentials in GitHub Secrets.

## Security notes

- No Meta HTTP request is performed in Phase 1.
- No access token is logged.
- Secrets are loaded from environment variables only.
- The payload preview redacts the access token.
- The generated MP4 is never modified by the publisher.

## Current limitations

- Real Facebook network publishing is intentionally disabled.
- MP4 codec/sample-rate compatibility must be verified against actual HyperFrames renders.
- Token validation and duplicate reconciliation are interface-ready but live Meta calls are not implemented.
- No performance-based schedule optimization is implemented.
