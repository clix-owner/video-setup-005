import contextlib,io,json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import clixarena_video as p
class SoftOutputTests(unittest.TestCase):
 def test_arguments_resize_watermark_only_uploaded_subtitle_and_selected_audio(self):
  streams=[{'codec_type':'video','codec_name':'h264','width':1282,'height':534},{'codec_type':'audio','codec_name':'aac','tags':{'language':'hin'}},{'codec_type':'audio','codec_name':'eac3','tags':{'language':'tam'}},{'codec_type':'subtitle','codec_name':'ass'}]
  with contextlib.redirect_stdout(io.StringIO()):args=p.soft_mp4_args(streams,'0:a:1',10,20,'sin',{'height':720,'preset':'ultrafast'})
  graph=args[args.index('-filter_complex')+1]
  self.assertIn('pad=1280:720',graph);self.assertIn('text=CLIXARENA',graph);self.assertNotIn('ass=',graph)
  self.assertIn('1:s:0',args);self.assertNotIn('0:s',args);self.assertIn('0:a:1',args);self.assertEqual(args[args.index('-c:v')+1],'libx264');self.assertEqual(args[args.index('-c:a')+1],'aac');self.assertEqual(args[args.index('-preset')+1],'ultrafast');self.assertIn('language=tam',args)
 @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
 def test_real_mp4_has_watermark_one_selected_audio_and_only_switchable_sinhala(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'old.srt').write_text('1\n00:00:00,000 --> 00:00:01,200\nOLD SUBTITLE\n',encoding='utf-8')
   (root/'sinhala.srt').write_text('1\n00:00:00,000 --> 00:00:01,200\nසිංහල උපසිරැසි\n',encoding='utf-8')
   source=['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=320x180:r=10:d=1.5','-f','lavfi','-i','sine=frequency=440:duration=1.5','-f','lavfi','-i','sine=frequency=880:duration=1.5','-i','old.srt','-map','0:v','-map','1:a','-map','2:a','-map','3:s','-c:v','libx264','-preset','ultrafast','-c:a','aac','-c:s','srt','-metadata:s:a:0','language=hin','-metadata:s:a:1','language=tam','-t','1.5','-f','matroska','source.video']
   run=subprocess.run(source,cwd=root,capture_output=True);self.assertEqual(run.returncode,0,run.stderr.decode(errors='replace'))
   streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json','source.video'],cwd=root))['streams']
   with contextlib.redirect_stdout(io.StringIO()):args=p.soft_mp4_args(streams,'0:a:1',1.5,20,'sin',{'height':480,'preset':'ultrafast'})
   if os.name=='nt':
    shutil.copyfile(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/arialbd.ttf',root/'watermark.ttf')
    index=args.index('-filter_complex')+1;args[index]=args[index].replace('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf','watermark.ttf')
   run=subprocess.run(args+['out.mp4'],cwd=root,capture_output=True);self.assertEqual(run.returncode,0,run.stderr.decode(errors='replace'))
   out=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json','out.mp4'],cwd=root));video=next(s for s in out['streams'] if s['codec_type']=='video');audio=[s for s in out['streams'] if s['codec_type']=='audio'];subs=[s for s in out['streams'] if s['codec_type']=='subtitle']
   self.assertEqual((video['width'],video['height']),(854,480));self.assertEqual(video['codec_name'],'h264');self.assertEqual(len(audio),1);self.assertEqual(audio[0]['tags']['language'],'tam');self.assertEqual(len(subs),1);self.assertEqual(subs[0]['codec_name'],'mov_text');self.assertEqual(subs[0]['tags']['language'],'sin')
   extracted=subprocess.check_output(['ffmpeg','-v','error','-i','out.mp4','-map','0:s:0','-f','srt','-'],cwd=root).decode('utf-8');self.assertIn('සිංහල උපසිරැසි',extracted);self.assertNotIn('OLD SUBTITLE',extracted)
   pixels=subprocess.check_output(['ffmpeg','-v','error','-i','out.mp4','-frames:v','1','-pix_fmt','gray','-f','rawvideo','-'],cwd=root)
   self.assertGreater(max(pixels[440*854:]),30) # visible bottom watermark
   self.assertLess(max(pixels[:400*854]),15) # captions did not burn into black video
   with contextlib.redirect_stdout(io.StringIO()):off=p.soft_mp4_args(streams,'0:a:1',1.5,20,'sin',{'height':480,'preset':'ultrafast','watermark_enabled':False})
   run=subprocess.run(off+['off.mp4'],cwd=root,capture_output=True);self.assertEqual(run.returncode,0,run.stderr.decode(errors='replace'))
   raw=subprocess.check_output(['ffmpeg','-v','error','-i','off.mp4','-frames:v','1','-pix_fmt','gray','-f','rawvideo','-'],cwd=root);self.assertLess(max(raw),15)
   info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json','off.mp4'],cwd=root))['streams'];self.assertEqual(sum(x['codec_type']=='subtitle' for x in info),1)
if __name__=='__main__':unittest.main()
