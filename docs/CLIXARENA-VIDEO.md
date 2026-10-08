# Manual CLIXARENA video workflow

## Preview before full encoding

`sample_only` is checked by default on Run workflow. It encodes up to the first 180 seconds using the same subtitles and watermark, then publishes `preview/sample.mp4` as the `CLIXARENA-sample` run artifact (retained 3 days). Open the completed run's Summary, scroll to Artifacts, download and extract CLIXARENA-sample, then play sample.mp4. Inspect Sinhala text from 01:18 for the supplied subtitle file. Streamtape secrets are not required for sample mode and nothing is uploaded to Streamtape. The full source video is still downloaded; this option saves encoding time, not download bandwidth. The sample is accessible to people with run artifact access.

After inspecting the sample, start another manual run with `sample_only` unchecked to encode and upload the full video. No run is started automatically.

Copy `.github/workflows/clixarena-video.yml`, `scripts/clixarena_video.py` and this document into the repository, preserving paths. Merge the workflow into the default branch so the Run workflow button appears. This package was prepared without repository access; check for existing files and repository instructions before merging.

Under Settings > Secrets and variables > Actions, create repository secrets `STREAMTAPE_LOGIN` and `STREAMTAPE_KEY`. Never put their values in YAML, code, dispatch inputs or screenshots.

Set `output_name` on Run workflow to your desired filename, for example `My Movie 2026.mp4`. The `.mp4` suffix is added if omitted. Sinhala names and spaces are supported; path separators, control characters and invalid filename characters are rejected. After direct upload and verification, the workflow renames the video through Streamtape's `/file/rename` API using an encoded POST body. The temporary runner file uses a fixed name for safety. If renaming fails, the upload already exists in Streamtape: check your account and rename it there instead of rerunning and creating a duplicate.

Upload your Unicode UTF-8 Sinhala SRT as `subtitles/sinhala.srt` and your licensed Iskoola Pota TTF as `fonts/IskoolaPota.ttf`. Those files must exist on the branch selected for the run. The package includes neither a font nor a subtitle. Only commit a proprietary font if its license permits repository redistribution, especially for public repositories.

Open Actions > CLIXARENA video encode and upload > Run workflow. Provide the direct HTTPS video URL. Keep the default `subtitle_path` and `font_path`, or enter your actual repository paths (case-sensitive on Linux), then click Run workflow. No run is triggered by uploading these files. Missing assets, paths outside the checkout, invalid family, non-Sinhala/invalid subtitle or missing secrets fails before downloading the video. Assets are copied to fixed temporary paths before FFmpeg runs.

Dispatch inputs are retained by GitHub and accessible to repository users. Log masking does not make them secrets. Do not enter confidential signed video URLs here; use non-sensitive links, or adapt VIDEO_URL to a repository secret for confidential sources. Downloads validate public HTTPS hosts and each redirect; use trusted hosts (DNS validation alone is not a complete defense against DNS rebinding). No credentials are sent to input URLs. URLs and asset paths never enter shell expressions or FFmpeg filters.

The result is MP4 with H.264 (CRF 23, fast preset, yuv420p), AAC 128 kbps when audio exists, original resolution rounded to even dimensions, Iskoola Pota subtitles and a small bold bottom-left CLIXARENA watermark in DejaVu Sans Bold. Watermark opacity is 55%, font size is video height / 44, left margin is width / 136 and bottom margin is height / 38, approximating the supplied screenshot at different resolutions. Silent sources remain silent. Sinhala shaping should be visually checked on a short authorized sample before a full movie run.

The runner holds downloads and output temporarily; no video/font artifacts are published to GitHub. The job has a 350-minute limit, a 12 GiB source limit and disk checks. Large/high-resolution videos can exceed hosted-runner storage or time; use a suitable runner or reduce source size. Downloads/API calls are bounded and uploads are not automatically retried, to avoid duplicate files. If an upload times out or verification fails, check Streamtape before rerunning. The success log and job summary show the verified file link; Streamtape playback processing can still be pending. Step outputs are `file_id` and `video_url`.

Direct upload follows https://strtape.tech/api : POST credentials to `/file/ul`, stream the encoded file as multipart `file1` to the returned HTTPS upload URL, and verify `/file/info`. Raw API responses and exceptions are suppressed. Proprietary font licensing remains the operator's responsibility.

Validation of the delivered package is offline only: syntax and mocked failure/success cases. No real GitHub Actions run, licensed-font rendering or Streamtape upload is performed.
