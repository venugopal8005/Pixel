"""Image filters retain whole records, stable identities, and complete exports."""
import copy
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image
import review_app as app
from test_sheet_review import fixture


def image_fixture():
    state=fixture()
    state.update(schema_version=2,created_date='10/11/2026',project_name='Image navigation',progress='Ready')
    state['pages']=[dict(name=f'AQ{i+1}.jpg',file=f'page-{i}.png') for i in range(3)]
    template=state['records'][0]
    state['records']=[]
    for i,sources in enumerate([[0],[0,1],[1],[0]]):
        record=copy.deepcopy(template)
        record['key']=f'record-{i}';record['record_id']=str(1800000000+i)
        record['fragments']=[dict(id=f'r{i}-p{page}',page=f'AQ{page+1}.jpg',file=f'page-{page}.png',
            box=[0,0,400,200],column=0,status='record_start' if j==0 else 'continuation_inferred') for j,page in enumerate(sources)]
        for j,line in enumerate(record['lines']):
            line['id']=f'r{i}-'+line['id'];line['page']=f'AQ{sources[min(j,len(sources)-1)]+1}.jpg'
            for segment in line['segments']:segment['id']=f'r{i}-'+segment['id']
        if i==3:record.pop('fragments') # Existing scans without a fragment ledger.
        state['records'].append(record)
    return state


class ImageNavigationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='pixel-images-')
        self.previous=app.DATA;app.DATA=Path(self.tmp.name)
        self.state=image_fixture()
        directory=app.folder(self.state['id']);directory.mkdir()
        for page in self.state['pages']:Image.new('RGB',(800,1000),'white').save(directory/page['file'])
        app.save(self.state)
        class QuietHandler(app.Handler):
            def log_message(self,*args):pass
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        app.DATA=self.previous;self.tmp.cleanup()

    def request(self,path,data=None,binary=False):
        req=urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}'+path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'X-Review-Token':app.TOKEN,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as response:
            return response.read() if binary else json.load(response)

    def view(self,image=None,offset=0):
        return self.request('/api/workspace?job='+self.state['id']+'&offset='+str(offset)+(('&image='+image) if image else ''))

    def test_continuation_appears_in_both_filters_without_trimming_or_duplicate_all_rows(self):
        before=copy.deepcopy(self.state)
        all_rows=self.view();left=self.view('page-0.png');right=self.view('page-1.png')
        self.assertEqual([r['key'] for r in all_rows['rows']],['record-0','record-1','record-2','record-3'])
        self.assertEqual([r['key'] for r in left['rows']],['record-0','record-1','record-3'])
        self.assertEqual([r['key'] for r in right['rows']],['record-1','record-2'])
        shared_left=left['state']['records'][1];shared_right=right['state']['records'][0]
        self.assertEqual(shared_left,shared_right)
        self.assertEqual(len(shared_left['crop_frames']),2)
        self.assertEqual(shared_left['source_images'],['page-0.png','page-1.png'])
        self.assertEqual([r['project_row'] for r in right['state']['records']],[2,3])
        self.assertEqual(right['state']['record_total'],2)
        self.assertEqual(right['state']['project_record_total'],4)
        self.assertEqual([p['records'] for p in right['state']['image_navigation']],[3,2,0])
        self.assertEqual([p['shared'] for p in right['state']['image_navigation']],[1,1,0])
        self.assertEqual(app.load(self.state['id']),before)

    def test_correction_is_shared_between_views_and_export_keeps_all_records(self):
        self.request('/api/field',dict(job=self.state['id'],record='record-1',field=6,value='Shared corrected address'))
        for image,row in [('page-0.png',1),('page-1.png',0)]:
            view=self.view(image)
            self.assertEqual(view['rows'][row]['cells'][6]['value'],'Shared corrected address')
            self.assertEqual(view['rows'][row]['cells'][6]['status'],'confirmed')
        export=app.export_data(app.load(self.state['id']))
        self.assertEqual(len(export['rows']),4)
        self.assertEqual(export['rows'][1][6],'Shared corrected address')

    def test_empty_image_and_unknown_image_are_distinct(self):
        empty=self.view('page-2.png')
        self.assertEqual(empty['rows'],[])
        self.assertEqual(empty['state']['record_total'],0)
        self.assertEqual(empty['state']['image_filter'],'page-2.png')
        self.assertEqual(empty['state']['project_record_total'],4)
        with self.assertRaises(urllib.error.HTTPError):self.view('page-99.png')

    def test_filtered_pagination_uses_global_project_numbers(self):
        records=[]
        for i in range(120):
            record=copy.deepcopy(self.state['records'][0 if i%2==0 else 2])
            record['key']=f'record-{i}';records.append(record)
        self.state['records']=records;app.save(self.state)
        view=self.view('page-1.png',50)
        self.assertEqual(len(view['rows']),10)
        self.assertEqual(view['state']['record_offset'],50)
        self.assertEqual(view['state']['record_total'],60)
        self.assertEqual([r['project_row'] for r in view['state']['records']],list(range(102,121,2)))

    def test_thumbnail_is_bounded_and_rejects_other_assets(self):
        query='?job='+self.state['id']+'&name='
        raw=self.request('/thumbnail'+query+'page-0.png',binary=True)
        with Image.open(io.BytesIO(raw)) as thumbnail:
            self.assertLessEqual(thumbnail.width,120);self.assertLessEqual(thumbnail.height,160)
            self.assertEqual(thumbnail.format,'JPEG')
        self.assertTrue((app.folder(self.state['id'])/'thumb-page-0.jpg').exists())
        self.assertEqual(raw,self.request('/thumbnail'+query+'page-0.png',binary=True))
        with self.assertRaises(urllib.error.HTTPError):self.request('/thumbnail'+query+'state.json')


if __name__=='__main__':unittest.main()
