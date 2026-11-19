# YouTube Shorts Publishing — Phase 2.7.1 (Dry-Run Foundation)

This phase adds an **independent** YouTube Shorts publisher. It reuses the existing
5-question Facebook Reel MP4. Ordinary local execution is dry-run only: no video is uploaded,
no token is exchanged and no history is written. A separate manual workflow can perform one
controlled **private** test upload. Facebook publishing is unchanged.

## Source video and preflight

- Source: `output/part_NNN/facebook/reels/world_general_knowledge_quiz_part_NNN_reel.mp4`
  (the same MP4 the Facebook Reel publisher uses).
- No second renderer is introduced. Question count, narration, Kokoro `af_bella`, TTS speed,
  countdown, SFX, subtitles and visual design are untouched.
- ffprobe preflight checks: file exists and is non-empty, resolution 1080×1920, aspect ratio
  9:16, frame rate 30/1, video codec H.264, audio codec AAC, an audio stream is present,
  duration is greater than zero and at most 180 seconds (YouTube Shorts limit).
- Actual MP4 specifications must be measured from a generated artifact before assuming any
  result; this phase does not claim a rendered file was inspected.

## Existing GitHub Secrets and environment mapping

The credentials have already been added to GitHub Secrets by the user. The future workflow
will map them into these environment-variable names (no values are stored in the repository):

| Secret / environment variable | Purpose |
|---|---|
| `YOUTUBE_CLIENT_ID` | OAuth client ID |
| `YOUTUBE_CLIENT_SECRET` | OAuth client secret |
| `YOUTUBE_REFRESH_TOKEN` | Long-lived refresh token for unattended publishing |
| `YOUTUBE_CHANNEL_ID` | Optional, channel verification only |

Runtime flags in `config.py`: `YOUTUBE_PUBLISH_ENABLED` (default `false`),
`YOUTUBE_PUBLISH_DRY_RUN` (default `true`), `YOUTUBE_PRIVACY_STATUS` (default `private`),
`YOUTUBE_CATEGORY_ID` (default `27`, Education), `YOUTUBE_CHANNEL_ID`.

## OAuth requirements

- Scope: `https://www.googleapis.com/auth/youtube.upload` only.
- Token endpoint: `https://oauth2.googleapis.com/token` with `grant_type=refresh_token`.
- Access tokens are held in memory only. No access token, refresh token, client secret or
  resumable upload session URL is written to disk or to any JSON history file.
- Errors and logs redact all configured secrets and the active session URL.

## Channel verification

The refresh token is bound to the Google account that authorized it. Channel verification is
not performed during dry-run. A later phase will compare the `snippet.channelId` returned by a
private test upload against `YOUTUBE_CHANNEL_ID` (if configured) and stop on mismatch. Note that
`channels.list?mine=true` would require the additional `youtube.readonly` scope, so it is not
used by the minimum-scope upload client.

## Metadata configuration

- Title: `World General Knowledge Quiz - Part N #shorts` (max 100 characters).
- Description: Part number, call to action, `#Shorts` hashtags, and a deterministic
  `Content hash: <sha256>` marker used to reconcile interrupted operations.
- Tags: `shorts`, `general knowledge`, `trivia`, `quiz` (500-character total limit).
- Category: `27` (Education) by default.
- Privacy: explicitly set; only `private` and `unlisted` are accepted in this phase. Public
  uploads are intentionally unavailable until a later approved phase.

## Dry-run process

```powershell
python main.py --publish-youtube --part 12
```

The command locates the Reel, runs ffprobe preflight, computes the SHA-256 hash, checks the
YouTube history for an existing matching upload, builds and validates the metadata, and prints
a report. It performs **zero HTTP requests**, creates no video, and writes no history record.
`--youtube-privacy private|unlisted` overrides the privacy shown in the report;
`--youtube-dry-run` is accepted but dry-run is already the default.

If `YOUTUBE_PUBLISH_ENABLED=true` and `YOUTUBE_PUBLISH_DRY_RUN=false`, the CLI fails closed
with an error instead of attempting a network upload.

## Duplicate prevention and failure recovery

