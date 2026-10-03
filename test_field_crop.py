"""Manual crop recovery: explicit consent, isolation, async persistence and export."""
import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from unittest.mock import patch

from PIL import Image
from openpyxl import load_workbook
import review_app as app
from field_crop import CropService,frames,validate_regions,recognize_regions,target,text_rows
from field_regions import review_record
from learning_data import build_examples
from test_sheet_review import fixture


def crop_fixture(directory):
    state=fixture();state.update(schema_version=2,progress='Ready')
    state['records'][0]['fragments']=[dict(id='f1',page='source.jpg',box=[0,0,280,80],file='page-0.png',status='complete',column=0)]
    for name in ['page-0.png','line-1.png','line-2.png']:Image.new('RGB',(280,80),'white').save(directory/name)
    return state


def fake_recognize(engine,directory,operation,regions,progress):
    with patch('field_crop.read_line',side_effect=lambda *args:[dict(text='i',options=['i','t'],category='ambiguous',x=0,reason='Two readings'),
                dict(text='',options=[],category='unrecognized',x=10,reason='Unreadable')]):
        return recognize_regions(lambda *a,**kw:(None,None),directory,operation,regions,progress)


class CropTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name)
        self.state=crop_fixture(self.directory);self.lock=threading.RLock();self.services=[]
    def tearDown(self):
        for service in self.services:
            service.queue.put(None)
            if service.worker:service.worker.join(3)
        self.tmp.cleanup()
    def service(self,recognizer=fake_recognize):
        def load(job):return copy.deepcopy(self.state)
        def save(state):self.state=copy.deepcopy(state)
        service=CropService(load,save,lambda job:self.directory,self.lock,lambda *args:None,lambda:object(),recognizer)
        self.services.append(service);return service
    def request(self,**kwargs):
        return dict(job=self.state['id'],record='record-1',field=6,regions=[dict(fragment='f1',box=[10,10,80,30])],confirmed=True,**kwargs)
    def finish(self,service,task):
        service.queue.join();return service.status(task['job'],task['operation'])
    def test_requires_explicit_confirmation_and_printed_field(self):
        service=self.service();data=self.request();data.pop('confirmed')
        with self.assertRaisesRegex(ValueError,'Confirm'):service.submit(data)
        for f in [0,2,13,25,36,True,'6']:
            with self.subTest(field=f),self.assertRaises(ValueError):target(self.state,'record-1',f)
        self.assertFalse(service.tasks);self.assertIsNone(service.worker)
    def test_coordinates_are_record_bound_finite_and_nonoverlapping(self):
        rec=self.state['records'][0]
        for regions in [[dict(fragment='wrong',box=[1,1,10,10])],[dict(fragment='f1',box=[-1,0,80,20])],
                        [dict(fragment='f1',box=[1,1,2,20])],[dict(fragment='f1',box=[True,1,40,20])],
                        [dict(fragment='f1',box=[1,1,float('nan'),20])],
                        [dict(fragment='f1',box=[1,1,50,20]),dict(fragment='f1',box=[20,5,60,20])],[]]:
            with self.subTest(regions=regions),self.assertRaises(ValueError):validate_regions(self.state,rec,regions,self.directory)
    def test_detector_overlap_does_not_duplicate_digits(self):
        self.assertEqual(text_rows([[6,0,46,18],[41,0,75,18],[37,1,51,15]]),[[6,0,75,18]])
        self.assertEqual(text_rows([[1,1,30,18],[40,2,70,19],[2,23,30,40]]),[[1,1,70,19],[2,23,30,40]])
    def test_original_lines_remain_unchanged_and_neighbor_mapping_isolated(self):
        before=copy.deepcopy(self.state['records']);neighbor=app.sheet_data(self.state)[0]['cells'][3]
        service=self.service();task=service.submit(self.request());self.assertEqual(self.finish(service,task)['status'],'complete')
        self.assertEqual(self.state['records'],before)
        cell=app.sheet_data(self.state)[0]['cells'][6]
        self.assertEqual(cell['value'],'[i/t][?]');self.assertFalse(cell['manual']);self.assertEqual(cell['status'],'uncertain')
        self.assertTrue(cell['segments'][0]['editable']);self.assertEqual(app.sheet_data(self.state)[0]['cells'][3],neighbor)
        self.assertEqual(len(app.review_state(self.state)['records'][0]['lines']),3)
        learning=build_examples(self.state,self.directory)
        self.assertEqual(len(learning['field_mappings']),1);self.assertEqual(learning['examples'],[]);self.assertFalse(learning['model_updated'])
    def test_multiple_fragment_selections_preserve_order(self):
        self.state['records'][0]['fragments'].append(dict(id='f2',page='source.jpg',box=[0,40,280,80]))
        data=self.request();data['regions']=[dict(fragment='f2',box=[1,41,50,61]),dict(fragment='f1',box=[1,1,50,21])]
        service=self.service();task=service.submit(data);self.finish(service,task)
        selection=self.state['field_regions']['record-1:6']
        self.assertEqual([r['fragment'] for r in selection['regions']],['f2','f1'])
        self.assertEqual([l['source_box'] for l in selection['lines']],[[1,41,50,61],[1,1,50,21]])
        self.assertEqual(app.sheet_data(self.state)[0]['cells'][6]['value'],'[i/t][?] [i/t][?]')
    def test_reader_does_not_hold_state_lock_and_deduplicates_clicks(self):
        started=threading.Event();release=threading.Event()
        def recognize(*args):started.set();release.wait(3);return fake_recognize(*args)
        service=self.service(recognize)
        try:
            task=service.submit(self.request());self.assertTrue(started.wait(2))
            self.assertTrue(self.lock.acquire(timeout=.1));self.lock.release()
            self.assertEqual(service.submit(self.request())['operation'],task['operation'])
            changed=self.request();changed['regions'][0]['box']=[90,10,130,30]
            with self.assertRaisesRegex(ValueError,'progress'):service.submit(changed)
        finally:release.set()
        self.assertEqual(self.finish(service,task)['status'],'complete')
    def test_concurrent_human_edit_is_never_overwritten(self):
        def recognize(*args):
            self.state.setdefault('field_decisions',{})['record-1:6']='Human value'
            return fake_recognize(*args)
        service=self.service(recognize);task=service.submit(self.request())
        self.assertEqual(self.finish(service,task)['status'],'error')
        self.assertEqual(self.state['field_decisions']['record-1:6'],'Human value');self.assertNotIn('field_regions',self.state)
    def test_failure_keeps_previous_mapping(self):
        self.state['field_regions']={'record-1:6':dict(first='l2s0',last='l2s2')}
        def broken(*args):raise RuntimeError('Reader unavailable')
        service=self.service(broken);task=service.submit(self.request())
        self.assertEqual(self.finish(service,task)['status'],'error');self.assertEqual(self.state['field_regions']['record-1:6']['first'],'l2s0')
    def test_numeric_rule_filters_crop_options_without_confirming(self):
        def recognize(*args):
            result=fake_recognize(*args);s=result['lines'][0]['segments'][0];s.update(text='O',options=['O','0'])
            return result
        service=self.service(recognize);data=self.request();data['field']=18
        self.finish(service,service.submit(data));cell=app.sheet_data(self.state)[0]['cells'][18]
        self.assertIn('0',cell['value']);self.assertNotIn('[O/0]',cell['value']);self.assertFalse(cell['manual'])
        self.assertEqual(self.state['field_regions']['record-1:18']['lines'][0]['segments'][0]['text'],'O')


