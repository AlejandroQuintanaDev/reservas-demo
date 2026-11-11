import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import partial
from http.server import ThreadingHTTPServer
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location('demo_server', Path(__file__).with_name('server.py'))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        server.DB = Path(cls.temp.name) / 'test.sqlite3'
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), partial(server.Handler, directory=str(server.ROOT)))
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def setUp(self):
        with server.connect() as con:
            con.execute('DELETE FROM items')

    def request(self, method='GET', path='/api/items', data=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def payload(self):
        if server.APP == 'crm':
            return dict(name='Ana Demo', company='Empresa de muestra', email='ana@example.com', value=500, stage='Nuevo', note='Revisión')
        day = datetime.now(ZoneInfo('Europe/Madrid')).date() + timedelta(days=1)
        while day.weekday() > 4:
            day += timedelta(days=1)
        return dict(name='Ana Demo', email='ana@example.com', service='Consulta de diseño', date=str(day), time='10:00')

    def test_empty_list(self):
        self.assertEqual(self.request(), (200, []))

    def test_create_persist_and_update(self):
        code, item = self.request('POST', data=self.payload())
        self.assertEqual(code, 201)
        self.assertEqual(self.request()[1][0]['name'], 'Ana Demo')
        update = self.payload() | {'stage': 'Ganado'} if server.APP == 'crm' else {'status': 'Cancelada'}
        code, changed = self.request('PUT', '/api/items/' + item['id'], update)
        self.assertEqual(code, 200)
        self.assertEqual(changed['stage'] if server.APP == 'crm' else changed['status'], 'Ganado' if server.APP == 'crm' else 'Cancelada')

    def test_invalid_payload(self):
        for data in ({}, [], self.payload() | {'email': 'invalid'}, self.payload() | {'name': ' '}):
            self.assertEqual(self.request('POST', data=data)[0], 400)

    def test_missing_record(self):
        self.assertEqual(self.request('PUT', '/api/items/missing', self.payload())[0], 404)

    def test_cross_origin_is_rejected(self):
        self.assertEqual(self.request('POST', data=self.payload(), origin='https://untrusted.example')[0], 403)

    def test_private_files_not_served(self):
        for path in ['/server.py', '/demo.sqlite3', '/.env', '/../../etc/passwd']:
            self.assertEqual(self.request(path=path)[0], 404)

    def test_conflict_or_crm_delete(self):
        code, item = self.request('POST', data=self.payload())
        self.assertEqual(code, 201)
        if server.APP == 'crm':
            self.assertEqual(self.request('DELETE', '/api/items/' + item['id'])[0], 200)
            self.assertEqual(self.request()[1], [])
        else:
            self.assertEqual(self.request('POST', data=self.payload())[0], 409)
            self.assertEqual(self.request('PUT', '/api/items/' + item['id'], {'status': 'Cancelada'})[0], 200)
            self.assertEqual(self.request('POST', data=self.payload())[0], 201)

    def test_concurrent_booking_has_one_winner(self):
        if server.APP != 'reservas':
            self.skipTest('Solo se aplica a reservas.')
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(lambda _: self.request('POST', data=self.payload())[0], range(2)))
        self.assertEqual(sorted(codes), [201, 409])
        self.assertEqual(len(self.request()[1]), 1)

    def test_boundary_validation(self):
        if server.APP == 'crm':
            self.assertEqual(self.request('POST', data=self.payload() | {'value': -1})[0], 400)
            self.assertEqual(self.request('POST', data=self.payload() | {'stage': 'bad'})[0], 400)
        else:
            self.assertEqual(self.request('POST', data=self.payload() | {'date': '2020-01-01'})[0], 400)
            self.assertEqual(self.request('POST', data=self.payload() | {'time': '10:15'})[0], 400)
            self.assertEqual(self.request('POST', data=self.payload() | {'service': 'bad'})[0], 400)


if __name__ == '__main__':
    unittest.main()