1. Compute the MP4 SHA-256 hash.
2. Look for a YouTube history record with the same Part, hash and `youtube_shorts` type.
3. Skip a Part whose matching upload is already `uploaded` or still `uploading`.
4. Never blindly retry an upload with an uncertain result; a `uploading` record or a lost
   resumable session (HTTP 404/410) requires manual reconciliation using the content-hash
   marker in YouTube metadata.
5. Resumable sessions use bounded 8 MiB chunks (256 KiB multiples), handle HTTP 308 with the
   `Range` header, and reject a session that makes no progress.

`data/youtube_publish_history.json` is entirely separate from
`data/facebook_publish_history.json` and `data/used_questions.json`. Its schema is
`{"schema_version": 1, "records": []}`; records carry Part number, video file name, content
hash, `content_type: youtube_shorts`, title, YouTube video ID, `upload_status`
(`dry_run`/`uploading`/`uploaded`/`failed`), privacy status, timestamps and redacted errors.
Writes are atomic; malformed history raises instead of being reset. Credential-named keys and
session URLs are stripped before a record is saved.

## Manual private test upload

Use the separate workflow **YouTube Shorts Test Upload (Private)**, dispatched manually from
the Actions tab (no cron, push or PR trigger):

1. Set `part_number` to a positive Part number, or `0` to use the repository's existing
   `next_part_number()` convention.
2. The workflow first checks that all four secrets are present (names only, never values).
3. It generates exactly one Part's 5-question Reel with the existing pipeline
   (`python main.py --part N --tts --render-reels --reels-question-count 5`), then measures the
   actual MP4 with ffprobe. The normal question-history commit for that Part is written by
   the generation step, exactly as in the Facebook workflows.
4. It runs the zero-HTTP dry-run, then performs one controlled upload. Privacy is hardcoded to
   `private` in `main.py`; the workflow has no privacy input and no public/unlisted path.
5. Network uploads are unlocked only by `YOUTUBE_ALLOW_NETWORK_UPLOAD=true` in that one step.
   Local runs remain dry-run unless someone explicitly sets that flag.

Metadata for the test upload: title `World General Knowledge Quiz | Part NNN #Shorts`, the
short quiz description with the content-hash marker, tags `shorts`/`general knowledge`/
`trivia`/`quiz`, category `27` (Education).

### Channel verification

The workflow maps `YOUTUBE_CHANNEL_ID` into the uploader. After `videos.insert`, the returned
`snippet.channelId` must match the configured ID exactly. On mismatch the upload is recorded
as `failed` (with the returned video ID preserved for diagnosis), no further upload is
attempted, and manual reconciliation is required. Holding a refresh token alone does not
prove authorization for the intended channel.

### History persistence and recovery

A single always-run persistence step commits both `data/used_questions.json` (changed by the
successful generation step) and `data/youtube_publish_history.json` (`[skip ci]`), after
`git fetch` + `git rebase origin/main`; there is no force push. A generated Part consumes its
questions even if a later validation or upload step fails, so its question history is never
lost with the runner. An ambiguous upload
(session loss, network error, HTTP 5xx/408/429) is recorded as `uploading` and blocks any
automatic retry. To reconcile, find the video in YouTube Studio using the `Content hash:`
marker in its description, then add the `youtube_video_id` and set `upload_status` to
`uploaded` by hand only after confirming the correct channel and privacy. A definitive 4xx
failure is recorded as `failed` and is safe to retry with a fresh Part/hash.

After a successful test upload, open **YouTube Studio → Content** to see the video, confirm it
is listed as a Short (vertical 9:16 video up to three minutes is classified as a Short), and
check its privacy badge says **Private**. The video ID in the workflow log and history record
can be used to open it directly.

## Token expiry and revocation

- If the OAuth consent screen is in Testing, refresh tokens expire after about seven days;
  unattended scheduled publishing requires a production/verified configuration.
- Changing scopes requires re-consent. Revoking access invalidates the refresh token; replace
  the GitHub Secret and re-authorize before enabling scheduled publishing.
- A 403 quota or permission error is reported with status/reason; no token value is logged.

## Current limitations

- The only network path is the manual private workflow; there is no schedule and no public
  upload path.
- No actual YouTube upload, channel verification or consent-screen validation has occurred
  yet; the workflow is prepared but has not been dispatched.
- The four YouTube secrets must already exist in GitHub; a missing `YOUTUBE_CHANNEL_ID`
  stops the workflow before generation or upload.
