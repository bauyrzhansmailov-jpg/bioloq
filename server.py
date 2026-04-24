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
                CREATE TABLE IF NOT EXISTS exam_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    taken_at TEXT NOT NULL,
                    total_questions INTEGER NOT NULL,
                    answered_questions INTEGER NOT NULL,
                    earned_points REAL NOT NULL,
                    total_points REAL NOT NULL,
                    percentage REAL NOT NULL,
                    filters_json TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS exam_attempt_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attempt_id INTEGER NOT NULL,
                    question_id INTEGER NOT NULL,
                    is_correct INTEGER NOT NULL,
                    earned_points REAL NOT NULL,
                    max_points REAL NOT NULL,
                    topic_snapshot TEXT,
                    source_snapshot TEXT,
                    year_snapshot TEXT,
                    FOREIGN KEY (attempt_id) REFERENCES exam_attempts(id),
                    FOREIGN KEY (question_id) REFERENCES questions(id)
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

    def save_exam_attempt(self, user_id, payload):
        now = datetime.now().isoformat()
        with self.conn() as db:
            cur = db.execute('''
                INSERT INTO exam_attempts
                (user_id, taken_at, total_questions, answered_questions, earned_points, total_points, percentage, filters_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                now,
                payload.get('totalQuestions', 0),
                payload.get('answeredQuestions', 0),
                payload.get('earnedPoints', 0),
                payload.get('totalPoints', 0),
                payload.get('percentage', 0),
                json.dumps(payload.get('filters', {}))
            ))
            attempt_id = cur.lastrowid

            for item in payload.get('items', []):
                db.execute('''
                    INSERT INTO exam_attempt_items
                    (attempt_id, question_id, is_correct, earned_points, max_points, topic_snapshot, source_snapshot, year_snapshot)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    attempt_id,
                    item.get('questionId'),
                    1 if item.get('isCorrect') else 0,
                    item.get('earnedPoints', 0),
                    item.get('maxPoints', 0),
                    json.dumps(item.get('topics', [])),
                    item.get('examSource', ''),
                    item.get('year', '')
                ))

            db.commit()
            return attempt_id

    def get_user_results(self, user_id):
        with self.conn() as db:
            rows = db.execute('''
                SELECT id, taken_at, total_questions, answered_questions,
                    earned_points, total_points, percentage, filters_json
                FROM exam_attempts
                WHERE user_id = ?
                ORDER BY taken_at DESC
            ''', (user_id,)).fetchall()

            result = []
            for r in rows:
                d = dict(r)
                d['filters'] = json.loads(d['filters_json']) if d['filters_json'] else {}
                del d['filters_json']
                result.append(d)
            return result

    def get_user_result_stats(self, user_id):
        with self.conn() as db:
            topic_rows = db.execute('''
                SELECT topic.value AS topic,
                    COUNT(*) AS total,
                    SUM(is_correct) AS correct,
                    ROUND(100.0 * SUM(is_correct) / COUNT(*), 1) AS accuracy
                FROM exam_attempt_items,
                    json_each(exam_attempt_items.topic_snapshot) AS topic
                WHERE attempt_id IN (
                    SELECT id FROM exam_attempts WHERE user_id = ?
                )
                GROUP BY topic.value
                ORDER BY total DESC, topic.value
            ''', (user_id,)).fetchall()

            source_rows = db.execute('''
                SELECT source_snapshot AS source,
                    COUNT(*) AS total,
                    SUM(is_correct) AS correct,
                    ROUND(100.0 * SUM(is_correct) / COUNT(*), 1) AS accuracy
                FROM exam_attempt_items
                WHERE attempt_id IN (
                    SELECT id FROM exam_attempts WHERE user_id = ?
                )
                GROUP BY source_snapshot
                ORDER BY total DESC, source_snapshot
            ''', (user_id,)).fetchall()

            year_rows = db.execute('''
                SELECT year_snapshot AS year,
                    COUNT(*) AS total,
                    SUM(is_correct) AS correct,
                    ROUND(100.0 * SUM(is_correct) / COUNT(*), 1) AS accuracy
                FROM exam_attempt_items
                WHERE attempt_id IN (
                    SELECT id FROM exam_attempts WHERE user_id = ?
                )
                GROUP BY year_snapshot
                ORDER BY year_snapshot DESC
            ''', (user_id,)).fetchall()

            return {
                'byTopic': [dict(r) for r in topic_rows],
                'bySource': [dict(r) for r in source_rows],
                'byYear': [dict(r) for r in year_rows],
            }

    def get_all_results(self):
        with self.conn() as db:
            rows = db.execute('''
                SELECT exam_attempts.id,
                    users.username,
                    exam_attempts.taken_at,
                    exam_attempts.total_questions,
                    exam_attempts.answered_questions,
                    exam_attempts.earned_points,
                    exam_attempts.total_points,
                    exam_attempts.percentage,
                    exam_attempts.filters_json
                FROM exam_attempts
                JOIN users ON users.id = exam_attempts.user_id
                ORDER BY exam_attempts.taken_at DESC
            ''').fetchall()

            result = []
            for r in rows:
                d = dict(r)
                d['filters'] = json.loads(d['filters_json']) if d['filters_json'] else {}
                del d['filters_json']
                result.append(d)
            return result

    def get_all_result_stats(self):
        with self.conn() as db:
            topic_rows = db.execute('''
                SELECT topic.value AS topic,
                    COUNT(*) AS total,
                    SUM(is_correct) AS correct,
                    ROUND(100.0 * SUM(is_correct) / COUNT(*), 1) AS accuracy
                FROM exam_attempt_items,
                    json_each(exam_attempt_items.topic_snapshot) AS topic
                GROUP BY topic.value
                ORDER BY total DESC, topic.value
            ''').fetchall()

            source_rows = db.execute('''
                SELECT source_snapshot AS source,
                    COUNT(*) AS total,
                    SUM(is_correct) AS correct,
                    ROUND(100.0 * SUM(is_correct) / COUNT(*), 1) AS accuracy
                FROM exam_attempt_items
                GROUP BY source_snapshot
                ORDER BY total DESC, source_snapshot
            ''').fetchall()

            year_rows = db.execute('''
                SELECT year_snapshot AS year,
                    COUNT(*) AS total,
                    SUM(is_correct) AS correct,
                    ROUND(100.0 * SUM(is_correct) / COUNT(*), 1) AS accuracy
                FROM exam_attempt_items
                GROUP BY year_snapshot
                ORDER BY year_snapshot DESC
            ''').fetchall()

            return {
                'byTopic': [dict(r) for r in topic_rows],
                'bySource': [dict(r) for r in source_rows],
                'byYear': [dict(r) for r in year_rows],
            }

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

        if path == '/api/my-results':
            session = self._auth()
            if not session: return
            return self._json({'results': self.db.get_user_results(session['user_id'])})

        if path == '/api/my-results/stats':
            session = self._auth()
            if not session: return
            return self._json(self.db.get_user_result_stats(session['user_id']))

        if path == '/api/results':
            session = self._auth(require_admin=True)
            if not session: return
            return self._json({'results': self.db.get_all_results()})

        if path == '/api/results/stats':
            session = self._auth(require_admin=True)
            if not session: return
            return self._json(self.db.get_all_result_stats())

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

        if path == '/api/exam-attempts':
            session = self._auth()
            if not session: return
            attempt_id = self.db.save_exam_attempt(session['user_id'], self._read_body())
            return self._json({'id': attempt_id, 'message': 'Exam attempt saved'}, 201)

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
