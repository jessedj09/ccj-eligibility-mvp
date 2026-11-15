# -*- coding: utf-8 -*-
"""resolve_clauses.py — R-③ 공고 단위 해소 운영 도구(src/clause_resolution.py, 2026-11-15 사용자 승인).

    python tools/resolve_clauses.py queue [--limit 30]           # 아직 해소 안 된 미분류 문장 — 보류 계층 수 × 최근 공고 × 필수 먼저
    python tools/resolve_clauses.py record <sha256> <쪽> <문장 id 끝 12자 또는 문장> not|new --source operator|session --judge 이름 [--reason 사유]
    python tools/resolve_clauses.py import <후보.json> --judge 이름    # 파싱 세션 판정 후보 — '초안'으로(묶음 C 통과 전 판정에 안 씀)
    python tools/resolve_clauses.py list [--status provisional]
    python tools/resolve_clauses.py revoke --judge 이름             # 판정자 단위 되돌리기(되돌린 문장은 다시 보류)

운영 DB에 쓴다(DATABASE_URL 또는 .streamlit/secrets.toml — 표는 저장소에 처음 붙을 때 만든다(store.get_store → migrate)). 판정은 공고 원문 문장만 다룬다 — 개인정보 없음.
'필수' 문장(자격 영역 안·제한 표현)은 잠정으로 들어가고, 다른 판정자가 같은 문장을 판정하면 교차 확인(같으면 확정, '새 조건'이면 취소).
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

import analysis  # noqa: E402
import clause_resolution as CR  # noqa: E402
import draft  # noqa: E402
import store as S  # noqa: E402

RECENT_DAYS = 45          # 최근 공고(접수 중·예정일 가능성이 큼)를 먼저 — 공고일 기준 근사


def _drafts(s):
    version = analysis.analysis_version()
    for row in s.analyzed_notices(version=version):
        snap = s.latest_analysis(row["sha256"], version)
        if snap is None:
            continue
        d = draft.from_snapshot(snap)
        yield row, CR.apply(d, row["sha256"], s.resolutions_for(row["sha256"], d.template or ""))


def cmd_queue(s, a):
    for r in CR.due(s.list_resolutions(status=CR.PROVISIONAL, limit=1000)):   # 교차 확인이 밀린 잠정 기록이 맨 앞(14일 지나면 다시 보류)
        print(f"[교차 확인 필요{' · 만료' if CR.expired(r) else ''}] #{r.id} {r.judge} {(r.created_at or '')[:10]} — {r.sha256} p.{r.page}\n"
              f"    \"{r.sentence}\"")
    recent = date.today() - timedelta(days=RECENT_DAYS)
    entries = [(row["sha256"], row.get("title") or row["sha256"][:12], d,
                bool(row.get("announcement_date") and row["announcement_date"] >= recent)) for row, d in _drafts(s)]
    items = CR.queue(entries)
    for q in items[:a.limit]:
        print(f"[{q.tier}] 보류 {len(q.layers)}계층{' · 최근' if q.open_now else ''} — {q.title}\n"
              f"    {q.sha256} p.{q.page} id …{q.sentence_id[-12:]}\n    \"{q.sentence}\"")
    print(f"\n미해소 문장 {len(items)}개(공고 {len({q.sha256 for q in items})}건)")


def cmd_record(s, a):
    hit = None
    for row, d in _drafts(s):
        if row["sha256"] != a.sha256:
            continue
        for page, text in d.unclassified:
            if page == a.page and (CR.sentence_id(a.sha256, page, text).endswith(a.sentence) or text == a.sentence):
                hit = (d, page, text)
    if hit is None:
        sys.exit("그 공고의 미해소 문장에서 찾지 못했습니다(이미 해소됐거나 쪽·문장이 다름) — queue로 확인하세요")
    d, page, text = hit
    verdict = CR.NOT_CONDITION if a.verdict == "not" else CR.NEW_CONDITION
    r = CR.record(s, d, a.sha256, page, text, verdict, a.source, a.judge, a.reason)
    print(f"기록 #{r.id}: {r.verdict} · {r.tier} · {r.status} — p.{page} \"{text[:60]}\"")


def cmd_import(s, a):
    items = json.loads(Path(a.file).read_text(encoding="utf-8"))
    rows = CR.import_proposals(items if isinstance(items, list) else items["items"], judge=a.judge, source=a.source)
    n = sum(1 for r in rows if s.save_resolution(r))
    items = items if isinstance(items, list) else items["items"]
    print(f"초안 {n}/{len(rows)}건 저장(상태: {sorted({r.status for r in rows})}) — 판정 없는 후보 {len(items) - len(rows)}건은 건너뜀")


def cmd_list(s, a):
    for r in s.list_resolutions(status=a.status, limit=a.limit):
        print(f"#{r.id} {r.status:11} {r.verdict:13} {r.tier:9} {r.source}/{r.judge} {r.sha256[:12]} p.{r.page} \"{r.sentence[:50]}\"")


def cmd_revoke(s, a):
    print(f"{s.revoke_judge(a.judge)}건 취소 — {a.judge}")


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("queue")
    q.add_argument("--limit", type=int, default=30)
    r = sub.add_parser("record")
    r.add_argument("sha256")
    r.add_argument("page", type=int)
    r.add_argument("sentence")
    r.add_argument("verdict", choices=("not", "new"))
    r.add_argument("--judge", required=True)
    r.add_argument("--reason", default="")
    r.add_argument("--source", required=True, choices=CR.SOURCES,
                   help="operator = 사람(사용자), session = Claude 세션(묶음 E 통과 전에는 필수 문장에 다른 판정자의 같은 판단이 있어야 반영)")
    i = sub.add_parser("import")
    i.add_argument("file")
    i.add_argument("--judge", required=True)
    i.add_argument("--source", default="sentence_check", choices=CR.SOURCES)
    ls = sub.add_parser("list")
    ls.add_argument("--status")
    ls.add_argument("--limit", type=int, default=100)
    rv = sub.add_parser("revoke")
    rv.add_argument("--judge", required=True)
    a = p.parse_args(argv)
    s = S.get_store()
    if type(s) is S.NullStore or not s.available:
        sys.exit("공유 저장소에 연결되지 않았습니다(DATABASE_URL)")
    {"queue": cmd_queue, "record": cmd_record, "import": cmd_import, "list": cmd_list, "revoke": cmd_revoke}[a.cmd](s, a)


if __name__ == "__main__":
    main()
