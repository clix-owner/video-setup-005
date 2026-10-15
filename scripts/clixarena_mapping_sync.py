"""Remove only mappings whose individual file status is confirmed missing twice."""
import base64,json,os,re,time,urllib.request,urllib.error
from clixarena_video import api,decrypt_mappings,encrypt_mappings,mask,NoRedirect


def missing_ids(ids,result):
    if not isinstance(result,dict):return set()
    return {fid for fid in ids if isinstance(result.get(fid),dict) and type(result[fid].get('status')) is int and result[fid]['status']==404}


def confirmed_missing(ids,check,pause=time.sleep):
    first=missing_ids(ids,check(ids))
    if not first:return set()
    pause(5)
    return first & missing_ids(first,check(sorted(first)))


def prune(rows,missing):
    return [row for row in rows if row.get('file_id') not in missing]


def main():
    try:
        repo=os.environ['GITHUB_REPOSITORY'];ref=os.environ['GITHUB_REF_NAME'];token=os.environ['MAPPING_GITHUB_TOKEN']
        login=os.environ['STREAMTAPE_LOGIN'];key=os.environ['STREAMTAPE_KEY']
        if not all((login,key,token)) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError()
        for value in (token,login,key):mask(value)
        endpoint='https://api.github.com/repos/'+repo+'/contents/mappings.json'
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/json'}
        def request(method='GET',payload=None):
            url=endpoint+'?ref='+urllib.parse.quote(ref,safe='') if method=='GET' else endpoint
            req=urllib.request.Request(url,data=json.dumps(payload).encode() if payload else None,headers=headers,method=method)
            with opener.open(req,timeout=60) as response:return json.loads(response.read(8*1024**2))
        def check(ids):return api('file/info',{'login':login,'key':key,'file':','.join(ids)})
        for attempt in range(8):
            try:current=request()
            except urllib.error.HTTPError as error:
                if error.code==404:print('No mappings.json found; no changes.');return 0
                raise
            rows=decrypt_mappings(json.loads(base64.b64decode(current['content'])))
            ids=sorted({row['file_id'] for row in rows if isinstance(row.get('file_id'),str) and re.fullmatch('[A-Za-z0-9_-]{1,128}',row['file_id'])})
            missing=set()
            for offset in range(0,len(ids),100):missing.update(confirmed_missing(ids[offset:offset+100],check))
            updated=prune(rows,missing)
            if updated==rows:print('Mapping sync complete: no confirmed deleted files.');return 0
            content=json.dumps(encrypt_mappings(updated),indent=2)+'\n'
            payload={'branch':ref,'sha':current['sha'],'message':'Remove confirmed deleted Streamtape mappings','content':base64.b64encode(content.encode()).decode()}
            try:request('PUT',payload)
            except urllib.error.HTTPError as error:
                if error.code==409 and attempt<7:time.sleep(1);continue
                raise
            print('Mapping sync complete: removed '+str(len(rows)-len(updated))+' mapping(s). No video IDs or URLs logged.');return 0
        raise ValueError()
    except Exception:
        print('::error::Mapping sync could not complete. Unconfirmed files are preserved; check API availability, secrets and repository permissions. Raw responses suppressed.')
        return 1

if __name__=='__main__':raise SystemExit(main())