class CropApiTest(unittest.TestCase):
    def test_crop_character_confirmation_reload_export_reset(self):
        original_data,original_service=app.DATA,app.CROPS
        with tempfile.TemporaryDirectory() as directory:
            app.DATA=Path(directory);job='a'*32;dest=app.folder(job);dest.mkdir();app.save(crop_fixture(dest))
            app.CROPS=CropService(app.load,app.save,app.folder,app.LOCK,app.write_examples,lambda:object(),fake_recognize)
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            def request(path,data=None):
                req=urllib.request.Request(base+path,data=None if data is None else json.dumps(dict(job=job,**data)).encode(),headers={'X-Review-Token':app.TOKEN,'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=90) as response:return response.read()
            try:
                task=json.loads(request('/api/field-crop',dict(record='record-1',field=6,regions=[dict(fragment='f1',box=[10,10,80,30])],confirmed=True)))
                app.CROPS.queue.join();self.assertEqual(app.CROPS.status(job,task['operation'])['status'],'complete')
                loaded=json.loads(request('/api/state?job='+job));line=loaded['records'][0]['lines'][-1]
                self.assertTrue(request('/image?job='+job+'&name='+line['image']).startswith(b'\x89PNG'))
                request('/api/confirm',dict(segment=line['segments'][0]['id'],value='t'))
                sheet=json.loads(request('/api/sheet?job='+job));self.assertEqual(sheet[0]['cells'][6]['value'],'t[?]')
                basic=zipfile.ZipFile(io.BytesIO(request('/api/test-report',dict(include_project=False,outcome='pass',test='Crop review'))))
                self.assertFalse(any('/crop-' in n or '/selection-' in n for n in basic.namelist()))
                detailed=zipfile.ZipFile(io.BytesIO(request('/api/test-report',dict(include_project=True,outcome='pass',test='Crop review'))))
                self.assertIn('project/'+line['image'],detailed.namelist())
                self.assertTrue(any('/selection-' in n for n in detailed.namelist()))
                result=json.loads(request('/api/export',{}));book=load_workbook(io.BytesIO(request(result['url'])),read_only=True)
                self.assertEqual(list(book['Converted records'].values)[1][6],'t[?]');book.close()
                request('/api/field',dict(record='record-1',field=6,value='typed field'))
                learning=json.loads((dest/'learning.json').read_text());self.assertEqual(learning['field_mappings'][0]['confirmed_field_value'],'typed field')
                self.assertIsNone(learning['examples'][0]['training_text'],'Formatted whole field cannot certify unreviewed crop characters')
                request('/api/field',dict(record='record-1',field=6,value='',reset=True))
                request('/api/field-region',dict(record='record-1',field=6,reset=True))
                learning=json.loads((dest/'learning.json').read_text());self.assertEqual(learning['field_mappings'],[]);self.assertEqual(learning['examples'],[])
                saved=app.load(job);self.assertEqual(len(saved['field_crop_history']),1);self.assertEqual(len(saved['records'][0]['lines']),2)
            finally:
                app.CROPS.queue.put(None);app.CROPS.worker.join(3);server.shutdown();server.server_close();thread.join();app.DATA,app.CROPS=original_data,original_service
