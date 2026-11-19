# Changelog

## Unreleased

- Added a manual-only GitHub Actions workflow for one controlled **private** YouTube Shorts upload of the existing 5-question Reel, with presence-only secret checks, channel-ID verification, real ffprobe validation, duplicate protection, an explicit upload unlock flag, independent YouTube history persistence and safe reconciliation of uncertain uploads. No Facebook workflow or behavior changed.
- Added an independent, dry-run-only YouTube Shorts publisher that reuses the existing 5-question Facebook Reel. It adds ffprobe preflight, SHA-256 hashing, OAuth refresh handling, resumable `videos.insert` upload support (network disabled in this phase), separate YouTube publication history, redacted errors, CLI `--publish-youtube` support, tests and documentation. Facebook publishing and all existing video/TTS/question behaviour are unchanged.
- Added Philippine-related content to the global knowledge bank: 20 verified Philippine facts,
  5 verified Philippine natural features (Mount Apo 2,954 m, Mayon Volcano 2,462 m, Mount
  Hamiguitan 1,637 m, the Puerto Princesa Subterranean River, Tubbataha Reefs Natural Park),
  and 48 curated questions on national symbols, history, geography, culture, cuisine, sports,
  government and UNESCO sites. The Philippine count in the bank rose from about 930 to about 4,770,
  so a refreshed Philippine question appears roughly once every 1–3 Parts; the Part remains an
  international quiz.
- The provenance of every added claim is recorded in `docs/PHILIPPINE_CONTENT_SOURCES.md`.

- Fixed the scheduled workflow failing with "No unused questions remain for these filters". The question bank now holds about 112,000 questions instead of 121, and when the unused pool still runs dry the questions used longest ago are recycled instead of aborting the run.
- A Part now keeps its general-knowledge character: the target is 13 single-entity questions and 2 comparison questions, with an absolute maximum of 4 comparisons. When the fresh single-entity questions run out they are recycled, least recently used first, instead of the Part turning into comparison questions only.
- `data/used_questions.json` keeps `used_ids` in recency order: a question that is used again moves to the end, so recycling rotates instead of repeating the same questions. The file format is unchanged and existing history files keep working.
- Question quality fixes: the country Georgia and the US state Georgia no longer generate the same question; ambiguous country and field questions are skipped unless the seed supports one answer; the historical facts each name the specific fact they hold; measurements carry their unit; and the questions that repeated a fact (largest city equal to the capital, a region equal to the city name, the atomic number equal to the proton count, and the inverse country questions) are no longer produced.
- Factual corrections with sources: the Chinese language family is Sino-Tibetan, Bolivia's largest city is Santa Cruz de la Sierra, Bolivia's constitutional capital (Sucre) and its seat of government (La Paz) are asked separately, and the Sahara area is given as about 9,000,000 square kilometres.
- Added `tests/test_question_bank_content.py`, which checks the raw generated questions before any deduplication, so a question can never hide two different answers.
- The question bank is now built from the curated questions in `data/questions.json` plus questions generated at run time from the verified seed facts in `data/seeds/` (countries, elements, US states, cities, natural features, dated facts, languages).
- A Part now draws one question per question family before it takes a second from any family, so a Part mixes capitals, elements, comparisons and history instead of repeating one question shape.
- The production narrator is now Kokoro `af_bella` instead of `af_heart`. The Kokoro engine is unchanged; the integration now sends the configured speaking speed and requests a short pause between sentences, and the workflows set `KOKORO_VOICE: "af_bella"`.
- The 10-question Page Video now keeps each question on screen through its countdown and its correct-answer reveal, and replaces it only when the next question starts. The 15-question full video is unchanged.
- The 10-question outro is larger and re-centred: the main ending line is 92px in the middle of the frame, the call-to-action pill is 42px on one line, and the Part badge no longer overlaps the ending text.
- Narration is about 8% slower (`speed=0.92`) for the 10-question Page Video and the 15-question full video; the Reel keeps 1.00 to help meet Meta's 90-second Reel limit. The actual rendered Reel duration still needs validation.
- Narration now asks for a short pause between sentences, so the spoken "Question N, easy." label does not run into the question.
- Documented the TTS voice comparison in `tts_samples/SAMPLES.md`, covering Kokoro `af_heart`, Kokoro `af_bella` and two Piper voices, with the measured durations and the licensing notes. The production engine is unchanged.
- Corrected the scheduled Facebook publishing times to 6:00 PM and 12:00 AM Philippine Time. Manual workflow dispatches now require an explicit `confirm_live_publish` selection before checking Meta secrets or publishing; scheduled runs retain automatic publishing.

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
- Moved the 10-question tracker to the left and separated the quiz layout to prevent overlap.
- Added opening hook and closing call-to-action overlays to the 10-question format.
- Scheduled publishing now targets the 10-question Facebook Page Video instead of the 5-question Reel.
- Redesigned the 10-question composition into a two-column answer board (10 numbered slots) with a branded header, difficulty pill, countdown timer bar, and no mascot.
- Replaced the big centered answer card in the 10-question format with the answer revealed inside its numbered slot; earlier answers stay on screen until the quiz ends.
- Enlarged the closing call to action into a "COMMENT YOUR SCORE OUT OF 10" pill with a share/follow sub-line.
- Removed the stale `actions/cache` step for `data/used_questions.json`; the cached copy overwrote the committed history and kept every scheduled run regenerating the same Part.
- Lowered the preflight audio-bitrate floor to 50000 bps (a narration track measures ~95 kbps, a track without narration ~13 kbps) and fixed the misleading error message.
- Failed Facebook publications now exit non-zero so a silent publish failure cannot look like a green workflow run.
- Narration is now generated one clip per intro/outro line, so every on-screen line is spoken and appears exactly when it is said.
- The spoken script now covers the "QUESTION N" label and the difficulty badge, the challenge hook, and the closing call to action.
- Rewrote the intro and outro lines to be speakable ("Welcome to the World General Knowledge Quiz!", "How did you do?") and aligned the SRT subtitles with the spoken script.
- The Reel keeps a single intro and outro clip, and speaks the bare question text, so it stays inside Meta's 90 second Reel limit.
- `ffprobe` failures while measuring narration length now raise a clear error instead of crashing the generation.
