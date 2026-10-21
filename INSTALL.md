# Half-hour mapping sync update

This is a patch for the existing video-setup repository, not a replacement project.
Copy `.github/workflows/clixarena-mapping-sync.yml` and `scripts/clixarena_mapping_sync.py` to the same paths in video-setup and commit/push to the default branch. Preserve all other project files and mappings.json. The tests folder is optional. No Vercel/HF redeploy is required.

Repository Actions secrets:

- MAPPING_PASSWORD: existing mapping encryption password, unchanged.
- STREAMTAPE_LOGIN and STREAMTAPE_KEY: existing Streamtape account credentials.
- STREAMHG_API_KEY: existing StreamHG account API key.
- ABYSS_API_KEY: existing Abyss account API key.

The workflow uses the built-in GitHub token with Contents write permission, so no extra personal token is needed. Repository/organization policies must allow this permission. The script imports existing `clixarena_video.py` and `clixarena_hosts.py`; keep those project files.

Schedule: minute 7 and 37 of every hour (UTC). GitHub scheduling may run late; it is not an exact real-time timer. Scheduled workflows run from the default branch and GitHub may disable schedules in inactive public repositories. Manual dispatch is also available; this patch has not triggered any run.

Behavior:

- Read/decrypt the current GitHub mappings.json, check unique file IDs in all three mapped providers, and save changes encrypted with the same password.
- No uploads, video deletions, transcoding or title matching by filename. Unmapped account videos cannot be assigned TMDB/MAL IDs automatically.
- Current providers records and legacy file_id/abyss_id/streamhg_id are supported.
- Remove a host reference only after two explicit missing-file results, five seconds apart. Remove the title row only when no provider references remain. Preserve names, identity fields, subtitle URLs, other metadata and surviving providers.
- Streamtape: file/info individual integer status 404 under a successful response.
- StreamHG: file/info successful outer status and an explicit matching file_code with individual integer status 404. Omitted IDs or non-playable/transcoding states are not deletion evidence.
- Abyss: first verify account identity using authenticated /v1/about, then require two file-specific JSON HTTP 404 responses from /v1/files/:id with an explicit file/video-not-found message. A generic 404 page is not sufficient. Uses the project's existing key query authentication. If the account API response schema or authentication differs, this adapter preserves every Abyss mapping and marks the sync incomplete; it never guesses that videos were deleted.
- Authentication failures, timeouts, rate limits, malformed responses or missing credentials preserve all mappings for that provider. Other successfully checked providers may still sync. An incomplete host check makes the workflow fail visibly instead of pretending success.
- Concurrent mapping writes are protected using the GitHub file SHA. On conflict the script reloads the newest mapping and rechecks providers before trying again.
- Logs contain counts and fixed warnings, not file IDs, media URLs, credentials or raw provider errors.

Validation uses mocked provider responses, including authentication failures, missing files, temporary errors and multiple hosts. No live authenticated host verification has been performed. Keep the first scheduled run's fixed stage warnings if an adapter needs adjustment to an account's API format; do not share keys or raw private responses.
