"""Abyss upload via its documented multipart endpoint. No upload retries."""
import json,re,subprocess,time,urllib.parse,urllib.request,urllib.error


def selected_host(layout):
    value=layout.get('uploadHost','streamtape')
    if value not in ('streamtape','abyss'):raise ValueError('Choose Streamtape or Abyss')
    return value


def merge_provider_mapping(rows,identity,file_id,provider='streamtape'):
    if provider not in ('streamtape','abyss') or not isinstance(file_id,str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}',file_id):raise ValueError('Invalid host or video ID')
    if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ValueError('Invalid mappings')
    key=('mal_id' if 'mal_id' in identity else 'anilist_id') if identity['type']=='anime' else 'tmdb_id'
    matches=lambda row:all(row.get(k)==identity.get(k) for k in ('type',key,'season','episode'))
    providers={}
    for row in rows:
        if not matches(row):continue
        if isinstance(row.get('providers'),dict):providers.update(row['providers'])
        if row.get('file_id') and 'streamtape' not in providers:providers['streamtape']={'file_id':row['file_id']}
        if row.get('abyss_id') and 'abyss' not in providers:providers['abyss']={'file_id':row['abyss_id']}
    providers[provider]={'file_id':file_id}
    item=dict(identity,provider=provider,providers=providers)
    if 'streamtape' in providers:item['file_id']=providers['streamtape']['file_id']
    if 'abyss' in providers:item['abyss_id']=providers['abyss']['file_id']
    return [row for row in rows if not matches(row)]+[item]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def upload_abyss(path,name,key,mask=lambda _:None,run=subprocess.run):
    if not key or len(key)>512 or any(ord(c)<33 for c in key):raise ValueError('ABYSS_API_KEY is missing or invalid')
    if any(c in name for c in ('\r','\n','\x00')):raise ValueError('Invalid output name')
    url='https://up.abyss.to/'+urllib.parse.quote(key,safe='')
    mask(key);mask(url)
    escaped=url.replace('\\','\\\\').replace('"','\\"')
    filename=name.replace('\\','\\\\').replace('"','\\"')
    form='file=@'+str(path)+';filename="'+filename+'"'
    response=run(['curl','--config','-','--silent','--fail','--proto','=https','--connect-timeout','30','--max-time','3600','--form',form],input='url = "'+escaped+'"\n',capture_output=True,text=True,timeout=3610)
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
