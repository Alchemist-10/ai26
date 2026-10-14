"""Single-host durable storage. SQL schema is versioned with PRAGMA user_version."""
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Repository:
    def __init__(self, path):
        if str(path) != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > 10:
            self.db.close()
            raise RuntimeError('Database version is newer than this application')
        with self.db:
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, camera TEXT, started REAL, data TEXT);
                CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, camera TEXT, ts REAL, plate TEXT, kind TEXT, passage TEXT, data TEXT);
                CREATE INDEX IF NOT EXISTS obs_time ON observations(ts);
                CREATE INDEX IF NOT EXISTS obs_plate_time ON observations(plate, ts);
                CREATE TABLE IF NOT EXISTS passages(id TEXT PRIMARY KEY, camera TEXT, first REAL, last REAL, kind TEXT, plate TEXT, reads INTEGER, data TEXT);
                CREATE INDEX IF NOT EXISTS passage_time ON passages(last);
                CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY, ts REAL, data TEXT, state TEXT DEFAULT 'open', review TEXT);
                CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, expires REAL, data TEXT);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, data TEXT);
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts REAL, action TEXT, subject TEXT, data TEXT,
                                                 previous_hash TEXT, record_hash TEXT);
            ''')
            if version < 2:
                self.db.executescript('''
                    CREATE TABLE IF NOT EXISTS artifact_leases(report TEXT, digest TEXT, expires REAL, PRIMARY KEY(report,digest));
                    CREATE INDEX IF NOT EXISTS artifact_lease_expiry ON artifact_leases(expires);
                    CREATE INDEX IF NOT EXISTS artifact_lease_digest ON artifact_leases(digest,expires);
                    INSERT OR IGNORE INTO artifact_leases
                        SELECT reports.id,json_extract(a.value,'$.sha256'),reports.expires
                        FROM reports,json_each(reports.data,'$.artifacts') a;
                    PRAGMA user_version=2;
                ''')
            if version < 3:
                self.db.executescript('''
                    BEGIN IMMEDIATE;
                    CREATE TABLE camera_catalog(camera TEXT, revision INTEGER, data TEXT, PRIMARY KEY(camera,revision));
                    CREATE TABLE journey_links(id TEXT PRIMARY KEY, plate TEXT, from_ts REAL, to_ts REAL, data TEXT);
                    CREATE INDEX journey_link_time ON journey_links(to_ts);
                    CREATE INDEX journey_link_plate_time ON journey_links(plate,to_ts);
                    PRAGMA user_version=3;
                    COMMIT;
                ''')
            if version < 4:
                columns={row['name'] for row in self.db.execute('PRAGMA table_info(audit)').fetchall()}
                if 'previous_hash' not in columns: self.db.execute('ALTER TABLE audit ADD COLUMN previous_hash TEXT')
                if 'record_hash' not in columns: self.db.execute('ALTER TABLE audit ADD COLUMN record_hash TEXT')
                previous=None
                rows=self.db.execute('SELECT id,ts,action,subject,data FROM audit ORDER BY id').fetchall()
                for row in rows:
                    record={'id':row['id'],'ts':row['ts'],'action':row['action'],'subject':row['subject'],
                            'data':row['data'],'previous_hash':previous}
                    digest=hashlib.sha256(canonical_json(record).encode()).hexdigest()
                    self.db.execute('UPDATE audit SET previous_hash=?,record_hash=? WHERE id=?',
                                    (previous,digest,row['id']))
                    previous=digest
                self.db.execute('PRAGMA user_version=4')
            if version < 5:
                self.db.executescript('''
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS users(
                        username TEXT PRIMARY KEY COLLATE NOCASE,
                        password_salt BLOB NOT NULL,
                        password_hash BLOB NOT NULL,
                        iterations INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        disabled INTEGER NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS auth_sessions(
                        token_hash TEXT PRIMARY KEY,
                        username TEXT NOT NULL,
                        csrf_token TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS auth_session_expiry ON auth_sessions(expires_at);
                    CREATE TABLE IF NOT EXISTS auth_login_failures(
                        id INTEGER PRIMARY KEY,
                        client_hash TEXT NOT NULL,
                        failed_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS auth_failure_window ON auth_login_failures(client_hash,failed_at);
                    PRAGMA user_version=5;
                    COMMIT;
                ''')
            if version < 6:
                self.db.executescript('''
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS user_case_access(
                        username TEXT NOT NULL,
                        case_id TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        PRIMARY KEY(username,case_id)
                    );
                    CREATE INDEX IF NOT EXISTS case_access_lookup ON user_case_access(case_id,username);
                    PRAGMA user_version=6;
                    COMMIT;
                ''')
            if version < 8:
                self.db.executescript('''
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS user_mfa(
                        username TEXT PRIMARY KEY,
                        secret_ciphertext BLOB NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 0,
                        recovery_hashes TEXT NOT NULL DEFAULT '[]',
                        updated_at REAL NOT NULL,
                        expires_at REAL NOT NULL
                    );
                    PRAGMA user_version=8;
                    COMMIT;
                ''')
            if version < 10:
                self.db.executescript('''
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS camera_pair_constraints(
                        from_camera TEXT NOT NULL,
                        to_camera TEXT NOT NULL,
                        from_revision INTEGER NOT NULL,
                        to_revision INTEGER NOT NULL,
                        min_travel_seconds REAL NOT NULL,
                        max_travel_seconds REAL NOT NULL,
                        enabled INTEGER NOT NULL,
                        reviewer TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY(from_camera,to_camera)
                    );
                    PRAGMA user_version=10;
                    COMMIT;
                ''')
        with self.db:
            self.db.execute('CREATE INDEX IF NOT EXISTS audit_subject_action_time ON audit(subject,action,ts)')
        self.schema_version = 10
        # Seed only missing IDs. Restart never overwrites operator metadata or its history.
        from cameras import CAMERAS
        with self.lock, self.db:
            for camera in CAMERAS:
                config = {k:v for k,v in camera.items() if k != 'path'}
                config.update(revision=1, metadata_source='repository defaults',
                              calibration_status='unverified', updated_at=0)
                self.db.execute('INSERT OR IGNORE INTO camera_catalog VALUES(?,?,?)',
                                (camera['id'], 1, canonical_json(config)))

    def camera_catalog(self):
        with self.lock:
            rows = self.db.execute('''SELECT data FROM camera_catalog c WHERE revision=(
                SELECT max(revision) FROM camera_catalog WHERE camera=c.camera) ORDER BY camera''').fetchall()
        return [json.loads(r[0]) for r in rows]

    def camera_configuration(self, camera, revision=None):
        with self.lock:
            row = self.db.execute('SELECT data FROM camera_catalog WHERE camera=? AND (? IS NULL OR revision=?) ORDER BY revision DESC LIMIT 1',
                                  (camera,revision,revision)).fetchone()
        return json.loads(row[0]) if row else None

    def update_camera(self, camera, change, now):
        # SQL transaction plus compare-and-swap protects against concurrent editors/connections.
        with self.lock, self.db:
            self.db.execute('BEGIN IMMEDIATE')
            previous = self.camera_configuration(camera)
            if previous is None: raise ValueError('Unknown camera')
            if previous['revision'] != change['expected_revision']:
                raise ValueError('Camera configuration changed; reload before saving')
            config = {**previous, **{k:change[k] for k in ('location','lat','lon','location_confirmed')},
                      'revision':previous['revision']+1, 'updated_at':now,
                      'metadata_source':'local operator entry; calibration unverified'}
            self.db.execute('INSERT INTO camera_catalog VALUES(?,?,?)', (camera,config['revision'],canonical_json(config)))
            self._append_audit(now,'camera_configuration',camera,{'revision':config['revision'],
                               'reviewer':change['reviewer'],'reason':change['reason']})
        return config

    def camera_pair_constraints(self):
        with self.lock:
            rows=self.db.execute('SELECT * FROM camera_pair_constraints ORDER BY from_camera,to_camera').fetchall()
            catalog_rows=self.db.execute('''SELECT data FROM camera_catalog c WHERE revision=(
                SELECT max(revision) FROM camera_catalog WHERE camera=c.camera)''').fetchall()
        catalog={item['id']:item for item in (json.loads(row['data']) for row in catalog_rows)}
        result=[]
        for row in rows:
            item={**dict(row),'enabled':bool(row['enabled'])}
            item['current_locations_valid']=all(
                item[f'{direction}_camera'] in catalog and
                catalog[item[f'{direction}_camera']]['location_confirmed'] and
                catalog[item[f'{direction}_camera']]['revision']==item[f'{direction}_revision']
                for direction in ('from','to'))
            result.append(item)
        return result

    def camera_pair_constraint(self, from_camera, to_camera):
        with self.lock:
            row=self.db.execute('SELECT * FROM camera_pair_constraints WHERE from_camera=? AND to_camera=?',
                                (from_camera,to_camera)).fetchone()
        return {**dict(row),'enabled':bool(row['enabled'])} if row else None

    def put_camera_pair_constraint(self, change, now):
        from_camera,to_camera=change['from_camera_id'],change['to_camera_id']
        with self.lock, self.db:
            self.db.execute('BEGIN IMMEDIATE')
            catalog_rows=self.db.execute('''SELECT data FROM camera_catalog c WHERE revision=(
                SELECT max(revision) FROM camera_catalog WHERE camera=c.camera)''').fetchall()
            locations={item['id']:item for item in (json.loads(row['data']) for row in catalog_rows)}
            if from_camera not in locations or to_camera not in locations:
                raise ValueError('Unknown camera in pair constraint')
            if from_camera==to_camera:
                raise ValueError('A camera pair must connect two different cameras')
            if not locations[from_camera]['location_confirmed'] or not locations[to_camera]['location_confirmed']:
                raise ValueError('Mark both camera locations as confirmed before setting pair constraints')
            previous_row=self.db.execute('SELECT * FROM camera_pair_constraints WHERE from_camera=? AND to_camera=?',
                                         (from_camera,to_camera)).fetchone()
            previous={**dict(previous_row),'enabled':bool(previous_row['enabled'])} if previous_row else None
            constraint={
                'from_camera':from_camera,'to_camera':to_camera,
                'from_revision':locations[from_camera]['revision'],'to_revision':locations[to_camera]['revision'],
                'min_travel_seconds':change['min_travel_seconds'],
                'max_travel_seconds':change['max_travel_seconds'],
                'enabled':change['enabled'],'reviewer':change['reviewer'],
                'reason':change['reason'],'updated_at':now,
            }
            self.db.execute('''INSERT INTO camera_pair_constraints VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(from_camera,to_camera) DO UPDATE SET
                from_revision=excluded.from_revision,to_revision=excluded.to_revision,
                min_travel_seconds=excluded.min_travel_seconds,
                max_travel_seconds=excluded.max_travel_seconds,enabled=excluded.enabled,
                reviewer=excluded.reviewer,reason=excluded.reason,updated_at=excluded.updated_at''',
                (from_camera,to_camera,locations[from_camera]['revision'],locations[to_camera]['revision'],
                 change['min_travel_seconds'],change['max_travel_seconds'],
                 int(change['enabled']),change['reviewer'],change['reason'],now))
            self._append_audit(now,'camera_pair_constraint',f'{from_camera}>{to_camera}',
                               {'previous':previous,'current':constraint})
        return {**constraint,'enabled':bool(constraint['enabled']),'current_locations_valid':True}

    def put_journey_links(self, plate, trajectory):
        """Materialize immutable decisions idempotently; polling the same route adds no rows."""
        result = {}
        with self.lock, self.db:
            for key, status in [('accepted_links','accepted'),('rejected_links','rejected'),('candidate_links','candidate')]:
                result[key] = []
                for link in trajectory[key]:
                    decision = {**link, 'plate':plate, 'decision_status':status}
                    link_id = hashlib.sha256(canonical_json(decision).encode()).hexdigest()[:32]
                    decision['link_id'] = link_id
                    self.db.execute('INSERT OR IGNORE INTO journey_links VALUES(?,?,?,?,?)',
                                    (link_id,plate,link['from_ts'],link['to_ts'],canonical_json(decision)))
                    result[key].append(decision)
        return {**trajectory, **result}

    def journey_links(self, plate=None, since=0, until=None, limit=5000):
        clauses = ['to_ts>=?', 'to_ts<=?']; args = [since,time.time() if until is None else until]
        if plate is not None: clauses.append('plate=?'); args.append(plate)
        with self.lock:
            rows = self.db.execute('SELECT data FROM journey_links WHERE '+' AND '.join(clauses)+
                                   ' ORDER BY to_ts DESC,id DESC LIMIT ?', [*args,limit]).fetchall()
        return [json.loads(r[0]) for r in rows]

    def start_session(self, session):
        with self.lock, self.db:
            self.db.execute('INSERT OR IGNORE INTO sessions VALUES(?,?,?,?)',
                            (session['id'], session['camera_id'], session['started_at'], canonical_json(session)))

    def ingest(self, events):
        inserted = 0
        with self.lock, self.db:
            for event in events:
                # A retry of the same source frame/track is the same observation.
                identity = [event['camera_id'], event.get('session_id', 'manual'),
                            event.get('frame_id', event['ts']), event['kind'], event.get('track_id'),
                            event.get('plate_norm') if event.get('track_id') is None else None]
                event = dict(event)
                event['event_id'] = event.get('event_id') or hashlib.sha256(canonical_json(identity).encode()).hexdigest()[:32]
                passage_key = [event['camera_id'], event.get('session_id', 'manual'), event['kind'],
                               event.get('track_id', event['event_id'])]
                event['passage_id'] = hashlib.sha256(canonical_json(passage_key).encode()).hexdigest()[:32]
                # Uncertain OCR remains in raw history, never silently enters plate identity queries.
                plate = event.get('plate_norm') if event.get('identity_status', 'supported') == 'supported' else None
                cursor = self.db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?)',
                                        (event['event_id'], event['camera_id'], event['ts'], plate,
                                         event['kind'], event['passage_id'], canonical_json(event)))
                if not cursor.rowcount:
                    continue
                inserted += 1
                previous = self.db.execute('SELECT * FROM passages WHERE id=?', (event['passage_id'],)).fetchone()
                first = min(previous['first'], event['ts']) if previous else event['ts']
                last = max(previous['last'], event['ts']) if previous else event['ts']
                summary = dict(json.loads(previous['data'])) if previous else dict(event)
                summary['first_seen'] = first
                summary['last_seen'] = last
                summary['read_count'] = (previous['reads'] if previous else 0) + 1
                if previous and (event.get('confidence', 0) >= summary.get('confidence', 0)):
                    summary.update(event)
                # Conflicting identity on a local track must invalidate its prior identity summary.
                if event['kind'] == 'plate':
                    old_plate = previous['plate'] if previous else None
                    conflict = summary.get('identity_conflict', False) or (old_plate and event.get('plate_norm') and event.get('identity_status') not in ('invalid','low_confidence') and event.get('plate_norm') != old_plate) or event.get('identity_status') == 'conflicting'
                    if conflict:
                        summary['identity_conflict'] = True
                        summary['identity_status'] = 'conflicting'
                        plate = None
                    elif plate:
                        summary['plate_norm'] = summary['plate'] = plate
                        summary['identity_status'] = 'supported'
                    else:
                        plate = old_plate
                # Keep latest observed position separate from the best-confidence read.
                summary['last_bbox'] = event['bbox']
                summary['first_bbox'] = summary.get('first_bbox', event['bbox'])
                summary['ts'] = first
                self.db.execute('INSERT OR REPLACE INTO passages VALUES(?,?,?,?,?,?,?,?)',
                                (event['passage_id'], event['camera_id'], first, last, event['kind'], plate,
                                 summary['read_count'], canonical_json(summary)))
        return inserted

    def observations(self, camera=None, plate=None, since=None, until=None, kind=None, limit=5000):
        clauses, args = [], []
        for col, value in [('camera', camera), ('plate', plate), ('kind', kind)]:
            if value is not None:
                clauses.append(f'{col}=?'); args.append(value)
        for op, value in [('>=', since), ('<=', until)]:
            if value is not None:
                clauses.append(f'ts{op}?'); args.append(value)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.lock:
            rows = self.db.execute('SELECT data FROM observations' + where + ' ORDER BY ts DESC, id DESC LIMIT ?', [*args, limit]).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]

    def passages(self, since=None, until=None, plate=None):
        clauses, args = [], []
        if since is not None: clauses.append('last>=?'); args.append(since)
        if until is not None: clauses.append('first<=?'); args.append(until)
        if plate is not None: clauses.append('plate=?'); args.append(plate)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.lock:
            rows = self.db.execute('SELECT data FROM passages' + where + ' ORDER BY first, id', args).fetchall()
        return [json.loads(row[0]) for row in rows]

    def supported_passage_reads(self, plate, since, until):
        # Earliest supported read within this interval; conflicting passages are excluded.
        with self.lock:
            rows = self.db.execute("""
                SELECT data FROM (
                    SELECT o.data, ROW_NUMBER() OVER (PARTITION BY o.passage ORDER BY o.ts,o.id) AS position
                    FROM observations o JOIN passages p ON o.passage=p.id
                    WHERE p.plate=? AND o.plate=? AND o.ts>=? AND o.ts<=?
                ) WHERE position=1
            """, (plate,plate,since,until)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def statistics(self, since, until, now):
        with self.lock:
            total = self.db.execute("SELECT count(*),avg(json_extract(data,'$.confidence')) FROM observations WHERE ts>=? AND ts<=?", (since,until)).fetchone()
            per_camera = dict(self.db.execute('SELECT camera,count(*) FROM observations WHERE ts>=? AND ts<=? GROUP BY camera',(since,until)).fetchall())
            last_minute = self.db.execute('SELECT count(*) FROM observations WHERE ts>=? AND ts<=?', (max(since,now-60),min(until,now))).fetchone()[0]
            vehicles = dict(self.db.execute("SELECT camera,count(DISTINCT passage) FROM observations WHERE kind='vehicle' AND ts>=? AND ts<=? GROUP BY camera", (since,until)).fetchall())
        return {'total_events':total[0], 'avg_confidence':round(total[1] or 0,3), 'events_last_minute':last_minute,
                'per_camera':per_camera, 'per_camera_passages':vehicles, 'vehicle_passages':sum(vehicles.values()),
                'busiest_camera':max(vehicles,key=vehicles.get) if vehicles else None}

    def reads_for_passages(self, ids, since, until):
        if not ids: return [],0
        placeholders=','.join('?' for _ in ids)
        where=f'passage IN ({placeholders}) AND ts>=? AND ts<=?'
        args=[*ids,since,until]
        with self.lock:
            count=self.db.execute('SELECT count(*) FROM observations WHERE '+where,args).fetchone()[0]
            rows=self.db.execute('SELECT data FROM observations WHERE '+where+' ORDER BY ts,id LIMIT 5000',args).fetchall()
        return [json.loads(r[0]) for r in rows],count

    def query_plates(self, camera, plate, since, until):
        clauses = ['o.ts>=?', 'o.ts<=?', 'p.plate=o.plate']
        args = [since,until]
        if camera: clauses.append('o.camera=?'); args.append(camera)
        if plate: clauses.append('o.plate=?'); args.append(plate)
        with self.lock:
            rows = self.db.execute('SELECT DISTINCT o.plate,o.camera FROM observations o JOIN passages p ON p.id=o.passage WHERE ' + ' AND '.join(clauses),args).fetchall()
        return rows

    def query_vehicle_count(self, camera, label, since, until):
        clauses = ["kind='vehicle'", 'ts>=?', 'ts<=?', "json_extract(data,'$.label')=?"]
        args = [since,until,label]
        if camera: clauses.append('camera=?'); args.append(camera)
        with self.lock:
            return self.db.execute('SELECT count(DISTINCT passage) FROM observations WHERE '+' AND '.join(clauses),args).fetchone()[0]

    def setting(self, key, default):
        with self.lock:
            row = self.db.execute('SELECT data FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, canonical_json(value)))

    def update_rules(self, value, now):
        with self.lock, self.db:
            previous_row=self.db.execute('SELECT data FROM settings WHERE key=?',('rules',)).fetchone()
            previous=json.loads(previous_row['data']) if previous_row else None
            self.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('rules',canonical_json(value)))
            self._append_audit(now,'rules_updated','rules',{'previous':previous,'current':value})

    def put_alert(self, alert):
        with self.lock, self.db:
            self.db.execute('INSERT OR IGNORE INTO alerts(id,ts,data) VALUES(?,?,?)',
                            (alert['alert_id'], alert['ts'], canonical_json(alert)))

    def alerts(self, since=0):
        with self.lock:
            rows = self.db.execute('SELECT * FROM alerts WHERE ts>=? ORDER BY ts DESC LIMIT 200', (since,)).fetchall()
        return [{**json.loads(r['data']), 'state': r['state'], 'review': json.loads(r['review']) if r['review'] else None} for r in rows]

    def escalated_alerts(self, limit=200):
        with self.lock:
            rows = self.db.execute("SELECT * FROM alerts WHERE state='escalated' ORDER BY ts DESC,id DESC LIMIT ?", (limit,)).fetchall()
        return [{**json.loads(r['data']), 'state': r['state'], 'review': json.loads(r['review']) if r['review'] else None} for r in rows]

    def review_alert(self, alert_id, review):
        with self.lock, self.db:
            old = self.db.execute('SELECT review FROM alerts WHERE id=?', (alert_id,)).fetchone()
            if not old: return False
            history = json.loads(old[0]) if old[0] else []
            history.append(review)
            self.db.execute('UPDATE alerts SET state=?,review=? WHERE id=?', (review['state'], canonical_json(history), alert_id))
            self._append_audit(review['ts'],'alert_review',alert_id,review)
        return True

    def put_report(self, report):
        with self.lock, self.db:
            self.db.execute('INSERT INTO reports VALUES(?,?,?)', (report['report_id'], report['expires_at'], canonical_json(report)))
            self.db.executemany('INSERT INTO artifact_leases VALUES(?,?,?)',
                                [(report['report_id'], a['sha256'], report['expires_at']) for a in report.get('artifacts', [])])

    def protected_artifacts(self, now):
        with self.lock:
            return {r[0] for r in self.db.execute('SELECT DISTINCT digest FROM artifact_leases WHERE expires>?', (now,))}

    def artifact_expiry(self, digest, now):
        with self.lock:
            return self.db.execute('SELECT max(expires) FROM artifact_leases WHERE digest=? AND expires>?', (digest,now)).fetchone()[0]


    def report(self, report_id, now):
        with self.lock, self.db:
            row = self.db.execute('SELECT data,expires FROM reports WHERE id=?', (report_id,)).fetchone()
            if not row or row['expires'] <= now: return None
            self._append_audit(now,'report_read',report_id,{})
            return json.loads(row['data'])

    def _append_audit(self, ts, action, subject, data):
        """Append a record linked to the current tail; callers hold the SQL transaction."""
        previous_row=self.db.execute('SELECT record_hash FROM audit ORDER BY id DESC LIMIT 1').fetchone()
        previous=previous_row['record_hash'] if previous_row else None
        payload=canonical_json(data)
        cursor=self.db.execute('INSERT INTO audit(ts,action,subject,data,previous_hash,record_hash) VALUES(?,?,?,?,?,NULL)',
                               (ts,action,subject,payload,previous))
        record={'id':cursor.lastrowid,'ts':ts,'action':action,'subject':subject,'data':payload,'previous_hash':previous}
        digest=hashlib.sha256(canonical_json(record).encode()).hexdigest()
        self.db.execute('UPDATE audit SET record_hash=? WHERE id=?',(digest,cursor.lastrowid))

    def verify_audit_chain(self):
        """Verify internal record links; this is not a signature or external checkpoint."""
        with self.lock:
            rows=self.db.execute('SELECT id,ts,action,subject,data,previous_hash,record_hash FROM audit ORDER BY id').fetchall()
        previous=None
        for row in rows:
            record={'id':row['id'],'ts':row['ts'],'action':row['action'],'subject':row['subject'],
                    'data':row['data'],'previous_hash':previous}
            expected=hashlib.sha256(canonical_json(record).encode()).hexdigest()
            if row['previous_hash']!=previous or row['record_hash']!=expected:
                return {'status':'invalid','records':len(rows),'first_invalid_id':row['id'],
                        'expected_previous_hash':previous,'reported_previous_hash':row['previous_hash']}
            previous=expected
        return {'status':'valid','records':len(rows),'head_hash':previous}

    def audit_sensitive_access(self, username, case_id, purpose, method, route, now):
        with self.lock, self.db:
            # The UI polls previews and live panels. Coalesce identical reads for a
            # minute to keep the durable hash chain useful without growing once per poll.
            if method == 'GET':
                repeated = self.db.execute('''SELECT 1 FROM audit WHERE subject=? AND action='sensitive_access'
                    AND ts>? AND json_extract(data,'$.case_id')=? AND json_extract(data,'$.purpose')=?
                    AND json_extract(data,'$.method')=? AND json_extract(data,'$.route')=? LIMIT 1''',
                    (username, now-60, case_id, purpose, method, route)).fetchone()
                if repeated:
                    return False
            self._append_audit(now, 'sensitive_access', username, {
                'case_id': case_id, 'purpose': purpose, 'method': method, 'route': route,
            })
            return True

    def cleanup(self, cutoff, now):
        with self.lock, self.db:
            self.db.execute('DELETE FROM observations WHERE ts<?', (cutoff,))
            self.db.execute('DELETE FROM passages WHERE last<?', (cutoff,))
            self.db.execute('DELETE FROM journey_links WHERE to_ts<?', (cutoff,))
            self.db.execute('DELETE FROM artifact_leases WHERE expires<=?', (now,))
            self.db.execute('DELETE FROM reports WHERE expires<=?', (now,))
            self.db.execute('DELETE FROM alerts WHERE ts<?', (cutoff,))
            self.db.execute("DELETE FROM sessions WHERE started<? AND NOT EXISTS (SELECT 1 FROM observations WHERE json_extract(observations.data,'$.session_id')=sessions.id)", (cutoff,))
            self.db.execute('DELETE FROM auth_sessions WHERE expires_at<=?', (now,))
            self.db.execute('DELETE FROM auth_login_failures WHERE failed_at<=?', (now-900,))

    def close(self):
        with self.lock: self.db.close()
