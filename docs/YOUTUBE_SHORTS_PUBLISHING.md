# YouTube Publishing

This project has two independent, **private-only** YouTube formats:

| Format | Content type | Source video | Part sequence |
|---|---|---|---|
| Shorts (legacy 5-question Reel) | `youtube_shorts` | `output/youtube/part_NNN/youtube/shorts/world_general_knowledge_quiz_part_NNN.mp4` | YouTube-only |
| 10-question video (current) | `youtube_ten_question_video` | `output/youtube/part_NNN/youtube/videos/world_general_knowledge_quiz_part_NNN_10_questions.mp4` | YouTube-only, per content type |

Ordinary local execution is dry-run only: no token is exchanged and no history is written.
The manual workflow performs one controlled **private** test upload. Facebook publishing is
unchanged.

## Source videos and preflight

- Shorts: `core.youtube_output.youtube_shorts_path()`; generated with
  `--render-reels --youtube-shorts --output-root output/youtube`.
- 10-question video: `core.youtube_output.youtube_ten_question_video_path()`; generated with
  the existing Facebook tracker pipeline
  (`--count 10 --render-ten-video --youtube-ten-question-video --output-root output/youtube`).
  Composition projects live under `output/youtube/hyperframes/part_NNN/videos/`.
- Facebook keeps its existing `output/part_NNN/facebook/` layout; no `facebook/` directory is
  created under the YouTube root. `--output-root` defaults to the existing Facebook root.
- ffprobe checks for both: non-empty file, 1080×1920 (9:16), 30 FPS, H.264 video, AAC audio,
  both streams present, positive duration. The **180-second limit applies only to Shorts**;
  the 10-question video has no Shorts duration cap. The workflow prints the measured duration
  and notes that YouTube may classify vertical videos up to three minutes as Shorts.
- Specifications must be measured from a generated artifact; no actual MP4 is inspected here.

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

- Shorts title: `World General Knowledge Quiz - Part N #shorts`; description with `#Shorts`
  hashtags and a `Content hash: <sha256>` marker; tags `shorts`, `general knowledge`, `trivia`,
  `quiz` (legacy behavior, unchanged).
- 10-question video title: `World General Knowledge Quiz | Part NNN | 10 Questions`;
  description explains the 10-question quiz, asks viewers to comment their score out of 10,
  and carries the same content-hash marker; tags `general knowledge`, `quiz`, `trivia`,
  `education`, `10 questions`. **No `#Shorts` branding** in the new format.
- Category: `27` (Education) by default.
- Privacy: explicitly set; only `private` and `unlisted` are accepted in this phase. Public
  uploads are intentionally unavailable until a later approved phase.

## Dry-run process

```powershell
python main.py --publish-youtube --part 12 --output-root output/youtube          # Shorts
python main.py --publish-youtube-video --part 1 --output-root output/youtube     # 10-question video
```

Each command locates its own MP4 via the shared resolver, runs ffprobe preflight, computes the SHA-256 hash, checks the
YouTube history for an existing matching upload, builds and validates the metadata, and prints
a report. It performs **zero HTTP requests**, creates no video, and writes no history record.
`--youtube-privacy private|unlisted` overrides the privacy shown in the report;
`--youtube-dry-run` is accepted but dry-run is already the default.

If `YOUTUBE_PUBLISH_ENABLED=true` and `YOUTUBE_PUBLISH_DRY_RUN=false`, the CLI fails closed
with an error instead of attempting a network upload.

## Duplicate prevention and failure recovery

1. Compute the MP4 SHA-256 hash.
2. Look for a YouTube history record with the same Part, hash **and content type**
   (`youtube_shorts` or `youtube_ten_question_video`). A Shorts upload never blocks a different
   10-question video for the same Part.
3. Skip a Part whose matching upload of that content type is already `uploaded` or `uploading`.
4. Never blindly retry an upload with an uncertain result; a `uploading` record or a lost
   resumable session (HTTP 404/410) requires manual reconciliation using the content-hash
   marker in YouTube metadata.
5. Resumable sessions use bounded 8 MiB chunks (256 KiB multiples), handle HTTP 308 with the
   `Range` header, and reject a session that makes no progress.

`data/youtube_publish_history.json` is entirely separate from
`data/facebook_publish_history.json` and `data/used_questions.json`. Its schema is
`{"schema_version": 1, "records": []}`; records carry Part number, video file name, content
hash, `content_type` (`youtube_shorts` or `youtube_ten_question_video`), title, YouTube video ID, `upload_status`
(`dry_run`/`uploading`/`uploaded`/`failed`), privacy status, timestamps and redacted errors.
Writes are atomic; malformed history raises instead of being reset. Credential-named keys and
session URLs are stripped before a record is saved.

## Manual private test upload

