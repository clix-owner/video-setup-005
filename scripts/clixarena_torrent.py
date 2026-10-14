"""Public torrent video selection and piece-verified download. No raw alerts/URLs."""
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import time
import urllib.error
import urllib.parse

class TorrentError(Exception):pass
VIDEO={'.mkv','.mp4','.webm','.avi','.mov','.m4v','.ts','.m2ts'}

def candidates(info):
    files=info.files();result=[]
    if files.num_files()>10000:raise TorrentError('Torrent contains too many files.')
    for index in range(files.num_files()):
        path=str(files.file_path(index));parts=path.replace('\\','/').split('/')
        if path.startswith(('/','\\')) or any(p in ('..','.') or ':' in p or '\x00' in p for p in parts):raise TorrentError('Torrent has unsafe file paths.')
        # Reject symlinks before any payload can be written.
        if int(files.file_flags(index))&8:raise TorrentError('Torrent symlinks are unsupported.')
        size=int(files.file_size(index));extension=Path(path).suffix.lower()
        if extension in VIDEO and size>0:
            name=' / '.join(parts[1:] or parts)
            name=''.join(c if ord(c)>=32 and ord(c)!=127 else ' ' for c in name)[:350]
            result.append({'index':index,'name':name,'bytes':size})
    if not result:raise TorrentError('Torrent contains no supported video files.')
    if len(result)>1000:raise TorrentError('Torrent contains too many video choices.')
    return result

def select_file(files,request,pause=time.sleep,clock=time.monotonic,wait_seconds=1200):
    if len(files)==1:return files[0]['index']
    job=os.getenv('PORTAL_JOB_ID','');run=os.getenv('GITHUB_RUN_ID','')
    state={'job':job,'run_id':run,'status':'waiting_file','files':files}
    try:current=request(job,state_dir='torrent')
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        current=None
    request(job,state,current.get('sha') if current else None,state_dir='torrent')
    print('Multiple torrent videos found. Select a file in the portal within 20 minutes; payload download is paused.',flush=True)
    deadline=clock()+wait_seconds
    while clock()<deadline:
        pause(min(30,max(0,deadline-clock())))
        current=request(job,state_dir='torrent');updated=json.loads(base64.b64decode(current['content']).decode())
        if updated.get('job')!=job or str(updated.get('run_id'))!=run:raise TorrentError('Torrent selection belongs to another run.')
        selected=updated.get('selected')
        if updated.get('status')=='selected' and type(selected) is int and any(f['index']==selected for f in files):
            updated['status']='downloading';request(job,updated,current['sha'],state_dir='torrent');return selected
    state['status']='expired'
    try:request(job,state,current['sha'],state_dir='torrent')
    except Exception:pass
    raise TorrentError('Torrent file selection expired after 20 minutes. No video was downloaded.')

def public_filter(lt):
    rules=lt.ip_filter()
    for cidr in ['0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8','169.254.0.0/16','172.16.0.0/12','192.168.0.0/16','192.0.0.0/24','198.18.0.0/15','224.0.0.0/3','::/128','::1/128','::ffff:0:0/96','fc00::/7','fe80::/10','ff00::/8']:
        net=ipaddress.ip_network(cidr);rules.add_rule(str(net.network_address),str(net.broadcast_address),1)
    return rules

def prepare(lt,descriptor,root):
    kind=descriptor.get('kind');job=os.getenv('PORTAL_JOB_ID','')
    if kind=='file':
        path=descriptor.get('path','')
        if not re.fullmatch(r'[a-f0-9]{32}',job) or path!=f'.clixarena/torrents/{job}.torrent':raise TorrentError('Invalid repository torrent path.')
        asset=root/path
        if asset.is_symlink() or root not in asset.resolve().parents or not asset.is_file() or asset.stat().st_size>1024*1024:raise TorrentError('Torrent file is missing, oversized or unsafe.')
        blob=asset.read_bytes();meta=lt.bdecode(blob)
        if not meta or not isinstance(meta.get(b'info'),dict) or meta[b'info'].get(b'private')==1 or b'pieces' not in meta[b'info']:raise TorrentError('Only public BitTorrent v1 torrents are supported.')
        # Trackers, web seeds and private passkeys never trigger HTTP requests.
        for key in (b'announce',b'announce-list',b'url-list',b'httpseeds',b'nodes'):meta.pop(key,None)
        params=lt.load_torrent_buffer(lt.bencode(meta))
    elif kind=='magnet':
        value=descriptor.get('magnet','');query=urllib.parse.parse_qs(urllib.parse.urlsplit(value).query)
        xt=next((x for x in query.get('xt',[]) if re.fullmatch(r'urn:btih:(?:[a-fA-F0-9]{40}|[A-Za-z2-7]{32})',x)),None)
        if not value.startswith('magnet:?') or not xt:raise TorrentError('Use a valid public BitTorrent v1 magnet.')
        params=lt.parse_magnet_uri('magnet:?xt='+xt)
    else:raise TorrentError('Invalid torrent source.')
    params.trackers=[];params.url_seeds=[];params.http_seeds=[]
    params.flags &= ~lt.torrent_flags.auto_managed
    params.flags |= lt.torrent_flags.upload_mode
    params.flags &= ~lt.torrent_flags.paused
    return params

