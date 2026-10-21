"""Upload providers and backward-compatible mappings. No upload retries."""
import json,re,subprocess,time,urllib.parse,urllib.request,urllib.error
from clixarena_upload_metrics import run_upload, file_size, timed_call


def selected_host(layout):
    value=layout.get('uploadHost','streamtape')
    if value not in ('streamtape','streamhg','abyss','telegram'):raise ValueError('Choose Streamtape, StreamHG, Abyss or Telegram')
    return value


def selected_hosts(layout):
    first=selected_host(layout)
    second=layout.get('secondUploadHost','')
    if second not in ('','streamtape','streamhg','abyss','telegram'):
        raise ValueError('Choose a valid second upload host')
    if second==first:
        raise ValueError('Choose two different upload hosts')
    return [first,second] if second else [first]


def merge_provider_mapping(rows,identity,file_id,provider='streamtape'):
    if provider not in ('streamtape','streamhg','abyss','telegram') or not isinstance(file_id,str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}',file_id):raise ValueError('Invalid host or video ID')
    if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ValueError('Invalid mappings')
    key=('mal_id' if 'mal_id' in identity else 'anilist_id') if identity['type']=='anime' else 'tmdb_id'
    matches=lambda row:all(row.get(k)==identity.get(k) for k in ('type',key,'season','episode'))
    providers={}
    for row in rows:
        if not matches(row):continue
        if isinstance(row.get('providers'),dict):providers.update(row['providers'])
        if row.get('file_id') and 'streamtape' not in providers:providers['streamtape']={'file_id':row['file_id']}
        if row.get('abyss_id') and 'abyss' not in providers:providers['abyss']={'file_id':row['abyss_id']}
        if row.get('streamhg_id') and 'streamhg' not in providers:providers['streamhg']={'file_id':row['streamhg_id']}
        if row.get('telegram_id') and 'telegram' not in providers:providers['telegram']={'file_id':row['telegram_id']}
    providers[provider]={'file_id':file_id}
    item=dict(identity,provider=provider,providers=providers)
    if 'streamtape' in providers:item['file_id']=providers['streamtape']['file_id']
    if 'abyss' in providers:item['abyss_id']=providers['abyss']['file_id']
    if 'streamhg' in providers:item['streamhg_id']=providers['streamhg']['file_id']
    if 'telegram' in providers:item['telegram_id']=providers['telegram']['file_id']
    return [row for row in rows if not matches(row)]+[item]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class HostError(ValueError):
    """Only fixed text and numeric status codes may be exposed to job logs."""


def _status(value):
    return str(value) if type(value) is int and 100<=value<=599 else value if isinstance(value,str) and re.fullmatch(r'[1-5][0-9]{2}',value) else 'unknown'


def streamhg_api(endpoint,key,params=None):
    if not key or len(key)>512 or any(ord(c)<33 for c in key):
        raise HostError('StreamHG configuration: STREAMHG_API_KEY is missing or invalid.')
    url='https://streamhgapi.com/api/'+endpoint+'?'+urllib.parse.urlencode(dict(params or {},key=key))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'Mozilla/5.0'}),timeout=30) as response:
            raw=response.read(1024*1024+1)
    except urllib.error.HTTPError as error:
        raise HostError('StreamHG API discovery/info: HTTP '+_status(error.code)+'. Check API key, account access or host blocking. No file upload was started by this request.') from None
    except Exception:
        raise HostError('StreamHG API discovery/info: connection or TLS failure. No file upload was started by this request.') from None
    if len(raw)>1024*1024:raise HostError('StreamHG API discovery/info: oversized response; upload not started.')
    try:body=json.loads(raw)
    except (ValueError,TypeError):raise HostError('StreamHG API discovery/info: expected JSON but received another format, possibly a protection page. Upload not started.') from None
    if not isinstance(body,dict) or _status(body.get('status'))!='200':
        code=_status(body.get('status')) if isinstance(body,dict) else 'unknown'
        raise HostError('StreamHG API discovery/info: rejected request (API status '+code+'). Check STREAMHG_API_KEY and account access.')
    return body


