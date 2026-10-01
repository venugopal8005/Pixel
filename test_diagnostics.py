import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from unittest.mock import patch
from PIL import Image
import review_app as app
import diagnostics
from test_sheet_review import fixture


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='pixel-diagnostics-')
        self.previous=app.DATA;app.DATA=Path(self.tmp.name)
        self.state=fixture();self.state['project_name']='Diagnostic test'
        directory=app.folder(self.state['id']);directory.mkdir()
        for name in ('page-0.png','line-1.png','line-2.png'):
            Image.new('RGB',(30,30),'white').save(directory/name)
        app.save(self.state)
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        app.DATA=self.previous;self.tmp.cleanup()

    def post(self,path,data,token=None):
        request=urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}'+path,
            data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Review-Token':app.TOKEN if token is None else token})
        return urllib.request.urlopen(request,timeout=10)

    def bundle(self,**kwargs):
        response=self.post('/api/test-report',dict(job=self.state['id'],outcome='fail',test='Character correction',**kwargs))
        with response:
            self.assertEqual(response.headers['Content-Type'],'application/zip')
            self.assertTrue(response.headers['X-Pixel-Request-ID'])
            raw=response.read()
        archive=zipfile.ZipFile(io.BytesIO(raw))
        return archive,json.loads(archive.read('report.json'))

    def test_basic_report_omits_project_data_and_session_token_without_mutating_state(self):
        before=(app.folder(self.state['id'])/'state.json').read_bytes()
        archive,report=self.bundle(context={'field':4,'token':app.TOKEN},events=[{'kind':'error','message':'Secret '+app.TOKEN}])
        self.assertEqual(set(archive.namelist()),{'report.json','READ-ME.txt'})
        text=archive.read('report.json').decode()
        self.assertNotIn(app.TOKEN,text);self.assertNotIn('Lid/B888',text)
        self.assertEqual(report['project']['record_candidates'],1)
        self.assertEqual(report['project']['pages'][0]['name'],'source.jpg')
        self.assertEqual(report['context'],{'field':4})
        self.assertEqual(before,(app.folder(self.state['id'])/'state.json').read_bytes())
        self.assertEqual(len(list((app.DATA/'_diagnostics/reports').glob('*.zip'))),1)

    def test_opt_in_captures_saved_corrections_and_available_source_assets(self):
        self.state['decisions']={'l2s4':'B'};app.save(self.state)
        archive,report=self.bundle(include_project=True)
        snapshot=json.loads(archive.read('project/state.json'))
        self.assertEqual(snapshot['decisions'],{'l2s4':'B'})
        self.assertIn('project/page-0.png',archive.namelist())
        self.assertIn('project/line-1.png',archive.namelist())
        self.assertTrue(report['include_project']);self.assertFalse(report['omitted_files'])

    def test_error_trace_and_request_id_correlate_to_report(self):
        with patch.object(app,'sheet_data',side_effect=RuntimeError('diagnostic failure example')):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(f'http://127.0.0.1:{self.server.server_port}/api/sheet?job='+self.state['id'])
        error=caught.exception;request_id=error.headers['X-Pixel-Request-ID'];error.close()
        _,report=self.bundle()
        logged=next(e for e in report['server_events'] if e.get('request_id')==request_id)
        self.assertEqual(logged['status'],400)
        self.assertIn('RuntimeError',logged['traceback'])
        self.assertEqual(logged['error'],'diagnostic failure example')

    def test_failed_or_missing_project_does_not_prevent_a_report(self):
        self.state.update(status='error',error='Scan failed');app.save(self.state)
        _,report=self.bundle();self.assertEqual(report['project']['status'],'error')
        (app.folder(self.state['id'])/'state.json').write_text('{corrupt')
        archive,report=self.bundle(include_project=True)
        self.assertTrue(report['state_read_error']);self.assertIsNone(report['project'])
        self.assertEqual(set(archive.namelist()),{'report.json','READ-ME.txt'})

    def test_no_project_and_invalid_session(self):
        with self.post('/api/test-report',dict(outcome='pass',test='Home page')) as response:
            archive=zipfile.ZipFile(io.BytesIO(response.read()))
            self.assertIsNone(json.loads(archive.read('report.json'))['project'])
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('/api/test-report',{},token='wrong')
        self.assertEqual(caught.exception.code,403);caught.exception.close()

    def test_only_selected_project_files_and_events_are_included(self):
        self.state['pages'].append({'name':'bad source','file':'../outside.txt'})
        (app.DATA/'outside.txt').write_text('PRIVATE EXTERNAL CONTENT')
        app.save(self.state)
        diagnostics.log_event(app.DATA/'_diagnostics','test',job='b'*32,error='other project error')
        archive,report=self.bundle(include_project=True)
        self.assertTrue(report['omitted_files'])
        self.assertNotIn('PRIVATE EXTERNAL CONTENT',''.join(archive.read(n).decode(errors='replace') for n in archive.namelist()))
        self.assertNotIn('other project error',json.dumps(report))

    def test_log_failure_does_not_raise(self):
        with patch.object(Path,'mkdir',side_effect=PermissionError('No disk access')):
            diagnostics.log_event(app.DATA,'test',error='Example')


if __name__=='__main__':unittest.main()
