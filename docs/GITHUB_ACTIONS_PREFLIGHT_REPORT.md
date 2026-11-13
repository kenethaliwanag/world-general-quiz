# GitHub Actions Pre-Flight Audit Report

## 1. Overall readiness

The project is structurally ready for a pre-flight GitHub Actions test, with one known high-risk area: persistent question history.

The workflows follow the intended runner model:
- Linux GitHub-hosted runners
- Python 3.12
- Node.js 20
- FFmpeg
- Global HyperFrames 0.9.20
- Native Kokoro-FastAPI on the runner's localhost interface
- per-Part artifacts uploaded after generation

No source-code changes were made during this audit. No full render was performed.

### Readiness summary

| Area | Status |
|---|---:|
| YAML workflow structure | pass, manual review |
| Workflow triggers | configured |
| CLI argument mapping | correct with minor remarks |
| Kokoro API compatibility | compatible |
| MP4 validation logic | valid |
| Artifact path alignment | valid |
| Least-privilege permissions | acceptable |
| Question-history persistence | high risk |
| Resource/cost estimation | documented |

## 2. Workflow audit findings

### 2.1 `validate-world-quiz.yml`

Validated command:
```text
python main.py --count 2 --category all --difficulty all --reset-history
npx hyperframes check output/hyperframes/part_001
```

Findings:
- The commands match the current CLI.
- `--reset-history` ensures each validation job starts from the committed repository state.
- The validation job installs HyperFrames 0.9.20 and runs HyperFrames runtime checks without rendering.
- The job runs on Ubuntu and installs FFmpeg.
- The `paths` triggers are limited to relevant source and data files.

Observations:
- No local PyYAML parser was available in this Windows environment, so YAML validation was performed by structural inspection only.
- Workflow action versions are specified by semantic version, not exact commit SHA. This is acceptable but can be hardened.
- Validation paths do not include documentation-only changes, which is appropriate.
- The `npm packages` step is absent from the validation workflow, preventing a typo from being caught.

### 2.2 `generate-world-quiz-videos.yml`

Findings:
- Manual inputs exist for starting Part, total Parts, question count, category, difficulty, TTS, and rendering.
- `--start-part 0` correctly maps to automatic next-Part selection after the source change in `main.py`.
- The workflow uses `actions/cache@v4` for history, HyperFrames browser cache, and uv cache.
- The workflow installs the Kokoro model and binds it to `127.0.0.1:8880`.
- HyperFrames rendering and artifact upload occur in the same job.
- MP4 validation checks resolution, frame rate, and duration.

Potential issues:
- Input values are interpolated directly into Bash commands. GitHub workflow inputs should be passed as environment variables to avoid injection risks.
- The Kokoro health-check loop uses `seq 1 180` and `sleep 2`, giving a maximum wait of six minutes.
- The remove-only step labeled "Install npm packages only when Kokoro setup is skipped" does not install any package and is confusing.
- `if: ${{ inputs.enable_render == true }}` should be verified against GitHub boolean input semantics before first production execution.
- The HyperFrames command uses the default GPU selection. In a cloud CPU-only workflow, this may still auto-detect software rendering, but adding `--no-browser-gpu` would make the setting explicit.
- The artifact path `output/**` includes HyperFrames project files. That is useful, but size should be monitored.

### 2.3 `scheduled-world-quiz-videos.yml`

Findings:
- Cron schedule is `0 8 * * 6`, meaning Saturday at 08:00 UTC.
- Quantity and TTS/render flags have sensible defaults.
- Scheduled workflow requests no additional permissions.
- Concurrency uses the same group as manual generation, preventing overlap.

Potential issues:
- The step condition:
  ```yaml
  if: ${{ inputs.enable_tts || true }}
  ```
  always starts Kokoro, even if TTS is disabled.
- `actions/cache@v4` with `save-always: true` can preserve updated question history, but GitHub cache retention is not permanent.
- As with the manual workflow, shell interpolation should be converted to environment variables.
- Model download time can consume most of the workflow duration on a clean run.

## 3. Kokoro compatibility findings

### API contract compatibility

The application's current implementation is compatible with `remsky/Kokoro-FastAPI` v0.9.2.

