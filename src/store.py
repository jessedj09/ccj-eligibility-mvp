# -*- coding: utf-8 -*-
"""store.py — 공유 저장소(Neon PostgreSQL, v3 ④ — 설계·개발 문서 §5). **판정은 이것 없이도 동작한다.**

    s = get_store()                      # DATABASE_URL이 없거나 접속이 안 되면 NullStore(아무것도 저장하지 않음)
    s.latest_analysis(sha, version)      # 같은 원문·같은 엔진으로 분석한 결과(초안 스냅샷) — 없으면 None
    s.save_analysis(sha, version, snapshot, grade)
    s.enqueue(sha, "enhance")  /  job = s.claim("enhance")  /  s.finish(job.id, ok)
    s.put_pdf(sha, data)  /  s.get_pdf(sha)  /  s.delete_pdf(sha)

- DB는 원본이 아니다(원본 = git의 검증된 규칙 + 공고 원문). 공유 캐시·작업 대기열·분석 중 PDF만 둔다.
- 사용자 조건·판정 결과·IP는 저장하지 않는다(usage_daily는 날짜별 건수만).
- 화면(Streamlit·Next.js)과 무관 — 설정은 환경변수 `DATABASE_URL`, 없으면 로컬 개발용 `.streamlit/secrets.toml`(git 제외).
- 표준 PostgreSQL만 쓴다(Neon 전용 기능 없음) — 다른 호스팅·AWS로 옮겨도 그대로.
- 질의가 실패하면 경고를 남기고 기본값을 돌려준다. 접속 실패 뒤 RETRY_AFTER초 동안은 다시 시도하지 않는다(판정을 늦추지 않게).
"""
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger("ccj.store")

ENV = "DATABASE_URL"
SECRETS = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
CONNECT_TIMEOUT = 8          # Neon은 5분 쉬면 잠들고 첫 접속에 1초 안팎으로 깬다
RETRY_AFTER = 60             # 접속 실패 뒤 이 시간 동안은 DB 없이 동작
MAX_PDF = 20 * 1024 * 1024   # 파일당 상한
MAX_PDF_TOTAL = 300 * 1024 * 1024   # 보관 중인 PDF 합계 상한(무료 1GB의 일부)
PDF_TTL_DAYS = 14            # 분석이 끝나지 않아도 이 기간이 지나면 지운다
MAX_ATTEMPTS = 3             # 작업 재시도 상한 — 넘으면 failed(운영자 검토로)
KINDS = ("enhance", "review", "register")
USAGE = ("uploads", "judged", "unjudged")

