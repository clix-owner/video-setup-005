import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import clixarena_hosts as hosts
import clixarena_hls as hls


class PreparedUploadTests(unittest.TestCase):
    def test_large_ts_uses_pyrogram_document(self):
        sent = []
        class FakeClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def send_document(self, **kwargs):
                sent.append(kwargs)
                return SimpleNamespace(id=101)
            async def send_video(self, **kwargs):
                raise AssertionError('TS must use send_document')
        module = SimpleNamespace(Client=FakeClient, utils=SimpleNamespace())
        with patch.dict(sys.modules, {'pyrogram': module}), patch.object(hosts, 'file_size', return_value=60*1024**2):
            result = hosts._upload_telegram_single('bundle.ts', 'Part 1.ts', 'token', '-1001234567890', 12345, 'hash', lambda _: None, None)
        self.assertEqual(result, '101')
        self.assertEqual(sent[0]['document'], 'bundle.ts')

    def test_ts_uses_document_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bundle.ts'
            path.write_bytes(b'G' * 188)
            calls = []
            def runner(args, **kwargs):
                calls.append((args, kwargs))
                return SimpleNamespace(returncode=0, stdout=json.dumps({'ok': True, 'result': {'message_id': 101}}))
            result = hosts._upload_telegram_single(path, 'Part 1.ts', 'test-token', '-1001234567890', None, None, lambda _: None, runner)
            self.assertEqual(result, '101')
            self.assertIn('/sendDocument', calls[0][1]['input'])
            self.assertNotIn('supports_streaming', calls[0][1]['input'])
            self.assertTrue(any(str(arg).startswith('document=@') for arg in calls[0][0]))

    def test_upload_returns_complete_index_only_after_all_bundles(self):
        with tempfile.TemporaryDirectory() as tmp:
            parts = [Path(tmp)/'part1.ts', Path(tmp)/'part2.ts']
            for p in parts:
                p.write_bytes(b'G' * 188)
            index = [[0,0,188,6.0], [1,0,188,4.0]]
            sent = []
            def send(path, name):
                sent.append(name)
                return str(100+len(sent))
            with patch.object(hls, 'package', return_value=(parts, index)):
                entry = hls.upload_hls('source.mp4', 'Movie.mp4', send)
            self.assertEqual(entry['parts'], ['101', '102'])
            self.assertEqual(entry['hls']['segments'], index)
            self.assertEqual(entry['hls']['sizes'], [188,188])
            self.assertEqual(sent, ['Movie - Part 1.ts', 'Movie - Part 2.ts'])
            with patch.object(hls, 'package', return_value=(parts, index)):
                with self.assertRaises(RuntimeError):
                    hls.upload_hls('source.mp4', 'Movie.mp4', lambda *a: (_ for _ in ()).throw(RuntimeError('Upload failed')))

    def test_large_primary_does_not_trigger_quality_reduction(self):
        path = SimpleNamespace(stat=lambda: SimpleNamespace(st_size=5000*1024**2))
        calls = []
        def prepared(path, name, *args, **kwargs):
            calls.append(path)
            return {'file_id': '101-102', 'parts': ['101','102']}
        with patch.object(hosts, 'get_video_dimensions', return_value=(1920,1080)), \
             patch.object(hosts, 'upload_telegram_hls', side_effect=prepared), \
             patch.object(hosts, 'transcode_resolution') as transcode:
            hosts.upload_telegram_multi(path, 'Movie.mp4', 'token', '-1001234567890')
            self.assertIs(calls[0], path)
            self.assertEqual([c.args[2] for c in transcode.call_args_list], [720,480])
            self.assertTrue(all(c.args[0] is path for c in transcode.call_args_list))

    def test_non_h264_input_fails_before_packaging(self):
        runner = lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps({'streams': [{'codec_type':'video','codec_name':'hevc'}]}))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'H.264/AAC'):
                hls.package('input.mp4', tmp, run=runner)


if __name__ == '__main__':
    unittest.main()