| Application requirement | Kokoro-FastAPI support |
|---|---|
| `POST /v1/audio/speech` | supported |
| `model: kokoro` | supported |
| `input` | supported |
| `voice: af_bella` | supported (`api/src/voices/v1_0/af_bella.pt` ships with the tag) |
| `response_format: mp3` | supported |
| `speed: 0.92` (0.25-4.0) | supported |
| `voice` listed via model endpoint | supported |
| no API key needed | supported by default |
| 30-second timeout per clip | supported |
| localhost operation | supported |

### Workflow findings

- The runner downloads `remsky/Kokoro-FastAPI` at tag `v0.9.2`.
- The runner installs CPU dependencies with `uv sync --frozen --extra cpu`.
- The service is launched with Uvicorn on `127.0.0.1:8880`.
- API log verbosity is reduced to `WARNING`.
- TTS generation cannot begin until `/health` and `/v1/models` pass.
- The service is automatically terminated when the runner job ends.
- The local application sends requests to `http://127.0.0.1:8880` via `KOKORO_BASE_URL`.
- Output audio is an MP3, matching `KOKORO_RESPONSE_FORMAT = "mp3"`.
- ffprobe validates cached audio after it is written.

### Concerns

- Third-party source is installed at workflow runtime rather than being pinned by immutable commit SHA.
- The service logs are not uploaded if startup fails.
- The first model download can be large and may vary in speed.
- The 180-second startup check can nearly consume the workflow timeout if Hugging Face access is congested.
- The server does not require authentication in this configuration. This is acceptable because it binds only to localhost.

## 4. Question-history persistence risks

This is the highest-risk area of the current cloud design.

### Current implementation

- `core/history_manager.py` stores history in `data/used_questions.json`.
- `core/question_manager.py` updates this file during question selection.
- Workflows restore and save the file with `actions/cache@v4`.
- `save-always: true` is requested.

### Audit results

- Multiple Parts in one workflow run share the same updated history because selection occurs in the same Python process.
- The concurrency group serializes manual and scheduled jobs, reducing simultaneous overwrites.
- A cache miss causes the application to start from the committed repository history, which is currently empty. This can lead to duplicate questions in a new daily run.
- A failed generation can still mark questions as used because `select_questions()` persists used IDs before export (or render) completes.
- GitHub cache entries are not guaranteed permanent. Entries can be evicted after approximately seven days without access or when quota limits are reached.
- Repository cache storage is limited; the expected history file itself is tiny, but saturation from other cache purposes can still result in evictions.

### Risk classification

- Severity: High
- Likelihood of history loss: Moderate
- Impact: duplicate question usage across different Parts or days

### Recommended persistence strategy

Short-term:
- retain the cache-backed approach
- extend workflows to upload `used_questions.json` as a small artifact named `question-history-${{ github.run_id }}`
- keep `save-always: true`

Medium-term:
- Store history in a dedicated GitHub Actions cache with a simple branch-keyed schema.
- Publish the final history as a timestamped workflow artifact.
- Add a workflow step to report cache hit/miss information in the job summary.

Long-term:
- Move persistent question history to a dedicated backend such as GitHub repository contents updated by a narrowly scoped bot, or an external datastore using repository secrets.
- Only allow automated history commits to a data branch managed by `contents: write`.
- Alternatively, migrate the question store to SQLite and protect the database with a storage backend.

Do not scale batch generation until this risk is resolved or accepted.

## 5. Artifact validation findings

### Expected output paths

The workflows upload:

```text
output/part_XXX/script.txt
output/part_XXX/script.json
output/part_XXX/subtitles/part_XXX.srt
output/part_XXX/narration/*
output/part_XXX/video/*
output/part_XXX/thumbnail/*
```

These match the current `script_exporter.export_quiz()` and `export_srt()` implementations.

### Audit results

- Paths are consistent with application output structure.
- MP4 validation checks resolution, frame rate, and duration.
- Artifact names are unique because they include `github.run_id`.
- Artifact retention is set to 30 days.
- `if-no-files-found: warn` prevents a workflow abort if generation is skipped, but it could allow a tacit success under malformed inputs.
- The `output/**` artifact glob also includes HyperFrames project files. This is useful for debugging but consumes more storage.
- Thumbnails are not currently generated explicitly, so only empty directories may be uploaded. This is acceptable because automatic thumbnail generation remains a future enhancement.

