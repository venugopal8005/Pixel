"""Exercise persistence and real XLSX export against an isolated local test server."""
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from PIL import Image
from openpyxl import load_workbook
import review_app as app
from test_sheet_review import fixture


class SheetApiTest(unittest.TestCase):
    def test_corrections_reload_export_and_reset(self):
        original=app.DATA
        with tempfile.TemporaryDirectory(prefix='pixel-sheet-test-') as root:
            app.DATA=Path(root)
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                state=fixture();directory=app.folder(state['id']);directory.mkdir()
                for name in ['line-1.png','line-2.png','page-0.png']:Image.new('RGB',(280,80),'white').save(directory/name)
                app.save(state)
                base=f'http://127.0.0.1:{server.server_port}'
                def request(path,data=None):
                    req=urllib.request.Request(base+path,data=None if data is None else json.dumps(dict(job=state['id'],**data)).encode(),
                        headers={'X-Review-Token':app.TOKEN,'Content-Type':'application/json'})
                    with urllib.request.urlopen(req,timeout=100) as res:return res.read(),res.headers
                request('/api/confirm',dict(segment='l2s4',value='B'))
                request('/api/field',dict(record='record-1',field=6,value='Entered address'))
                saved=json.loads(request('/api/state?job='+state['id'])[0])
                self.assertEqual(saved['decisions']['l2s4'],'B')
                sheet=json.loads(request('/api/sheet?job='+state['id'])[0])
                self.assertEqual(sheet[0]['cells'][6]['status'],'confirmed')
                result=json.loads(request('/api/export',{})[0]);data,headers=request(result['url'])
                self.assertIn('attachment',headers['Content-Disposition'])
                book=load_workbook(io.BytesIO(data),read_only=True)
                values=list(book['Converted records'].values)[1]
                self.assertEqual(values[6],'Entered address')
                self.assertEqual(values[3],'Lid/B888/6677-e6-1234567')
                self.assertIn('[0/O]',values[1]);self.assertEqual(values[5],'[?]')
                book.close()
                request('/api/field',dict(record='record-1',field=6,value='',reset=True))
                sheet=json.loads(request('/api/sheet?job='+state['id'])[0])
                self.assertEqual(sheet[0]['cells'][6]['value'],'[?]')
            finally:
                server.shutdown();server.server_close();thread.join();app.DATA=original


if __name__=='__main__':unittest.main()
