"""Manual Actions media pipeline. Never print remote responses or credentials."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import urllib.parse
import urllib.request


def mask(value):
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


def api(endpoint, values):
    # Credentials go in a POST body, not a URL or command line.
    data = urllib.parse.urlencode(values).encode()
    req = urllib.request.Request('https://api.streamtape.com/' + endpoint, data=data)
    # No redirects: do not forward credentials to a different endpoint.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=60) as response:
        body = json.loads(response.read(1024 * 1024))
    if body.get('status') != 200 or not isinstance(body.get('result'), dict):
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
        for value in values.values():
            mask(value)
        if not all(values.values()):
            raise ValueError('Required URL, asset path or Streamtape secret is missing')
        for tool in ('ffmpeg', 'ffprobe', 'fc-scan', 'curl'):
            if not shutil.which(tool):
                raise ValueError('Required media tool is missing')
        stage = 'repository subtitle and font availability'
        root = Path.cwd().resolve()
        srt_path = repository_file(root, values['SUBTITLE_PATH'], '.srt', 10 * 1024**2)
        font_path = repository_file(root, values['FONT_PATH'], '.ttf', 30 * 1024**2)
        with tempfile.TemporaryDirectory(prefix='clixarena-') as directory:
            original = Path.cwd()
            os.chdir(directory)
            try:
                stage = 'subtitle and font validation'
                print('Checking subtitle and font', flush=True)
                shutil.copyfile(srt_path, 'subtitles.srt')
                subtitle = Path('subtitles.srt').read_text(encoding='utf-8-sig')
                if not re.search(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', subtitle) or not re.search('[\u0d80-\u0dff]', subtitle):
                    raise ValueError('SRT must contain valid timestamps and Unicode Sinhala text')
                Path('fonts').mkdir()
                shutil.copyfile(font_path, 'fonts/iskoola.ttf')
                family = command(['fc-scan', '--format', '%{family}', 'fonts/iskoola.ttf'])
                if 'Iskoola Pota' not in family.split(','):
                    raise ValueError('Font file does not identify as Iskoola Pota')
                stage = 'video download and validation'
                print('Downloading video', flush=True)
                download(values['VIDEO_URL'], Path('source.video'), 12 * 1024**3)
                source = probe('source.video')
                if not any(s['codec_type'] == 'video' for s in source['streams']):
                    raise ValueError('Source has no video stream')
                if shutil.disk_usage('.').free < Path('source.video').stat().st_size * 2 + 2 * 1024**3:
                    raise ValueError('Insufficient disk space for encoding')
                stage = 'encoding'
                print('Encoding H.264/AAC with Sinhala subtitles and watermark', flush=True)
                filters = ("scale=trunc(iw/2)*2:trunc(ih/2)*2,"
                           "subtitles=subtitles.srt:fontsdir=fonts:force_style='FontName=Iskoola Pota,FontSize=22,Outline=1,Shadow=0,MarginV=24',"
                           "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                           "text=CLIXARENA:fontsize=h/44:fontcolor=white@0.55:x=w/136:y=h-th-h/38")
                command(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                         '-i', 'source.video', '-map', '0:v:0', '-map', '0:a:0?',
                         '-vf', filters, '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                         '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
                         '-movflags', '+faststart', 'clixarena.mp4'], timeout=16000)
                output = probe('clixarena.mp4')
                streams = output['streams']
                if not any(s.get('codec_name') == 'h264' for s in streams) or any(s.get('codec_type') == 'audio' and s.get('codec_name') != 'aac' for s in streams):
                    raise ValueError('Encoded file has unexpected codecs')
                if abs(float(source['format']['duration']) - float(output['format']['duration'])) > 2:
                    raise ValueError('Encoded duration differs from source')
                stage = 'Streamtape upload'
                print('Uploading encoded MP4 to Streamtape', flush=True)
                file_id = upload(Path('clixarena.mp4'), values['STREAMTAPE_LOGIN'], values['STREAMTAPE_KEY'])
                link = 'https://streamtape.com/v/' + file_id
                print('Upload verified: ' + link)
                if os.getenv('GITHUB_OUTPUT'):
                    with open(os.environ['GITHUB_OUTPUT'], 'a') as file:
                        file.write('file_id=' + file_id + '\nvideo_url=' + link + '\n')
                if os.getenv('GITHUB_STEP_SUMMARY'):
                    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as file:
                        file.write('### Upload verified\n[Open video](' + link + ')\n\nStreamtape may still be processing playback.\n')
            finally:
                os.chdir(original)
    except Exception:
        # Exception strings can contain signed URLs, credentials and response bodies.
        print('::error::Failed during ' + stage + '. Check inputs, secrets, formats, service availability and disk space. Raw errors suppressed to protect credentials.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