### Recommendations

- Add generated-file assertions before artifact upload:
  - at least one MP4
  - exactly 15 question count unless `--count` is intentionally different
  - every MP4 readable by ffprobe
- Upload Kokoro logs as artifacts when any job fails.
- Keep artifact retention at 30 days during experimentation.
- Later reduce retention to 7 days once video review is stable.

## 6. Estimated resource consumption

### Validation workflow

- Expected duration: 5 to 10 minutes
- Purpose: low-cost smoke test without full render
- No TTS server required

### Single Full Part

Estimated total: 20 to 60 minutes per Part.

Breakdown:
- Runner setup and cache: 2 to 5 minutes
- Python/Node installation: 1 to 2 minutes
- FFmpeg installation: 1 to 2 minutes
- Kokoro setup with cache: fewer than 5 minutes on cache hit
- Kokoro setup from scratch: 5 to 20 minutes
- TTS generation: 1 to 4 minutes
- HyperFrames rendering: 15 to 35 minutes
- MP4 validation and artifact upload: 1 to 3 minutes

### Single-Runner Batch Guidance

- Recommended maximum initial batch: 3 Parts
- Estimated clean-cache batch: 60 to 180 minutes
- Free private repository quota: 2,000 minutes per month
- A private repository generating one Part per day would consume approximately 600 to 1,200 monthly minutes.
- Public repositories have different unlimited standard-runner rules but may still impose practical runner availability constraints.

### Artifact storage

- Estimated per Part:
  - MP4: 8 to 16 MB
  - narration audio: 1 to 3 MB
  - scripts and subtitle files: under 1 MB
  - HyperFrames project: 2 to 6 MB
- Artifact retention: 30 days
- Artifact storage accounting should include `output/**`, not only the MP4.

### Kokoro and cache impact

- uv and pip dependencies can be large because PyTorch is included.
- Kokoro model files are approximately 327 MB or more depending on runtime versions.
- Cache hit rates will strongly influence run time and open-source network reliability.

## 7. Recommended fixes before first run

### High priority

1. Add explicit runner caching for the uv package cache if not already enabled by `astral-sh/setup-uv`.
2. Verify that `actions/cache@v4` with `save-always: true` saves updated history as expected.
3. Add an on-failure upload step for `/tmp/kokoro.log`.
4. Avoid directly expanding workflow inputs in Bash. Pass them through safe immutable environment variables.
5. Add pre-flight assertions that generated MP4 and SRT files are not empty.

### Medium priority

1. Pin all third-party action versions to exact commit SHAs rather than semantic version tags.
2. Add `--no-browser-gpu` to rendering for CPU-only cloud stability.
3. Test Kokoro startup using the same `v0.9.2` tag on a local Ubuntu VM before the first workflow run.
4. Add a cap of 2 Parts for the first scheduled run.
5. Record cache hit/miss information in the job summary.

### Low priority

1. Remove the no-op npm package step from the manual workflow.
2. Make the TTS no-op behavior in the scheduled workflow explicit instead of using `if: ${{ inputs.enable_tts || true }}`.
3. Add an artifact pattern that excludes large HyperFrames cache directories if output starts containing them unexpectedly.

## 8. First-run testing instructions

Use these settings for the first GitHub Actions run:

```text
start_part: 0
total_parts: 1
questions_per_part: 2
category: all
difficulty: all
enable_tts: true
enable_render: true
```

Before triggering it:
- confirm that `data/used_questions.json` is intentionally committed in its desired state
- confirm that repository secret permissions are not needed because local Kokoro remains localhost-only
- select a private repository only if required

After the run:
1. Inspect the workflow logs.
2. Confirm Kokoro started successfully and did not repeatedly hang.
3. Download the artifact.
4. Verify:
   - all MP4 files read with ffprobe
   - 1080x1920
   - 30 FPS
   - finite durations
   - SRT timing matches the spoken narration
   - no narration is truncated
5. Review `data/used_questions.json` cache behavior.
6. Run the validation workflow separately before adding any batch scheduling.

Do not proceed to a full 15-question render or scheduled run until the 2-question pre-flight run succeeds on GitHub Actions.