Use **YouTube 10-Question Video Test Upload (Private)**, dispatched manually from the Actions
tab (no cron, push or PR trigger). The legacy Shorts workflow behavior is described below for
backward compatibility; the workflow now targets the 10-question tracker format.

1. Set `part_number`, or `0` to let
   `next_youtube_part_number(content_type="youtube_ten_question_video")` choose the Part.
   Numbering is per content type and independent of Facebook: Part 1 is available for the
   10-question video even though Part 1 already has an uploaded Short (`yEgHXZc2Gls`). The
   existing failed Part 25 and uploaded Part 26 Shorts records stay untouched. A failed attempt
   without a video ID does not consume a number.
2. Presence-only checks confirm all four secrets are configured (names only, never values).
3. The path comes from `youtube_ten_question_video_path()`. If that exact file exists it is
   reused; otherwise the workflow generates exactly 10 questions with the Facebook tracker
   pipeline: `--count 10 --render-ten-video --ten-question-count 10
   --youtube-ten-question-video --output-root output/youtube`. The ffprobe step also reads the
   associated `script.json` and requires exactly 10 questions, then prints the measured
   duration and the possible Shorts-classification caveat.
4. It runs `--publish-youtube-video` (zero HTTP), then `--youtube-video-upload`. Both use the
   same resolver and `--output-root output/youtube`. Privacy is forced to `private` in
   `main.py`; there is no public/unlisted path.
5. Network uploads are unlocked only by `YOUTUBE_ALLOW_NETWORK_UPLOAD=true` in the upload step.

Legacy Shorts commands (`--publish-youtube`, `--youtube-upload` with `--youtube-shorts`
generation) remain available and still use `youtube_shorts_path()` and `youtube_shorts`
history records.

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
failure is recorded as `failed` and is safe to retry with the same Part.

### Question history

`data/used_questions.json` stays global and is never reset or rewritten. YouTube Part numbers
are metadata only: `record_question_usage()` keeps the maximum existing `last_part`, so a
YouTube Part 1 cannot lower Facebook's Part counter. Questions used by a YouTube Short are
recorded as used, preserving the global no-repeat behavior for both platforms.

After a successful test upload, open **YouTube Studio → Content** to see the video. For the
10-question format, check that the script contains 10 questions, that the privacy badge says
**Private**, and note whether YouTube displays it as a Short (vertical videos up to three
minutes may be classified that way automatically). The video ID in the workflow log and
history record can be used to open it directly. Do not alter the video design to influence
classification.

## Token expiry and revocation

- If the OAuth consent screen is in Testing, refresh tokens expire after about seven days;
  unattended scheduled publishing requires a production/verified configuration.
- Changing scopes requires re-consent. Revoking access invalidates the refresh token; replace
  the GitHub Secret and re-authorize before enabling scheduled publishing.
- A 403 quota or permission error is reported with status/reason; no token value is logged.

## Scheduled public publishing

The existing scheduled Facebook workflow now also publishes the 10-question YouTube video at
the same times:

- `0 10 * * *` — 18:00 PHT (6 PM)
- `0 16 * * *` — 00:00 PHT (12 AM)

The YouTube steps live in the **same job** as Facebook generation (`world-quiz-generation`
concurrency group; the manual test workflow uses that group too), so both platforms update
`data/used_questions.json` sequentially on one runner. Scheduled generation uses exactly
`--count 10` with the existing tracker flags and `--output-root output/youtube`, and resolves
its Part via `next_youtube_part_number(content_type="youtube_ten_question_video")`.

Scheduled uploads set `YOUTUBE_PRIVACY_STATUS=public`, `YOUTUBE_ALLOW_NETWORK_UPLOAD=true` and
`YOUTUBE_ALLOW_PUBLIC_UPLOAD=true`, then call
`main.py --youtube-video-upload --youtube-scheduled-upload`. The CLI requires the explicit
public unlock and `YOUTUBE_PRIVACY_STATUS=public` before the publisher will allow a public
upload. The manual test workflow never sets the public unlock and always forces `private`;
it remains manual-only.

The final always-run step persists both `data/used_questions.json` and
`data/youtube_publish_history.json` after `git fetch` + `git rebase origin/main`, staging only
those two paths, with no force push. Existing history records are never reset.

## Current limitations

- Public uploads are limited to the two scheduled daily runs with an explicit unlock flag;
  there is no manual public path.
- A Part 1 Shorts video (`yEgHXZc2Gls`) and a Part 26 Shorts video (`c22bxuuTvd8`) were
  previously uploaded privately. The new 10-question workflow has not been used yet.
- Consent-screen verification and ongoing scheduled publishing remain owner-controlled and
  out of scope for this repository change.
- The four YouTube secrets must already exist in GitHub; a missing `YOUTUBE_CHANNEL_ID`
  stops the workflow before generation or upload.