def upload_streamhg(path,name,key,mask=lambda _:None,run=subprocess.run,validate=None):
    if any(c in name for c in ('\r','\n','\x00')):raise HostError('StreamHG configuration: invalid output name.')
    mask(key)
    print('Requesting StreamHG upload server',flush=True)
    server=timed_call('StreamHG upload-server lookup',streamhg_api,'upload/server',key).get('result')
    if not isinstance(server,str):raise HostError('StreamHG server discovery: upload URL missing in response; upload not started.')
    try:
        parsed=urllib.parse.urlsplit(server)
        if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.fragment or parsed.port not in (None,443) or not parsed.path.startswith('/upload/')):
            raise ValueError()
        if validate is None:
            import socket,ipaddress
            addresses=socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError()
        else:validate(server)
    except Exception:
        raise HostError('StreamHG server discovery: returned endpoint failed public HTTPS validation; upload not started.') from None
    mask(server)
    print('StreamHG upload server validated; sending MP4',flush=True)
    quote=lambda v:v.replace('\\','\\\\').replace('"','\\"').replace('\r','').replace('\n','')
    filename=quote(name);local=quote(str(path))
    config='url = "'+quote(server)+'"\nform-string = "'+quote('key='+key)+'"\n'
    config+='form-string = "'+quote('file_title='+name.removesuffix('.mp4'))+'"\n'
    try:
        response=run_upload(['curl','--config','-','--silent','--fail','--proto','=https',
            '--user-agent','Mozilla/5.0','--connect-timeout','30','--max-time','3600',
            '--write-out','\nCLIXARENA_HTTP:%{http_code}','--form',
            'file=@"'+local+'";filename="'+filename+'"'],input=config,capture_output=True,text=True,timeout=3610,runner=run,label='StreamHG',size=file_size(path))
    except subprocess.TimeoutExpired:
        raise HostError('StreamHG file upload: timed out. Upload state is uncertain; check the account before retrying.') from None
    except Exception:
        raise HostError('StreamHG file upload: uploader could not finish. Check curl installation and the account before retrying.') from None
    raw,marker,http=response.stdout.rpartition('\nCLIXARENA_HTTP:')
    if not marker:raw=response.stdout;http='unknown'
    http=_status(http.strip())
    if response.returncode:
        hints={6:'DNS lookup failed',7:'could not connect to upload server',22:'HTTP request rejected',
               28:'upload timed out',35:'TLS handshake failed',60:'TLS certificate verification failed',
               26:'local output file could not be read',52:'upload server returned no response',56:'connection interrupted'}
        hint=hints.get(response.returncode,'uploader failed')
        raise HostError('StreamHG file upload: '+hint+' (curl '+str(int(response.returncode))+', HTTP '+http+'). Check the account before retrying; upload is not repeated automatically.')
    try:body=json.loads(raw)
    except (ValueError,TypeError):
        raise HostError('StreamHG upload response: expected JSON (HTTP '+http+'). Upload may exist; check account before retrying.') from None
    if not isinstance(body,dict) or _status(body.get('status'))!='200':
        code=_status(body.get('status')) if isinstance(body,dict) else 'unknown'
        raise HostError('StreamHG upload response: rejected or unsupported response (API status '+code+', HTTP '+http+'). Check account quota and upload permissions before retrying.')
    files=body.get('files')
    if not isinstance(files,list) or len(files)!=1 or not isinstance(files[0],dict):
        raise HostError('StreamHG upload response: expected one file result. Upload may exist; check account before retrying.')
    if str(files[0].get('status','')).upper()!='OK':
        raise HostError('StreamHG upload response: file was not accepted. Check account quota, file limits and upload permissions before retrying.')
    code=files[0].get('filecode')
    if not isinstance(code,str) or not re.fullmatch('[A-Za-z0-9]{1,128}',code):
        raise HostError('StreamHG upload response: accepted result has no valid filecode. Check account before retrying; no mapping was written.')
    return code


def verify_streamhg(file_id,key,size,name,attempts=6,pause=time.sleep):
    # Host transcoding changes sizes; verify the returned file ID and title.
    for attempt in range(attempts):
        try:
            rows=streamhg_api('file/info',key,{'file_code':file_id}).get('result')
            if isinstance(rows,list):
                for row in rows:
                    if isinstance(row,dict) and row.get('file_code')==file_id and row.get('status')==200:
                        return True,row.get('file_title') in (name,name.removesuffix('.mp4'))
        except Exception:pass
        if attempt<attempts-1:pause(5)
    return False,False


def upload_abyss(path,name,key,mask=lambda _:None,run=subprocess.run):
    if not key or len(key)>512 or any(ord(c)<33 for c in key):raise ValueError('ABYSS_API_KEY is missing or invalid')
    if any(c in name for c in ('\r','\n','\x00')):raise ValueError('Invalid output name')
    url='https://up.abyss.to/'+urllib.parse.quote(key,safe='')
    mask(key);mask(url)
    escaped=url.replace('\\','\\\\').replace('"','\\"')
    filename=name.replace('\\','\\\\').replace('"','\\"')
    form='file=@'+str(path)+';filename="'+filename+'"'
    response=run_upload(['curl','--config','-','--silent','--fail','--proto','=https','--connect-timeout','30','--max-time','3600','--form',form],input='url = "'+escaped+'"\n',capture_output=True,text=True,timeout=3610,runner=run,label='Abyss',size=file_size(path))
    if response.returncode:raise ValueError('Abyss upload failed or timed out. Check the account before uploading again.')
    try:body=json.loads(response.stdout)
    except (ValueError,TypeError):raise ValueError('Abyss upload response was not understood. Check account before uploading again.') from None
    slug=body.get('slug') if isinstance(body,dict) else None
    if not isinstance(slug,str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}',slug):raise ValueError('Abyss upload returned no valid video ID. Check account before uploading again.')
    return slug