SCHEMA = """
CREATE TABLE IF NOT EXISTS notices (
    sha256 text PRIMARY KEY,
    issuer text, program text, title text, announcement_date date,
    window_start timestamptz, window_end timestamptz, source_url text,
    origin text NOT NULL DEFAULT 'upload',           -- upload / collect / registered
    registered_id text,                              -- 등록 공고 N번호
    first_seen timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS analyses (
    id bigserial PRIMARY KEY,
    sha256 text NOT NULL REFERENCES notices(sha256) ON DELETE CASCADE,
    engine_version text NOT NULL,
    status text NOT NULL,                            -- 초안 상태: ok / unsupported / blocked / unreadable
    grade text,                                      -- auto / partial (status = ok일 때)
    snapshot jsonb NOT NULL,                         -- 초안 스냅샷(draft.to_snapshot) — 규칙·보류·장부 포함
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL DEFAULT 'engine'        -- engine / worker / operator
);
CREATE INDEX IF NOT EXISTS analyses_lookup ON analyses (sha256, engine_version, id DESC);
CREATE TABLE IF NOT EXISTS jobs (
    id bigserial PRIMARY KEY,
    sha256 text NOT NULL REFERENCES notices(sha256) ON DELETE CASCADE,
    kind text NOT NULL,                              -- enhance / review / register
    status text NOT NULL DEFAULT 'pending',          -- pending / running / done / failed
    priority int NOT NULL DEFAULT 0,
    attempts int NOT NULL DEFAULT 0,
    error text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS jobs_one_open ON jobs (sha256, kind) WHERE status IN ('pending', 'running');
CREATE TABLE IF NOT EXISTS pdf_blobs (
    sha256 text PRIMARY KEY,
    bytes bytea NOT NULL,
    size int NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS program_health (
    program text PRIMARY KEY,
    compared int NOT NULL DEFAULT 0, same int NOT NULL DEFAULT 0,
    cautious int NOT NULL DEFAULT 0, danger int NOT NULL DEFAULT 0,
    demoted_at timestamptz
);
CREATE TABLE IF NOT EXISTS usage_daily (
    day date PRIMARY KEY,
    uploads int NOT NULL DEFAULT 0, judged int NOT NULL DEFAULT 0, unjudged int NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True)
class Job:
    id: int
    sha256: str
    kind: str
    attempts: int


def database_url() -> Optional[str]:
    url = os.environ.get(ENV, "").strip()
    if url:
        return url
    if SECRETS.exists():
        import tomllib
        try:
            return (tomllib.loads(SECRETS.read_text(encoding="utf-8")).get(ENV) or "").strip() or None
        except (OSError, ValueError) as e:
            log.warning("secrets.toml을 읽지 못했습니다: %s", e)
    return None


class NullStore:
    """DB가 없을 때 — 아무것도 저장하지 않고, 찾으면 늘 없음."""
    available = False

    def migrate(self): return False
    def save_notice(self, sha, **meta): return False
    def save_analysis(self, sha, version, snapshot, grade=None, by="engine"): return None
    def latest_analysis(self, sha, version): return None
    def enqueue(self, sha, kind, priority=0): return False
    def claim(self, kind): return None
    def finish(self, job_id, ok, error=""): return False
    def put_pdf(self, sha, data): return False
    def get_pdf(self, sha): return None
    def delete_pdf(self, sha): return False
    def purge_expired(self): return 0
    def count(self, what, n=1): return False


def _safe(default):
    """질의 실패는 판정을 막지 않는다 — 경고만 남기고 기본값."""
    def wrap(f):
        def g(self, *a, **k):
            try:
                return f(self, *a, **k)
            except Exception as e:   # noqa: BLE001 — DB 문제(접속·질의·형식)는 모두 'DB 없음'과 같게 다룬다
                log.warning("저장소 %s 실패: %s", f.__name__, e)
                self._drop(e)
                return default
        g.__name__ = f.__name__
        return g
    return wrap


class Store(NullStore):
    """PostgreSQL 저장소. 연결 하나를 잠금으로 나눠 쓴다(베타 규모). schema: 테스트가 따로 쓰는 스키마."""

    def __init__(self, url: str, schema: str = "public"):
        self.url, self.schema = url, schema
        self._conn = None
        self._lock = threading.RLock()
        self._down_until = 0.0

    @property
    def available(self) -> bool:
        return time.monotonic() >= self._down_until

    def _connect(self):
        import psycopg
        conn = psycopg.connect(self.url, connect_timeout=CONNECT_TIMEOUT, autocommit=True)
        if self.schema != "public":
            conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
        conn.execute(f'SET search_path TO "{self.schema}"')
        return conn

    def _drop(self, err):
        import psycopg
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:   # noqa: BLE001
                    pass
            self._conn = None
            if isinstance(err, psycopg.OperationalError):
                self._down_until = time.monotonic() + RETRY_AFTER

    def _run(self, fn):
        """연결을 잡고 fn(conn) — 끊긴 연결(Neon 절전 등)이면 한 번 다시 붙는다. 장애 중이면 바로 실패."""
        import psycopg
        if not self.available:
            raise psycopg.OperationalError("저장소 잠시 사용 안 함(최근 접속 실패)")
        with self._lock:
            for attempt in (1, 2):
                if self._conn is None or self._conn.closed:
                    self._conn = self._connect()
                try:
                    return fn(self._conn)
                except psycopg.OperationalError:
                    self._conn.close()
                    self._conn = None
                    if attempt == 2:
                        raise

    def close(self):
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @_safe(False)
    def migrate(self):
        self._run(lambda c: c.execute(SCHEMA))
        return True

    @_safe(False)
    def save_notice(self, sha, issuer=None, program=None, title=None, announcement_date=None, origin="upload",
                    registered_id=None, source_url=None, window_start=None, window_end=None):
        """처음 본 공고면 넣고, 이미 있으면 비어 있던 값만 채운다(first_seen 유지)."""
        self._run(lambda c: c.execute(
            """INSERT INTO notices (sha256, issuer, program, title, announcement_date, origin, registered_id, source_url,
                                    window_start, window_end)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (sha256) DO UPDATE SET
                 issuer = COALESCE(notices.issuer, EXCLUDED.issuer), program = COALESCE(notices.program, EXCLUDED.program),
                 title = COALESCE(notices.title, EXCLUDED.title),
                 announcement_date = COALESCE(notices.announcement_date, EXCLUDED.announcement_date),
                 registered_id = COALESCE(EXCLUDED.registered_id, notices.registered_id),
                 source_url = COALESCE(notices.source_url, EXCLUDED.source_url),
                 window_start = COALESCE(notices.window_start, EXCLUDED.window_start),
                 window_end = COALESCE(notices.window_end, EXCLUDED.window_end)""",
            (sha, issuer, program, title, announcement_date, origin, registered_id, source_url, window_start, window_end)))
        return True

    @_safe(None)
    def save_analysis(self, sha, version, snapshot: Dict, grade=None, by="engine") -> Optional[int]:
        row = self._run(lambda c: c.execute(
            "INSERT INTO analyses (sha256, engine_version, status, grade, snapshot, created_by) "
            "VALUES (%s, %s, %s, %s, %s::jsonb, %s) RETURNING id",
            (sha, version, snapshot["status"], grade, json.dumps(snapshot, ensure_ascii=False), by)).fetchone())
        return row[0]

    @_safe(None)
    def latest_analysis(self, sha, version) -> Optional[Dict]:
        row = self._run(lambda c: c.execute(
            "SELECT snapshot FROM analyses WHERE sha256 = %s AND engine_version = %s ORDER BY id DESC LIMIT 1",
            (sha, version)).fetchone())
        return row[0] if row else None

    @_safe(False)
    def enqueue(self, sha, kind, priority=0) -> bool:
        """같은 공고·같은 종류의 작업이 대기·진행 중이면 넣지 않는다(False)."""
        assert kind in KINDS, kind
        row = self._run(lambda c: c.execute(
            "INSERT INTO jobs (sha256, kind, priority) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING id",
            (sha, kind, priority)).fetchone())
        return row is not None

    @_safe(None)
    def claim(self, kind) -> Optional[Job]:
        """대기 작업 하나를 가져간다 — 여러 작업기가 동시에 가져가도 겹치지 않게(FOR UPDATE SKIP LOCKED)."""
        row = self._run(lambda c: c.execute(
            """UPDATE jobs SET status = 'running', attempts = attempts + 1, updated_at = now()
               WHERE id = (SELECT id FROM jobs WHERE status = 'pending' AND kind = %s
                           ORDER BY priority DESC, id FOR UPDATE SKIP LOCKED LIMIT 1)
               RETURNING id, sha256, kind, attempts""", (kind,)).fetchone())
        return Job(*row) if row else None

    @_safe(False)
    def finish(self, job_id, ok, error="") -> bool:
        """성공 → done. 실패 → 시도 횟수가 남았으면 다시 pending, 아니면 failed(운영자 검토)."""
        self._run(lambda c: c.execute(
            """UPDATE jobs SET updated_at = now(), error = %s,
                 status = CASE WHEN %s THEN 'done' WHEN attempts < %s THEN 'pending' ELSE 'failed' END
               WHERE id = %s""", (error or None, ok, MAX_ATTEMPTS, job_id)))
        return True

    @_safe(False)
    def put_pdf(self, sha, data: bytes) -> bool:
        """분석 중인 공고 PDF를 잠시 둔다. 파일·합계 상한을 넘으면 넣지 않는다(False)."""
        if len(data) > MAX_PDF:
            return False

        def go(c):
            with c.transaction():
                c.execute("LOCK TABLE pdf_blobs IN SHARE ROW EXCLUSIVE MODE")
                used = c.execute("SELECT COALESCE(SUM(size), 0) FROM pdf_blobs WHERE sha256 <> %s", (sha,)).fetchone()[0]
                if used + len(data) > MAX_PDF_TOTAL:
                    return False
                c.execute("""INSERT INTO pdf_blobs (sha256, bytes, size, expires_at)
                             VALUES (%s, %s, %s, now() + make_interval(days => %s))
                             ON CONFLICT (sha256) DO UPDATE SET expires_at = EXCLUDED.expires_at""",
                          (sha, data, len(data), PDF_TTL_DAYS))
                return True
        return self._run(go)

    @_safe(None)
    def get_pdf(self, sha) -> Optional[bytes]:
        row = self._run(lambda c: c.execute("SELECT bytes FROM pdf_blobs WHERE sha256 = %s", (sha,)).fetchone())
        return bytes(row[0]) if row else None

    @_safe(False)
    def delete_pdf(self, sha) -> bool:
        return self._run(lambda c: c.execute("DELETE FROM pdf_blobs WHERE sha256 = %s", (sha,)).rowcount) > 0

    @_safe(0)
    def purge_expired(self) -> int:
        return self._run(lambda c: c.execute("DELETE FROM pdf_blobs WHERE expires_at < now()").rowcount)

    @_safe(False)
    def count(self, what, n=1) -> bool:
        """오늘(한국 날짜) 건수 더하기 — 개인정보 없는 집계."""
        assert what in USAGE, what
        self._run(lambda c: c.execute(
            f"""INSERT INTO usage_daily (day, {what}) VALUES ((now() AT TIME ZONE 'Asia/Seoul')::date, %s)
                ON CONFLICT (day) DO UPDATE SET {what} = usage_daily.{what} + EXCLUDED.{what}""", (n,)))
        return True


_store = None
_store_lock = threading.Lock()


def get_store():
    """프로세스에 하나. 처음 부를 때 테이블을 만든다(이미 있으면 그대로). psycopg가 없거나 주소가 없으면 NullStore."""
    global _store
    with _store_lock:
        if _store is None:
            url = database_url()
            try:
                import psycopg  # noqa: F401
            except ImportError:
                url = None
            _store = Store(url) if url else NullStore()
            if url:
                _store.migrate()
        return _store


def reset_store(store=None):
    """테스트용 — 다음 get_store()가 새로 만들거나 주어진 저장소를 쓰게."""
    global _store
    with _store_lock:
        _store = store
