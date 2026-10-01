import copy,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import review_app as app


class ScanReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='pixel-save-test-')
        self.original=app.DATA;app.DATA=Path(self.tmp.name)
        self.state=dict(id='f'*32,project_name='Recovery test',status='scanning',progress='Reading',
            pages=[dict(name='AQ159.jpg',file='page-0.png')],records=[],decisions={},history=[],schema_version=2)
        app.folder(self.state['id']).mkdir()
        Image.new('RGB',(100,100),'white').save(app.folder(self.state['id'])/'page-0.png')
        app.save(self.state)

    def tearDown(self):
        app.LIVE_PROGRESS.pop(self.state['id'],None)
        app.DATA=self.original;self.tmp.cleanup()

    def test_temporary_windows_replace_denial_retries(self):
        original=Path.replace;calls=[]
        def replace(path,target):
            calls.append(path)
            if len(calls)<3:raise PermissionError('Windows sharing violation')
            return original(path,target)
        self.state['decisions']={'char-1':'B'}
        with patch.object(Path,'replace',replace),patch.object(app.time,'sleep'):
            app.save(self.state)
        self.assertEqual(len(calls),3)
        self.assertEqual(app.load(self.state['id'])['decisions'],{'char-1':'B'})

    def test_persistent_denial_keeps_last_good_checkpoint(self):
        self.state['decisions']={'char-1':'B'}
        with patch.object(Path,'replace',side_effect=PermissionError('Denied')),patch.object(app.time,'sleep'):
            with self.assertRaises(PermissionError):app.save(self.state)
        self.assertEqual(app.load(self.state['id'])['decisions'],{})
        recovery=list(app.folder(self.state['id']).glob('state-*.tmp'))
        self.assertEqual(json.loads(recovery[0].read_text())['decisions'],{'char-1':'B'})

    def test_concurrent_polling_and_saves_keep_valid_json(self):
        errors=[]
        def reader():
            try:
                for _ in range(100):
                    self.assertEqual(app.load(self.state['id'])['id'],self.state['id'])
                    self.assertEqual(len(app.list_jobs()),1)
            except Exception as e:errors.append(e)
        threads=[threading.Thread(target=reader) for _ in range(3)]
        for thread in threads:thread.start()
        for i in range(40):self.state['progress']=str(i);app.save(self.state)
        for thread in threads:thread.join()
        self.assertFalse(errors);self.assertEqual(app.load(self.state['id'])['progress'],'39')

    def test_retry_keeps_failed_attempt_and_copies_original_pages(self):
        self.state.update(status='error',error='Interrupted',decisions={'old':'B'})
        app.save(self.state);before=copy.deepcopy(self.state)
        with patch.object(app,'scan'):
            new=app.retry_scan(self.state)
        self.assertEqual(app.load(self.state['id']),before)
        self.assertNotEqual(new['id'],self.state['id']);self.assertEqual(new['recovery_of'],self.state['id'])
        self.assertEqual(new['decisions'],{});self.assertEqual(new['records'],[])
        self.assertEqual((app.folder(new['id'])/'page-0.png').read_bytes(),(app.folder(self.state['id'])/'page-0.png').read_bytes())
        app.LIVE_PROGRESS.pop(new['id'],None)

    def test_progress_is_live_and_final_save_failure_never_reports_complete(self):
        block=dict(box=[0,0,100,100],column=0,block=0,first_in_column=True,open_bottom=False)
        box=[[5,5],[80,5],[80,20],[5,20]];snapshots=[]
        def read_line(*args):
            snapshots.append(copy.deepcopy(app.get_progress(self.state['id'])))
            return [dict(text='A',options=['A'],category='single',x=0)]
        engine=lambda *args,**kw:([box,box],0)
        original_save=app.save
        def save(state):
            if state['status']=='ready':raise PermissionError('Final file locked')
            return original_save(state)
        with patch('rapidocr_onnxruntime.RapidOCR',return_value=engine),patch('detect_records.blocks',return_value=[block]),patch.object(app,'read_header',return_value=('1234567890','1234567890')),patch.object(app,'read_line',side_effect=read_line),patch.object(app,'save',side_effect=save):
            app.scan(self.state)
        self.assertTrue(all(s['status']=='scanning' and s['scan_stats']['percent']<100 for s in snapshots))
        self.assertEqual(snapshots[1]['scan_stats']['text_regions'],1)
        final=app.get_progress(self.state['id'])
        self.assertEqual(final['status'],'error');self.assertNotEqual(final['scan_stats']['stage'],'complete')
        self.assertLess(final['scan_stats']['percent'],100)


if __name__=='__main__':unittest.main()