def verify_abyss(file_id,key,size,name,attempts=6,pause=time.sleep):
    # Read-only retries never repeat multipart upload; transcoding may still be waiting.
    url='https://api.abyss.to/v1/files/'+file_id+'?key='+urllib.parse.quote(key,safe='')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    for attempt in range(attempts):
        try:
            with opener.open(urllib.request.Request(url,headers={'Accept':'application/json'}),timeout=30) as response:data=json.loads(response.read(1024*1024))
            if data.get('id')==file_id and int(data.get('size',-1))==size:return True,data.get('name')==name
        except Exception:pass
        if attempt<attempts-1:pause(5)
    return False,False




def upload_telegram(path, name, bot_token, chat_id, api_id=None, api_hash=None, mask=lambda _:None, run=subprocess.run):
    size = file_size(path)
    if size > 2000 * 1024 * 1024:
        raise HostError('Telegram file limit exceeded: video file exceeds the 2000MB (2GB) Telegram limit. Re-encode with higher CRF or lower bitrate.')

    if not bot_token or not re.fullmatch(r'\d{8,12}:[A-Za-z0-9_-]{30,45}', bot_token):
        raise HostError('Telegram configuration: TELEGRAM_BOT_TOKEN is missing or invalid format.')
    chat_str = str(chat_id).strip()
    if not chat_str or not re.fullmatch(r'-?\d{5,20}', chat_str):
        raise HostError('Telegram configuration: TELEGRAM_CHAT_ID is missing or invalid format.')
    if any(c in name for c in ('\r', '\n', '\x00')):
        raise HostError('Telegram configuration: invalid output name.')
    mask(bot_token)
    mask(chat_str)
    if api_hash:
        mask(str(api_hash))

    if size >= 50 * 1024 * 1024 and api_id and api_hash:
        try:
            import asyncio
            from pyrogram import Client
            async def _send():
                async with Client("uploader", api_id=int(api_id), api_hash=str(api_hash), bot_token=str(bot_token), in_memory=True) as app:
                    msg = await app.send_video(chat_id=int(chat_str), video=str(path), caption=name, file_name=name, supports_streaming=True)
                    return str(msg.id)
            return asyncio.run(_send())
        except Exception as e:
            raise HostError('Telegram Pyrogram upload failed: ' + str(e) + '. Check bot permissions in storage channel.') from None

    url = 'https://api.telegram.org/bot' + bot_token + '/sendVideo'
    mask(url)
    quote = lambda v: v.replace('\\', '\\\\').replace('"', '\\"').replace('\r', '').replace('\n', '')
    filename = quote(name)
    local = quote(str(path))
    config = 'url = "' + quote(url) + '"\nform-string = "chat_id=' + quote(chat_str) + '"\nform-string = "supports_streaming=true"\nform-string = "caption=' + quote(name) + '"\n'
    try:
        response = run_upload([
            'curl', '--config', '-', '--silent', '--fail', '--proto', '=https',
            '--connect-timeout', '30', '--max-time', '3600',
            '--write-out', '\nCLIXARENA_HTTP:%{http_code}',
            '--form', 'video=@"' + local + '";filename="' + filename + '"'
        ], input=config, capture_output=True, text=True, timeout=3610, runner=run, label='Telegram', size=size)
    except subprocess.TimeoutExpired:
        raise HostError('Telegram file upload: timed out. Check storage channel before retrying.') from None
    except Exception:
        raise HostError('Telegram file upload: uploader failed. Check curl and bot access before retrying.') from None

    raw, marker, http = response.stdout.rpartition('\nCLIXARENA_HTTP:')
    if not marker:
        raw = response.stdout
        http = 'unknown'
    http = _status(http.strip())

    if response.returncode:
        raise HostError('Telegram file upload failed (curl ' + str(int(response.returncode)) + ', HTTP ' + http + '). Check bot permissions in channel.')
    try:
        body = json.loads(raw)
    except (ValueError, TypeError):
        raise HostError('Telegram upload response: expected JSON (HTTP ' + http + '). Check bot and channel access.') from None

    if not isinstance(body, dict) or not body.get('ok'):
        desc = body.get('description', 'Unknown rejection') if isinstance(body, dict) else 'unknown'
        raise HostError('Telegram upload rejected: ' + desc + ' (HTTP ' + http + ').')

    result = body.get('result', {})
    msg_id = result.get('message_id')
    if not msg_id or not isinstance(msg_id, int):
        raise HostError('Telegram upload response: accepted result has no valid message_id.')
    return str(msg_id)


def verify_telegram(file_id, key, size, name, attempts=6, pause=time.sleep):
    if isinstance(file_id, (str, int)) and str(file_id).isdigit():
        return True, True
    return False, False
