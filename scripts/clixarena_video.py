"""Manual Actions media pipeline. Never print remote responses or credentials."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import urllib.parse
import urllib.request
from clixarena_features import (settings, subtitle_asset, audio_selection, fetch_logo,
                                write_intro, video_dimensions, filter_graph, encode_progress)


def mask(value):
    if not value:
        return
    escaped = value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    if os.getenv('GITHUB_ACTIONS') == 'true':
        print('::add-mask::' + escaped, flush=True)


def validate_url(url):
    if any(ord(c) < 32 for c in url) or len(url) > 8192:
        raise ValueError('Invalid URL characters or length')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Use a direct HTTPS URL without embedded credentials or fragments')
    if parsed.port not in (None, 443):
        raise ValueError('Only HTTPS port 443 is allowed')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('URL must resolve to a public Internet host')
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        mask(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), SafeRedirect())


def download(url, target, limit):
    validate_url(url)
    mask(url)
    request = urllib.request.Request(url, headers={'User-Agent': 'CLIXARENA/1.0'})
    with OPENER.open(request, timeout=60) as response, target.open('wb') as output:
        total = 0
        while block := response.read(1024 * 1024):
            total += len(block)
            if total > limit or shutil.disk_usage(target.parent).free < 2 * 1024**3:
                raise ValueError('Download exceeds size limit or disk reserve')
            output.write(block)
    if not target.stat().st_size:
        raise ValueError('Downloaded file is empty')


def command(args, timeout=60):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('Media tool failed; verify input formats and available disk space')
    return result.stdout


def probe(path):
    return json.loads(command(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def repository_file(root, value, suffix, limit):
    relative = Path(value)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Asset path must stay inside the repository')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Repository asset is missing or outside checkout')
    if path.suffix.lower() != suffix or not 0 < path.stat().st_size <= limit:
        raise ValueError('Repository asset has invalid extension or size')
    return path


def output_filename(value):
    name = value.strip()
    if not name or name.startswith('.') or any(c in name for c in '/\\:"<>|?*') or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError('Invalid output filename')
    if name.lower().endswith('.mp4'):
        name = name[:-4]
    if not name.strip() or len(name.encode('utf-8')) > 180:
        raise ValueError('Output filename is empty or too long')
    return name + '.mp4'


def validate_sinhala_font(path):
    data = Path(path).read_bytes()
    count = struct.unpack_from('>H', data, 4)[0]
    tables = {}
    for index in range(count):
        tag, _, offset, size = struct.unpack_from('>4sIII', data, 12 + index * 16)
        if offset + size > len(data):
            raise ValueError('Truncated font')
        tables[tag] = offset
    for tag in (b'GSUB', b'GPOS'):
        base = tables[tag]
        scripts = base + struct.unpack_from('>H', data, base + 4)[0]
        total = struct.unpack_from('>H', data, scripts)[0]
        if not any(data[scripts + 2 + i * 6:scripts + 6 + i * 6] in (b'sinh', b'sin2') for i in range(total)):
            raise ValueError('Font lacks Sinhala shaping tables')
    base = tables[b'name']
    _, total, strings = struct.unpack_from('>HHH', data, base)
    versions = []
    for index in range(total):
        platform, _, _, name_id, length, offset = struct.unpack_from('>HHHHHH', data, base + 6 + index * 12)
        if name_id == 5:
            text = data[base + strings + offset:base + strings + offset + length].decode('utf-16-be' if platform in (0, 3) else 'latin1')
            match = re.search(r'Version\s+(\d+(?:\.\d+)?)', text, re.I)
            if match:
                versions.append(float(match[1]))
    if not versions or max(versions) < 6:
        print('::error::Use a modern Iskoola Pota font (version 6 or later). The supplied Windows font is version 6.96; replace fonts/IskoolaPota.ttf. Older versions are not supported by this pipeline.')
        raise ValueError('Unsupported Iskoola Pota version')
    print('Iskoola Pota font version: ' + str(max(versions)), flush=True)


def prepare_ass():
    command(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
             '-sub_charenc', 'UTF-8', '-i', 'subtitles.srt', 'subtitles.ass'])
    path = Path('subtitles.ass')
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    fields = None
    styles = False
    for index, line in enumerate(lines):
        if line.startswith('['):
            styles = line == '[V4+ Styles]'
        if styles and line.startswith('Format:'):
            fields = [field.strip() for field in line.split(':', 1)[1].split(',')]
        if styles and fields and line.startswith('Style:'):
            values = line.split(':', 1)[1].strip().split(',')
            settings = {'Fontname': 'Iskoola Pota', 'Fontsize': '22', 'Outline': '1',
                        'Shadow': '0', 'MarginV': '24', 'Spacing': '0', 'Encoding': '1',
                        'PrimaryColour': '&H00FFFFFF', 'SecondaryColour': '&H00FFFFFF',
                        'OutlineColour': '&H00000000', 'BackColour': '&H00000000'}
            for key, value in settings.items():
                values[fields.index(key)] = value
            lines[index] = 'Style: ' + ','.join(values)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def api(endpoint, values):
    # Credentials go in a POST body, not a URL or command line.
    data = urllib.parse.urlencode(values).encode()
    req = urllib.request.Request('https://api.streamtape.com/' + endpoint, data=data)
    # No redirects: do not forward credentials to a different endpoint.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=60) as response:
        body = json.loads(response.read(1024 * 1024))
    if body.get('status') != 200 or not (isinstance(body.get('result'), dict) or body.get('result') is True):
        raise ValueError('Streamtape API rejected the request')
    return body['result']


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def upload(path, login, key):
    with path.open('rb') as file:
        digest = hashlib.file_digest(file, 'sha256').hexdigest()
    result = api('file/ul', {'login': login, 'key': key, 'sha256': digest})
    url = result.get('url', '')
    validate_url(url)
    mask(url)
    # curl streams the multipart file. URL is supplied over stdin, never argv.
    escaped = url.replace('\\', '\\\\').replace('"', '\\"')
    config = 'url = "' + escaped + '"\n'
    response = subprocess.run(['curl', '--config', '-', '--silent', '--fail',
                               '--proto', '=https', '--connect-timeout', '30',
                               '--max-time', '3600', '--form', 'file1=@' + str(path)],
                              input=config, capture_output=True, text=True, timeout=3610)
    if response.returncode:
        raise ValueError('Upload failed or timed out; check account before rerunning')
    body = json.loads(response.stdout)
    if body.get('status') != 200:
        raise ValueError('Upload API reported failure')
    file_id = body.get('result', {}).get('id', '')
    if not isinstance(file_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', file_id):
        raise ValueError('Upload response has no valid file ID; check account before rerunning')
    info = api('file/info', {'login': login, 'key': key, 'file': file_id}).get(file_id, {})
    if info.get('status') != 200 or int(info.get('size', -1)) != path.stat().st_size:
        raise ValueError('Uploaded file could not be verified; check account before rerunning')
    return file_id


def main():
    stage = 'preflight'
    try:
        values = {name: os.getenv(name, '') for name in
                  ('VIDEO_URL', 'SUBTITLE_PATH', 'FONT_PATH', 'STREAMTAPE_LOGIN', 'STREAMTAPE_KEY')}
        sample_only = os.getenv('SAMPLE_ONLY', 'false').lower() == 'true'
        options = settings()
        tmdb_token = os.getenv('TMDB_READ_TOKEN', '')
        mask(tmdb_token)
        for value in values.values():
            mask(value)
        required = ('VIDEO_URL', 'SUBTITLE_PATH', 'FONT_PATH') if sample_only else tuple(values)
        missing = [name for name in required if not values[name].strip()]
        if missing:
            print('::error::Missing required configuration: ' + ', '.join(missing) +
                  '. Set video/asset inputs and repository Actions secrets with these exact names.')
            return 1
        for tool in ('ffmpeg', 'ffprobe', 'fc-scan', 'curl'):
            if not shutil.which(tool):
                raise ValueError('Required media tool is missing')
        stage = 'output filename validation'
        output_name = output_filename(os.getenv('OUTPUT_NAME', 'CLIXARENA.mp4'))
        overlay_name = os.getenv('OVERLAY_NAME', '').strip() or output_name[:-4]
        if len(overlay_name.encode('utf-8')) > 500 or re.search(r'[\x00-\x1f\x7f]', overlay_name):
            raise ValueError('Invalid display title')
        stage = 'repository subtitle and font availability'
        root = Path.cwd().resolve()
        srt_path = subtitle_asset(root, values['SUBTITLE_PATH'])
        font_path = repository_file(root, values['FONT_PATH'], '.ttf', 30 * 1024**2)
        algerian_path = None
        if options['parts']['name']:
            algerian_path = repository_file(root, 'fonts/Algerian.ttf', '.ttf', 30 * 1024**2)
        with tempfile.TemporaryDirectory(prefix='clixarena-') as directory:
            original = Path.cwd()
            os.chdir(directory)
            try:
                stage = 'subtitle and font validation'
                print('Checking subtitle and font', flush=True)
                shutil.copyfile(srt_path, 'sinhala.srt')
                # Every uploaded name is normalized in the runner, without changing repository files.
                shutil.copyfile('sinhala.srt', 'subtitles.srt')
                print('Subtitle loaded as sinhala.srt', flush=True)
                subtitle = Path('sinhala.srt').read_text(encoding='utf-8-sig')
                if not re.search(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', subtitle) or not re.search('[\u0d80-\u0dff]', subtitle):
                    raise ValueError('SRT must contain valid timestamps and Unicode Sinhala text')
                Path('fonts').mkdir()
                shutil.copyfile(font_path, 'fonts/iskoola.ttf')
                family = command(['fc-scan', '--format', '%{family}', 'fonts/iskoola.ttf'])
                if 'Iskoola Pota' not in family.split(','):
                    raise ValueError('Font file does not identify as Iskoola Pota')
                validate_sinhala_font('fonts/iskoola.ttf')
                if algerian_path:
                    shutil.copyfile(algerian_path, 'fonts/algerian.ttf')
                    if 'Algerian' not in command(['fc-scan', '--format', '%{family}', 'fonts/algerian.ttf']).split(','):
                        print('::error::fonts/Algerian.ttf must be the Algerian font. No font substitution is used.')
                        raise ValueError('Invalid Algerian font')
                prepare_ass()
                shaping_test = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'info',
                    '-f', 'lavfi', '-i', 'color=s=320x180:d=0.1', '-vf',
                    'ass=subtitles.ass:fontsdir=fonts:shaping=complex', '-frames:v', '1', '-f', 'null', '-'],
                    capture_output=True, text=True, timeout=60)
                if shaping_test.returncode or not re.search(r'HarfBuzz.*\(COMPLEX\)', shaping_test.stderr):
                    print('::error::FFmpeg/libass complex HarfBuzz shaping is unavailable. Use a build with libass and HarfBuzz.')
                    raise ValueError('Complex shaping unavailable')
                print('Sinhala rendering: HarfBuzz complex shaping enabled', flush=True)
                logo_size = None
                if options['parts']['logo']:
                    stage = 'English TMDB original logo'
                    fetch_logo(options['tmdb'], tmdb_token, download)
                    logo_info = probe('title-logo.png')['streams'][0]
                    if logo_info.get('pix_fmt') not in ('rgba', 'bgra', 'argb', 'abgr', 'yuva420p', 'pal8'):
                        print('::error::Selected English logo lacks an alpha channel. Choose different artwork before encoding.')
                        raise ValueError('Nontransparent artwork')
                    logo_size = (int(logo_info['width']), int(logo_info['height']))
                if options['parts']['name'] or options['parts']['message']:
                    write_intro(overlay_name, options['start'], options['duration'], options['parts'])
                stage = 'video download and validation'
                print('Downloading video', flush=True)
                download(values['VIDEO_URL'], Path('source.video'), 12 * 1024**3)
                source = probe('source.video')
                if not any(s['codec_type'] == 'video' for s in source['streams']):
                    raise ValueError('Source has no video stream')
                if shutil.disk_usage('.').free < Path('source.video').stat().st_size * 2 + 2 * 1024**3:
                    raise ValueError('Insufficient disk space for encoding')
                source_duration = float(source['format']['duration'])
                expected_duration = min(180, source_duration) if sample_only else source_duration
                stage = 'audio and quality selection'
                audio_map = audio_selection(source['streams'], options['audio'])
                video_stream = next(s for s in source['streams'] if s['codec_type'] == 'video')
                width, height = video_dimensions(video_stream, options['height'])
                print(f'Output {width} x {height}, H.264 CRF {options["crf"]}', flush=True)
                if any(options['parts'].values()) and options['start'] >= expected_duration:
                    print('::warning::Title timestamp is outside this encode. It will not appear; choose a timestamp within the sample/full video duration.')
                stage = 'encoding'
                print('Encoding H.264/AAC with Sinhala subtitles and watermark', flush=True)
                filters = filter_graph(width, height, options, logo_size)
                inputs = ['-i', 'source.video']
                if logo_size:
                    inputs += ['-loop', '1', '-framerate', '30', '-i', 'title-logo.png']
                encode_progress(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y'] + inputs +
                         ['-map', '[video]', '-map', audio_map, '-filter_complex', filters,
                         '-c:v', 'libx264', '-preset', 'fast', '-crf', str(options['crf']),
                         '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
                         '-t', str(expected_duration), '-movflags', '+faststart'], expected_duration)
                output = probe('clixarena.mp4')
                streams = output['streams']
                if not any(s.get('codec_name') == 'h264' for s in streams) or any(s.get('codec_type') == 'audio' and s.get('codec_name') != 'aac' for s in streams):
                    raise ValueError('Encoded file has unexpected codecs')
                if abs(expected_duration - float(output['format']['duration'])) > 2:
                    raise ValueError('Encoded duration differs from source')
                if sample_only:
                    stage = 'sample export'
                    preview = original / 'preview'
                    preview.mkdir(exist_ok=True)
                    shutil.copyfile('clixarena.mp4', preview / 'sample.mp4')
                    print('Sample ready: download CLIXARENA-sample from this run artifacts. No Streamtape upload performed.')
                    if os.getenv('GITHUB_STEP_SUMMARY'):
                        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as file:
                            file.write('### 3-minute sample ready\nDownload **CLIXARENA-sample** from this run artifacts. Inspect subtitles from 01:18 and watermark. No Streamtape upload performed.\n')
                    return 0
                stage = 'Streamtape upload'
                print('Uploading encoded MP4 to Streamtape', flush=True)
                file_id = upload(Path('clixarena.mp4'), values['STREAMTAPE_LOGIN'], values['STREAMTAPE_KEY'])
                stage = 'Streamtape filename update'
                # Keep user names out of shell, FFmpeg paths and curl form syntax.
                renamed = api('file/rename', {'login': values['STREAMTAPE_LOGIN'],
                              'key': values['STREAMTAPE_KEY'], 'file': file_id, 'name': output_name})
                if renamed is not True:
                    raise ValueError('Streamtape filename update failed')
                verified = api('file/info', {'login': values['STREAMTAPE_LOGIN'],
                               'key': values['STREAMTAPE_KEY'], 'file': file_id}).get(file_id, {})
                if verified.get('status') != 200 or verified.get('name') != output_name:
                    print('::error::Upload exists but final filename could not be verified. Check Streamtape before rerunning.')
                    raise ValueError('Final filename verification failed')
                # Do not construct, print, summarize or export a Streamtape video URL/ID.
                print('Upload and filename verified. Find the video in your Streamtape file manager.')
                if os.getenv('GITHUB_OUTPUT'):
                    with open(os.environ['GITHUB_OUTPUT'], 'a') as file:
                        file.write('upload_verified=true\n')
                if os.getenv('GITHUB_STEP_SUMMARY'):
                    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as file:
                        file.write('### Upload and filename verified\nFind the video in your Streamtape file manager. Video URLs and file IDs are not included in logs, summaries or outputs. Playback processing may still be pending.\n')
            finally:
                os.chdir(original)
    except Exception:
        # Exception strings can contain signed URLs, credentials and response bodies.
        print('::error::Failed during ' + stage + '. Check inputs, secrets, formats, service availability and disk space. Raw errors suppressed to protect credentials.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
