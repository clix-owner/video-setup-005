# Download progress update — 2026.10.20

Copy every file from scripts/ into the existing GitHub repository scripts/ folder, replacing matching files, then commit and push. No UI redeploy or new secrets. Only new runs use the update.

Includes the previous upload telemetry/wait-reduction update.

Direct HTTPS, resolved Google Drive and range-parallel downloads emit progress every 10 seconds: percentage when Content-Length is known, received/total MiB, average MiB/s, elapsed time, estimated remaining time and selected connections. Unknown-size downloads show bytes and speed without invented percentages or ETA. A heartbeat continues when data stalls. Parallel ranges aggregate downloaded bytes, resetting a retried range instead of double-counting it. Completion is printed only after download byte/range checks pass; video validation follows separately. Torrent downloads retain their existing libtorrent progress logs.

Only fixed text and numbers are logged. URLs, headers, tokens, file names and remote exception text are not printed by the new progress helper.

Includes regression tests for single-stream completion, incomplete transfers, unknown sizes, stalled heartbeats and parallel retry accounting. No remote media was downloaded and no Actions run was triggered for this update.
