"""Local-only portfolio server. Python 3.11+, standard library, SQLite."""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
APP = 'reservas'
DB = Path(os.environ.get('DEMO_DB', ROOT / 'demo.sqlite3'))
STAGES = ('Nuevo', 'En contacto', 'Propuesta', 'Ganado')
SERVICES = ('Consulta de diseño', 'Revisión de una web', 'Definición de un proyecto')


def connect():
    con = sqlite3.connect(DB, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute('CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
    return con


def clean(data, previous=None):
    if not isinstance(data, dict):
        raise ValueError('Se esperaba un objeto JSON.')
    def text(key, maximum):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError('Campo no válido: ' + key)
        return value.strip()
    if APP == 'crm':
        name, company, email = text('name', 80), text('company', 100), text('email', 120)
        if '@' not in email or '.' not in email.split('@')[-1]:
            raise ValueError('Correo no válido.')
        value = data.get('value')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1000000:
            raise ValueError('Importe no válido.')
        stage = data.get('stage')
        if stage not in STAGES:
            raise ValueError('Fase no válida.')
        note = data.get('note', '')
        if not isinstance(note, str) or len(note) > 500:
            raise ValueError('Nota demasiado larga.')
        return dict(name=name, company=company, email=email, value=value, stage=stage, note=note.strip())
    if previous:
        if set(data) != {'status'} or data['status'] != 'Cancelada':
            raise ValueError('Solo se permite cancelar una reserva existente.')
        return {k: v for k, v in previous.items() if k != 'id'} | {'status': 'Cancelada'}
    name, email = text('name', 80), text('email', 120)
    if '@' not in email or '.' not in email.split('@')[-1]:
        raise ValueError('Correo no válido.')
    if data.get('service') not in SERVICES:
        raise ValueError('Servicio no válido.')
    try:
        slot = datetime.strptime(data.get('date', '') + ' ' + data.get('time', ''), '%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo('Europe/Madrid'))
    except (ValueError, TypeError):
        raise ValueError('Fecha u hora no válida.')
    now = datetime.now(ZoneInfo('Europe/Madrid'))
    if slot <= now or slot.date() > (now + timedelta(days=90)).date() or slot.weekday() > 4 or not 9 <= slot.hour < 17 or slot.minute not in (0, 30):
        raise ValueError('Elige una hora futura laborable entre 09:00 y 16:30, dentro de los próximos 90 días.')
    return dict(name=name, email=email, service=data['service'], date=slot.strftime('%Y-%m-%d'), time=slot.strftime('%H:%M'), status='Confirmada')


def all_items(con):
    return [json.loads(row['body']) | {'id': row['id']} for row in con.execute('SELECT * FROM items ORDER BY rowid')]


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Do not log names, emails or submitted form content.

    def security_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")

    def reply(self, code, body):
        payload = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.security_headers()
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/items':
            with connect() as con:
                self.reply(200, all_items(con))
            return
        # Serve only explicit frontend assets, never database/source/config files.
        allowed = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css'}
        if path not in allowed:
            self.reply(404, {'error': 'No encontrado.'})
            return
        file = ROOT / allowed[path]
        mime = {'html': 'text/html; charset=utf-8', 'js': 'text/javascript; charset=utf-8', 'css': 'text/css; charset=utf-8'}
        payload = file.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime[file.suffix[1:]])
        self.send_header('Content-Length', str(len(payload)))
        self.security_headers()
        self.end_headers()
        self.wfile.write(payload)

    def mutate(self):
        path = urlsplit(self.path).path
        if not (path == '/api/items' or path.startswith('/api/items/')):
            return self.reply(404, {'error': 'No encontrado.'})
        # Local development only. Reject cross-origin browser mutations.
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
            return self.reply(403, {'error': 'Origen no permitido.'})
        identifier = path.removeprefix('/api/items').strip('/')
        try:
            if self.command != 'DELETE':
                if self.headers.get_content_type() != 'application/json':
                    return self.reply(415, {'error': 'Usa application/json.'})
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    return self.reply(413, {'error': 'Tamaño no permitido.'})
                data = json.loads(self.rfile.read(length))
            with connect() as con:
                con.execute('BEGIN IMMEDIATE')  # Serialize conflict check and insert.
                current = con.execute('SELECT body FROM items WHERE id=?', (identifier,)).fetchone() if identifier else None
                if self.command in ('PUT', 'DELETE') and not current:
                    return self.reply(404, {'error': 'Registro no encontrado.'})
                if self.command == 'DELETE':
                    if APP != 'crm':
                        return self.reply(405, {'error': 'Cancela la reserva en lugar de eliminarla.'})
                    con.execute('DELETE FROM items WHERE id=?', (identifier,))
                    con.commit()
                    return self.reply(200, {'deleted': True})
                if self.command == 'POST' and identifier:
                    return self.reply(400, {'error': 'Ruta de creación no válida.'})
                previous = json.loads(current['body']) if current else None
                cleaned = clean(data, previous)
                if APP == 'reservas' and self.command == 'POST':
                    if any(x['date'] == cleaned['date'] and x['time'] == cleaned['time'] and x['status'] == 'Confirmada' for x in all_items(con)):
                        return self.reply(409, {'error': 'Esta hora ya está ocupada. Elige otra.'})
                if self.command == 'POST':
                    identifier = str(uuid.uuid4())
                    con.execute('INSERT INTO items VALUES (?,?)', (identifier, json.dumps(cleaned)))
                else:
                    con.execute('UPDATE items SET body=? WHERE id=?', (json.dumps(cleaned), identifier))
                con.commit()
                return self.reply(201 if self.command == 'POST' else 200, cleaned | {'id': identifier})
        except (ValueError, TypeError, KeyError) as error:
            return self.reply(400, {'error': str(error)})
        except sqlite3.Error:
            return self.reply(503, {'error': 'No se pudo guardar. Vuelve a intentarlo.'})

    do_POST = mutate
    do_PUT = mutate
    do_DELETE = mutate


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Servidor local de muestra. No exponer a Internet.')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    connect().close()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, directory=str(ROOT)))
    print(f'Demo local ({APP}): http://127.0.0.1:{args.port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
