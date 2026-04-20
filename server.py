#!/usr/bin/env python3
"""
ExamPrep Question Bank Server
REST API with session-based authentication and role enforcement.
Roles: admin (full access), user (read + practice only)
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import sqlite3
import os
import hashlib
import secrets
import string
from urllib.parse import urlparse
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'question_bank.db')

# In-memory session store: token -> {user_id, username, role, expires}
SESSIONS = {}
SESSION_HOURS = 24


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token():
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(64))

def get_session(token):
    if not token or token not in SESSIONS:
        return None
    session = SESSIONS[token]
    if datetime.now() > session['expires']:
        del SESSIONS[token]
        return None
    return session

def get_token_from_request(handler):
    auth = handler.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    return ''


class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()

    def conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def init_db(self):
        with self.conn() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    username   TEXT NOT NULL UNIQUE,
                    password   TEXT NOT NULL,
                    role       TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS questions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    text        TEXT NOT NULL,
                    year        TEXT,
                    exam_source TEXT,
                    topics      TEXT,
                    skills      TEXT,
                    answers     TEXT,
                    explanation TEXT,
                    image       TEXT,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );
            ''')
            row = db.execute('SELECT COUNT(*) FROM users').fetchone()
            if row[0] == 0:
                now = datetime.now().isoformat()
                db.execute('INSERT INTO users (username,password,role,created_at) VALUES (?,?,?,?)',
                           ('admin', hash_password('admin123'), 'admin', now))
                db.execute('INSERT INTO users (username,password,role,created_at) VALUES (?,?,?,?)',
                           ('user', hash_password('user123'), 'user', now))
                db.commit()
                print('Default accounts created:')
                print('  admin / admin123  (administrator)')
                print('  user  / user123   (read-only)')
        print(f'Database ready: {self.db_path}')

    def get_user_by_credentials(self, username, password):
        with self.conn() as db:
            row = db.execute('SELECT * FROM users WHERE username=? AND password=?',
                             (username, hash_password(password))).fetchone()
            return dict(row) if row else None

    def get_all_users(self):
        with self.conn() as db:
            rows = db.execute('SELECT id,username,role,created_at FROM users ORDER BY id').fetchall()
            return [dict(r) for r in rows]

    def add_user(self, username, password, role='user'):
        with self.conn() as db:
            db.execute('INSERT INTO users (username,password,role,created_at) VALUES (?,?,?,?)',
                       (username, hash_password(password), role, datetime.now().isoformat()))
            db.commit()

    def update_user_password(self, user_id, new_password):
        with self.conn() as db:
            db.execute('UPDATE users SET password=? WHERE id=?', (hash_password(new_password), user_id))
            db.commit()

    def delete_user(self, user_id):
        with self.conn() as db:
            db.execute('DELETE FROM users WHERE id=?', (user_id,))
            db.commit()

    def get_all_questions(self):
        with self.conn() as db:
            rows = db.execute('SELECT * FROM questions ORDER BY id DESC').fetchall()
        result = []
        for row in rows:
            q = dict(row)
            q['topics']  = json.loads(q['topics'])  if q['topics']  else []
            q['skills']  = json.loads(q['skills'])  if q['skills']  else []
            q['answers'] = json.loads(q['answers']) if q['answers'] else None
            result.append(q)
        return result

    def add_question(self, d):
        now = datetime.now().isoformat()
        with self.conn() as db:
            cur = db.execute(
                'INSERT INTO questions (text,year,exam_source,topics,skills,answers,explanation,image,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                (d.get('text',''), d.get('year',''), d.get('examSource',''),
                 json.dumps(d.get('topics',[])), json.dumps(d.get('skills',[])),
                 json.dumps(d.get('answers')), d.get('explanation',''), d.get('image'), now, now))
            db.commit()
            return cur.lastrowid

    def update_question(self, qid, d):
        now = datetime.now().isoformat()
        with self.conn() as db:
            db.execute(
                'UPDATE questions SET text=?,year=?,exam_source=?,topics=?,skills=?,answers=?,explanation=?,image=?,updated_at=? WHERE id=?',
                (d.get('text',''), d.get('year',''), d.get('examSource',''),
                 json.dumps(d.get('topics',[])), json.dumps(d.get('skills',[])),
                 json.dumps(d.get('answers')), d.get('explanation',''), d.get('image'), now, qid))
            db.commit()

    def delete_question(self, qid):
        with self.conn() as db:
            db.execute('DELETE FROM questions WHERE id=?', (qid,))
            db.commit()


class RequestHandler(BaseHTTPRequestHandler):
    db = Database(DB_PATH)

    def _headers(self, status=200, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def _json(self, data, status=200):
        self._headers(status)
        self.wfile.write(json.dumps(data).encode())

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length).decode()) if length else {}

    def _serve_file(self, filepath, content_type='text/html'):
        base = os.path.dirname(os.path.abspath(__file__))
        full = os.path.join(base, filepath)
        try:
            with open(full, 'rb') as f:
                self._headers(content_type=content_type)
                self.wfile.write(f.read())
        except FileNotFoundError:
            self._json({'error': 'File not found'}, 404)

    def _auth(self, require_admin=False):
        token = get_token_from_request(self)
        session = get_session(token)
        if not session:
            self._json({'error': 'Not authenticated'}, 401)
            return None
        if require_admin and session['role'] != 'admin':
            self._json({'error': 'Admin access required'}, 403)
            return None
        return session

    def log_message(self, fmt, *args):
        print(f'[{self.log_date_time_string()}] {fmt % args}')

    def do_OPTIONS(self):
        self._headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':            return self._serve_file('exam-prep.html')
        if path == '/login':       return self._serve_file('login.html')
        if path == '/practice-exam.html': return self._serve_file('practice-exam.html')
        if path.startswith('/icons/'):
            content_type = 'image/png'
            if path.endswith('.jpg') or path.endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif path.endswith('.webp'):
                content_type = 'image/webp'
            elif path.endswith('.svg'):
                content_type = 'image/svg+xml'
            return self._serve_file(path.lstrip('/'), content_type=content_type)
        
        if path == '/manifest.webmanifest':
            return self._serve_file('manifest.webmanifest', content_type='application/manifest+json')
        
        if path == '/sw.js':
            return self._serve_file('sw.js', content_type='application/javascript')

        if path == '/api/me':
            session = get_session(get_token_from_request(self))
            if session:
                return self._json({'username': session['username'], 'role': session['role']})
            return self._json({'error': 'Not authenticated'}, 401)

        if path == '/api/questions':
            session = self._auth()
            if not session: return
            return self._json({'questions': self.db.get_all_questions()})

        if path == '/api/users':
            session = self._auth(require_admin=True)
            if not session: return
            return self._json({'users': self.db.get_all_users()})

        self._json({'error': 'Not found'}, 404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == '/api/login':
            body = self._read_body()
            user = self.db.get_user_by_credentials(body.get('username',''), body.get('password',''))
            if not user:
                return self._json({'error': 'Invalid username or password'}, 401)
            token = generate_token()
            SESSIONS[token] = {
                'user_id': user['id'], 'username': user['username'],
                'role': user['role'], 'expires': datetime.now() + timedelta(hours=SESSION_HOURS)
            }
            return self._json({'token': token, 'username': user['username'], 'role': user['role']})

        if path == '/api/logout':
            SESSIONS.pop(get_token_from_request(self), None)
            return self._json({'message': 'Logged out'})

        if path == '/api/questions':
            session = self._auth(require_admin=True)
            if not session: return
            qid = self.db.add_question(self._read_body())
            return self._json({'id': qid, 'message': 'Question added'}, 201)

        if path == '/api/users':
            session = self._auth(require_admin=True)
            if not session: return
            body = self._read_body()
            username = body.get('username','').strip()
            password = body.get('password','').strip()
            role     = body.get('role','user')
            if not username or not password:
                return self._json({'error': 'Username and password required'}, 400)
            if role not in ('admin','user'):
                return self._json({'error': 'Role must be admin or user'}, 400)
            try:
                self.db.add_user(username, password, role)
                return self._json({'message': 'User created'}, 201)
            except sqlite3.IntegrityError:
                return self._json({'error': 'Username already exists'}, 409)

        self._json({'error': 'Not found'}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path

        if path.startswith('/api/questions/'):
            session = self._auth(require_admin=True)
            if not session: return
            qid = int(path.split('/')[-1])
            self.db.update_question(qid, self._read_body())
            return self._json({'message': 'Question updated'})

        if path.startswith('/api/users/'):
            session = self._auth(require_admin=True)
            if not session: return
            uid = int(path.split('/')[-1])
            body = self._read_body()
            new_pw = body.get('password','').strip()
            if not new_pw:
                return self._json({'error': 'New password required'}, 400)
            self.db.update_user_password(uid, new_pw)
            return self._json({'message': 'Password updated'})

        self._json({'error': 'Not found'}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path

        if path.startswith('/api/questions/'):
            session = self._auth(require_admin=True)
            if not session: return
            qid = int(path.split('/')[-1])
            self.db.delete_question(qid)
            return self._json({'message': 'Question deleted'})

        if path.startswith('/api/users/'):
            session = self._auth(require_admin=True)
            if not session: return
            uid = int(path.split('/')[-1])
            self.db.delete_user(uid)
            return self._json({'message': 'User deleted'})

        self._json({'error': 'Not found'}, 404)


def run_server(port=None):
    port = port or int(os.environ.get('PORT', 8000))
    httpd = HTTPServer(('', port), RequestHandler)
    print(f'\nExamPrep  →  http://localhost:{port}')
    print(f'Database  →  {DB_PATH}\n')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
        httpd.shutdown()


if __name__ == '__main__':
    run_server()
