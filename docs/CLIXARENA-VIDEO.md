# CLIXARENA advanced workflow

Upload all ZIP contents to the repository root, preserving paths. Replace the workflow and BOTH Python scripts together. Files do not trigger a run; use Run workflow manually.

## Required files and secrets

- fonts/IskoolaPota.ttf: licensed modern Iskoola Pota (version 6+, locally tested with 6.96).
- fonts/Algerian.ttf: licensed Algerian, needed when the title overlay is enabled.
- subtitles/: use GitHub Add file > Upload files to drag-and-drop your UTF-8 Sinhala SRT, with ANY filename. Keep exactly one SRT for automatic selection; otherwise enter its repository path. It is copied to sinhala.srt in the runner, without modifying the repository.
- Actions repository secrets: STREAMTAPE_LOGIN, STREAMTAPE_KEY, TMDB_READ_TOKEN. The latter is the TMDB API Read Access Token (not the short API key). Streamtape secrets are unnecessary in sample mode. TMDB token and Algerian are unnecessary when tmdb_url is blank.

No proprietary fonts are included. Only upload fonts where the license permits repository redistribution.

## Subtitle upload

Open subtitle-upload.html locally, drop your SRT, download the renamed sinhala.srt, then upload it to your repository's subtitles/ folder. This page sends nothing to a server and needs no token. Alternatively upload the original filename directly in GitHub: runner normalization handles it. GitHub's native Run workflow form cannot accept file attachments; file upload happens through the repository upload page.

## Inputs

| Input | Behavior |
| --- | --- |
| video_url | Direct public HTTPS media URL; MP4 and MKV are supported. |
| output_name | Streamtape filename; .mp4 is added if omitted. The name before .mp4 appears beneath the title logo. |
| sample_only | Unchecked by default. Checked: first 180 seconds, downloadable sample, no Streamtape upload. |
| subtitle_path | auto selects the only SRT in subtitles/, or provide an exact repository path. |
| font_path | Defaults to fonts/IskoolaPota.ttf. |
| quality | Original/1080p/720p with High (CRF 18) or Balanced (CRF 23). Original - High is default. No upscaling. |
| audio_track | auto selects default or first audio; alternatively zero-based number or language tag such as eng. Available tracks appear in logs. Missing selections fail. |
| tmdb_url | TMDB movie or TV series URL. Blank disables the timed title overlay. |
| overlay_start | Start in seconds or HH:MM:SS, default 5. |
| overlay_duration | Duration in seconds (4-60), default 8. |

## Approved overlay

Only TMDB logos tagged English (en) are eligible. Highest pixel-count PNG wins, rating breaks ties. Download uses the original endpoint, never a thumbnail or lossy WebP conversion. Alpha-capable artwork is required. Proportional Lanczos downscaling fits it to the approved composition; logos are never enlarged past native pixels. Maximum artwork quality means the best English PNG currently available on TMDB, not unlimited resolution or lossless video encoding. Missing English artwork fails before the video download; other languages are never substituted.

Centered logo fades in, filename beneath it appears in white Algerian italic and moves slightly upward, then the Sinhala message fades in. All fade out at the configured end. Word spaces are widened; line spacing follows the approved preview. No background rectangles or replacement backgrounds are applied: the original video remains visible. The small bottom-left CLIXARENA watermark remains throughout. HarfBuzz complex shaping renders the Sinhala subtitles. Names too long for the frame are reduced in size, and ASS commands in filenames are neutralized.

## Progress and results

Encoding reports percentage, elapsed time and estimated remaining minutes about every 20 seconds. Scene complexity affects estimates. Raw tool output, responses and exception strings are suppressed and never published as artifacts.

Streamtape video URLs and IDs are not printed, placed in summaries or exported. Full runs report upload/rename verification status only (upload_verified=true); find the named file in your Streamtape file manager. No automatic upload retries: a timeout or failed rename can leave a file on the service, so check your account before rerunning. Playback processing may still be pending after successful upload.

Sample runs publish CLIXARENA-sample for three days. Download from the completed run's Artifacts section, extract and play sample.mp4. The entire source downloads again each run. Choose a title timestamp below 180 seconds to preview it. Check Sinhala shaping and synchronization before full encoding.

## Limits and security

Dispatch inputs are retained by GitHub. Masking does not make a URL secret: use non-sensitive video URLs, or configure VIDEO_URL from a repository secret for confidential links. Public HTTPS hosts and redirects are validated, but trusted sources are still necessary because DNS validation is not a complete DNS-rebinding defense. TMDB Bearer auth does not follow redirects; Streamtape auth uses POST bodies; upload URLs go to curl over stdin. Inputs never enter shell expressions.

Hosted runners have limited time/storage. Source size cap is 12 GiB, disk reserve checks apply, job limit is 350 minutes, encode watchdog 16000 seconds, upload limit one hour. High resolution movies can still exceed runner resources. AAC audio is 192 kbps; silent sources remain silent. Streamtape can additionally process the H.264 MP4 output.

## Attribution and validation

TMDB movie images: https://developer.themoviedb.org/reference/movie-images
TV images: https://developer.themoviedb.org/reference/tv-series-images
This product uses the TMDB API but is not endorsed or certified by TMDB. Artwork is supplied by contributors. See https://developer.themoviedb.org/docs/faq for attribution and usage requirements.

Validation includes local FFmpeg rendering/encoding and mocked API, selection and privacy checks. Local rendering uses Windows FFmpeg; Ubuntu behavior and live TMDB/Streamtape authentication still need a manual sample run. No real Actions run or upload was started while preparing the ZIP.

The title logo, output name and Sinhala message have independent switches, all enabled by default. The main switch disables all three. Only the logo needs TMDB; only the name needs Algerian. Update both workflow and Vercel files.

File name and Title shown in video are separate editable fields, both filled from TMDB. TV titles support season and episode selection (including specials). Names use Series - Episode title, falling back to Series - Season-1 Episode-1 when the episode title is missing or generic. The workflow overlay_name input controls only the title on video; output_name controls the MP4 and Streamtape filename.

Preview layout editor: click title/message to edit, drag title/message/logo to reposition, or use percent coordinates. Select an item then click empty preview space to place it. Reset positions restores the original arrangement. Title changes do not change the MP4 filename. Custom text/positions pass through validated overlay_layout JSON and are burned into the final video. The browser preview is approximate; repository fonts are used for encoding.

Logo performance: the original English PNG is resized once with Lanczos to its final display size, preserving alpha without upscaling. The small PNG input starts at the configured timestamp and ends at the end of the animation; EOF passes through the full video. Original resolution, CRF, text positions and subtitles remain unchanged. Jobs already running require no modification; updated scripts affect subsequent runs only.

CRF selector defaults to 18 and supports integers 0-51. It overrides High/Balanced compression while keeping the selected resolution. Auto restores High=18/Balanced=23. CRF controls quality and size, not an encoding-speed guarantee.

Two subtitle methods: Burn preserves font, overlays and watermark. On/off creates MP4 with exactly one Sinhala mov_text track, explicitly omitting all original subtitle/data/attachment tracks. H.264 video and selected AAC audio are copied; other video converts to H.264 and other audio to AAC. No logo, watermark, animation or resize applies in on/off mode. A separate UTF-8 Sinhala SRT is provided as a 3-day Actions artifact. Streamtape importing MP4 subtitles is not verified; use its player subtitle upload or documented dynamic SRT URL mechanism. Player font/rendering may differ. Subtitles already burned into source pixels cannot be removed.
