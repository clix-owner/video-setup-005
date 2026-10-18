import contextlib,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import clixarena_video as pipeline
from clixarena_hosts import selected_hosts
class DualUploadTests(unittest.TestCase):
 def test_order_validation(self):
  for first,second in [('streamtape','abyss'),('abyss','streamhg'),('streamhg','streamtape')]:
   self.assertEqual(selected_hosts({'uploadHost':first,'secondUploadHost':second}),[first,second])
  self.assertEqual(selected_hosts({}),['streamtape'])
  for second in ('streamtape','unknown',[],None):
   with self.assertRaises(ValueError):selected_hosts({'secondUploadHost':second})
 def test_same_file_order_and_no_second_encode(self):
  path=Path('already-encoded.mp4');calls=[]
  def one(p,name,values,provider):calls.append((p,name,provider))
  with patch.dict(os.environ,{'OVERLAY_LAYOUT':json.dumps({'uploadHost':'abyss','secondUploadHost':'streamhg'})}),patch.object(pipeline,'complete_upload_one',one),contextlib.redirect_stdout(io.StringIO()):
   pipeline.complete_upload(path,'Title.mp4',{})
  self.assertEqual(calls,[(path,'Title.mp4','abyss'),(path,'Title.mp4','streamhg')])
 def test_either_failure_continues_once_and_marks_job_failed_without_raw_error(self):
  for failed in ('streamtape','abyss'):
   calls=[];out=io.StringIO()
   def one(p,n,v,provider):
    calls.append(provider)
    if provider==failed:raise ValueError('SECRET-RAW-ERROR')
   with patch.dict(os.environ,{'OVERLAY_LAYOUT':'{"uploadHost":"streamtape","secondUploadHost":"abyss"}'}),patch.object(pipeline,'complete_upload_one',one),contextlib.redirect_stdout(out):
    with self.assertRaises(pipeline.DownloadError) as error:pipeline.complete_upload(Path('out.mp4'),'Title.mp4',{})
   self.assertEqual(calls,['streamtape','abyss']);self.assertIn(failed,str(error.exception));self.assertNotIn('SECRET',out.getvalue()+str(error.exception))
 def test_encrypted_receipt_preserves_both_ids_even_when_repository_save_fails(self):
  identity={'type':'movie','tmdb_id':1,'season':0,'episode':0}
  with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'OVERLAY_LAYOUT':json.dumps({'mapping':identity}),'GITHUB_WORKSPACE':directory,'GITHUB_REPOSITORY':'','MAPPING_PASSWORD':'test-password'}),patch.object(pipeline,'external_subtitle_mapping',return_value={}):
   for provider,id in [('streamtape','first-id'),('abyss','second-id')]:
    with self.assertRaises(ValueError):pipeline.save_mapping(id,provider)
   raw=(Path(directory)/'mapping-result.json').read_text();self.assertNotIn('first-id',raw);self.assertNotIn('second-id',raw)
   rows=pipeline.decrypt_mappings(json.loads(raw));self.assertEqual(rows[0]['file_id'],'first-id');self.assertEqual(rows[0]['abyss_id'],'second-id')
if __name__=='__main__':unittest.main()
