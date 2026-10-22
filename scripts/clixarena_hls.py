"""Prepare H.264/AAC once at upload time; pack real HLS segments below 2 GiB."""
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def package(source, directory, run=subprocess.run, limit=1900 * 1024**2):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    probe = run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(source)],
                capture_output=True, text=True, timeout=120)
    if probe.returncode:
        raise ValueError('Cannot probe HLS input')
    streams = json.loads(probe.stdout)['streams']
    video = next((s for s in streams if s.get('codec_type') == 'video'), {})
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), {})
    if video.get('codec_name') != 'h264' or audio.get('codec_name', 'aac') != 'aac':
        raise ValueError('HLS packaging requires H.264/AAC; prepare the input using the normal workflow')
    args = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-i', str(source), '-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy',
            '-sn', '-dn', '-f', 'hls', '-hls_time', '6', '-hls_list_size', '0',
            '-hls_playlist_type', 'vod', '-hls_segment_filename', str(directory / 'segment_%06d.ts'),
            str(directory / 'index.m3u8')]
    result = run(args, capture_output=True, timeout=7200)
    if result.returncode:
        raise ValueError('FFmpeg HLS packaging failed')
    lines = (directory / 'index.m3u8').read_text().splitlines()
    if '#EXT-X-ENDLIST' not in lines:
        raise ValueError('Incomplete HLS output')
    segments = []
    duration = None
    for line in lines:
        if line.startswith('#EXTINF:'):
            duration = float(line.split(':')[1].split(',')[0])
        elif line and not line.startswith('#'):
            if not re.fullmatch(r'segment_\d+\.ts', line) or duration is None or not math.isfinite(duration) or duration <= 0:
                raise ValueError('Invalid segment metadata')
            segments.append((directory / line, duration))
            duration = None
    if not segments:
        raise ValueError('No HLS segments generated')
    bundles, index = [], []
    output = None
    offset = 0
    try:
        for segment, duration in segments:
            size = segment.stat().st_size
            if size <= 0 or size > limit or size % 188:
                raise ValueError('HLS segment exceeds Telegram bundle limit or is not MPEG-TS')
            if output is None or offset + size > limit:
                if output:
                    output.close()
                bundle = directory / f'part{len(bundles)+1}.ts'
                bundles.append(bundle)
                output = bundle.open('wb')
                offset = 0
            with segment.open('rb') as stream:
                shutil.copyfileobj(stream, output, 1024**2)
            # Bundle index, byte offset, byte count, measured duration.
            index.append([len(bundles)-1, offset, size, duration])
            offset += size
            segment.unlink()
    finally:
        if output:
            output.close()
    return bundles, index


def upload_hls(path, name, send, run=subprocess.run):
    with tempfile.TemporaryDirectory(prefix='telegram-hls-') as directory:
        bundles, segments = package(path, directory, run=run)
        ids = []
        for i, bundle in enumerate(bundles):
            print(f'Uploading prepared HLS part {i+1}/{len(bundles)} (no video re-encode)', flush=True)
            ids.append(str(send(bundle, f'{Path(name).stem} - Part {i+1}.ts')))
        fid = '-'.join(ids)
        if len(fid) > 128:
            raise ValueError('Too many Telegram parts for current mapping ID format')
        return {'file_id': fid, 'parts': ids,
                'hls': {'version': 1, 'format': 'mpegts-bundles',
                        'sizes': [p.stat().st_size for p in bundles], 'segments': segments}}