def download_torrent(descriptor,target,limit,root,request):
    try:import libtorrent as lt
    except ImportError:raise TorrentError('libtorrent is missing. Update the Actions workflow and media tools.') from None
    folder=Path('.torrent-payload').resolve();folder.mkdir()
    session=lt.session({'listen_interfaces':'0.0.0.0:0','enable_dht':True,'enable_lsd':False,'enable_upnp':False,'enable_natpmp':False,'upload_rate_limit':1024,'connections_limit':80,'max_metadata_size':1024*1024})
    session.set_ip_filter(public_filter(lt));handle=None
    try:
        params=prepare(lt,descriptor,root);params.save_path=str(folder)
        if params.ti:
            choices=candidates(params.ti);params.file_priorities=[0]*params.ti.num_files()
        handle=session.add_torrent(params)
        print('Fetching torrent metadata from public peers',flush=True)
        deadline=time.monotonic()+600
        while not handle.has_metadata():
            if time.monotonic()>=deadline:raise TorrentError('Torrent metadata timed out after 10 minutes. Check public seeders.')
            if handle.status().errc.value():raise TorrentError('Torrent metadata failed. Raw peer errors were suppressed.')
            session.pop_alerts();time.sleep(2)
        info=handle.torrent_file()
        if info.priv():raise TorrentError('Private torrents are unsupported.')
        choices=candidates(info);handle.prioritize_files([0]*info.num_files())
        # Keep every destination flat and generated, independent of untrusted names.
        for i in range(info.num_files()):handle.rename_file(i,f'file-{i:05d}'+Path(info.files().file_path(i)).suffix.lower()[:12])
        selected=select_file(choices,request)
        size=next(f['bytes'] for f in choices if f['index']==selected)
        if size>limit:raise TorrentError('Selected video exceeds the 12 GB source limit.')
        if shutil.disk_usage(folder).free<size*3+2*1024**3:raise TorrentError('Not enough runner space for this video and MP4 processing. Select a smaller file.')
        priorities=[0]*info.num_files();priorities[selected]=4;handle.prioritize_files(priorities)
        handle.unset_flags(lt.torrent_flags.upload_mode)
        started=time.monotonic();last=0;last_bytes=0;last_progress=started
        print('Downloading only the selected torrent video; boundary pieces may include small parts of adjacent files.',flush=True)
        while True:
            status=handle.status();progress=handle.file_progress(lt.torrent_handle.piece_granularity)[selected];now=time.monotonic()
            if status.errc.value():raise TorrentError('Torrent download failed. Raw peer errors were suppressed.')
            if progress>last_bytes:last_bytes=progress;last_progress=now
            if now-last>=30:
                print(f'Torrent download {min(100,progress/size*100):.1f}% | {status.download_rate/1024**2:.2f} MiB/s | peers {status.num_peers}',flush=True);last=now
            session.pop_alerts()
            if progress>=size:break
            if now-started>7200:raise TorrentError('Torrent download exceeded the 2-hour limit.')
            if now-last_progress>900:raise TorrentError('Torrent made no download progress for 15 minutes. Check public seeders before rerunning.')
            time.sleep(2)
        handle.pause();session.remove_torrent(handle);handle=None
        file=folder/f'file-{selected:05d}{Path(info.files().file_path(selected)).suffix.lower()[:12]}'
        # torrent_file may reflect renamed paths; the destination is still generated.
        if not file.is_file() or file.is_symlink() or file.stat().st_size!=size:raise TorrentError('Selected torrent video did not complete correctly.')
        shutil.move(str(file),str(target));print('Selected torrent video complete; piece hashes verified by libtorrent.',flush=True)
    finally:
        if handle is not None:handle.pause();session.remove_torrent(handle)
        session.pause()
        # session must release its disk worker before the directory is cleaned by the outer job.

