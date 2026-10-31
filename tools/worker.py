# -*- coding: utf-8 -*-
"""worker.py — 운영자 PC 보강 작업기(v3 ④-3, 설계·개발 문서 §8).

    python tools/worker.py              # 계속 돈다(대기열이 비면 POLL초마다 확인) — Ctrl+C로 멈춤
    python tools/worker.py --once       # 지금 있는 작업만 처리하고 끝(작업 스케줄러용)
    python tools/worker.py --status     # 대기열·보관 PDF 현황만

공유 저장소(Neon)의 enhance 작업을 하나씩 가져와(FOR UPDATE SKIP LOCKED) 보관된 공고 PDF를 로컬 LLM(Ollama)과 함께 다시
분석한다. LLM은 결정론이 못 채운 빈칸만 채우고, 낸 값은 같은 검증(원문 대조·주제 일치)을 통과해야 쓴다(src/draft.py).
- 나아졌을 때만 새 분석으로 저장(created_by=worker) — 화면·API는 같은 엔진 판의 최신 분석을 쓴다.
- 자동 확정이 되면 PDF를 지운다. 여전히 확인할 곳이 남으면 운영자 검토(review) 작업으로 넘기고 PDF는 보관 기한까지 둔다.
- PC로 들어오는 접속은 없다(바깥으로만). Ollama가 꺼져 있으면 작업을 가져가지 않는다(시도 횟수를 쓰지 않게).
"""
import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import analysis  # noqa: E402
import draft  # noqa: E402
import grading  # noqa: E402
import llm_slot as L  # noqa: E402
from store import NullStore, get_store  # noqa: E402

POLL = 60


def ollama_ready(host: str, model: str) -> bool:
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as r:
            names = {m["name"] for m in json.load(r).get("models", [])}
    except (OSError, ValueError):
        return False
    return model in names or f"{model}:latest" in names


def score(d: draft.Draft) -> tuple:
    """클수록 좋은 초안 — 판정할 수 있는가, 자동 확정 계층 수, 확인 못 한 것이 적은가."""
    if d is None:
        return (-1,)
    autos = sum(g.grade == grading.AUTO for g in grading.grades(d).values()) if d.status == draft.OK else 0
    return (d.status == draft.OK, autos, -(len(d.missing) + len(d.held_fields)))


def enhance(store, job, slot) -> str:
    """작업 하나 — 결과 한 줄(로그용). 예외는 호출한 쪽이 실패로 기록한다."""
    data = store.get_pdf(job.sha256)
    if data is None:
        store.finish(job.id, False, "보관된 PDF 없음(기한 지남·삭제)")
        return "PDF 없음"
    version = analysis.analysis_version()
    snap = store.latest_analysis(job.sha256, version)
    old = draft.from_snapshot(snap) if snap else None
    new = draft.make_draft(data, slot=slot)
    better = score(new) > score(old)
    if better:
        store.save_analysis(job.sha256, version, draft.to_snapshot(
            new, job.sha256, created=datetime.now(timezone.utc).isoformat()), analysis.overall_grade(new), by="worker")
    best = new if better else old
    if best is not None and analysis.overall_grade(best) == grading.AUTO:
        store.delete_pdf(job.sha256)
        tail = "자동 확정 → PDF 삭제"
    else:
        store.enqueue(job.sha256, "review", priority=5)
        tail = "확인할 곳 남음 → 운영자 검토"
    store.finish(job.id, True)
    return f"{'나아짐(저장)' if better else '변화 없음'} · {tail} · LLM 호출 {slot.calls}·실패 {slot.failed}"


def status(store) -> str:
    rows = store._run(lambda c: c.execute(
        "SELECT kind, status, count(*) FROM jobs GROUP BY 1, 2 ORDER BY 1, 2").fetchall())
    pdf = store._run(lambda c: c.execute("SELECT count(*), COALESCE(sum(size), 0) FROM pdf_blobs").fetchone())
    jobs = ", ".join(f"{k}/{s} {n}" for k, s, n in rows) or "없음"
    return f"작업: {jobs} | 보관 PDF {pdf[0]}건 {pdf[1] / 1e6:.1f}MB"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="운영자 PC 보강 작업기(Ollama)")
    ap.add_argument("--once", action="store_true", help="지금 있는 작업만 처리하고 끝")
    ap.add_argument("--status", action="store_true", help="대기열 현황만")
    ap.add_argument("--model", default=L.DEFAULT_MODEL)
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    args = ap.parse_args(argv)
    store = get_store()
    if type(store) is NullStore or not store.available:   # Store도 NullStore를 상속하므로 isinstance로 가리지 않는다
        print("공유 저장소에 연결할 수 없습니다(DATABASE_URL 확인).")
        return 2
    if args.status:
        print(status(store))
        return 0
    print(f"보강 작업기 시작 — 모델 {args.model}, 엔진 판 {analysis.analysis_version()}")
    while True:
        purged = store.purge_expired()
        if purged:
            print(f"보관 기한이 지난 PDF {purged}건 삭제")
        job = None
        if ollama_ready(args.host, args.model):
            job = store.claim("enhance")
        else:
            print(f"Ollama({args.host})가 꺼져 있거나 모델 {args.model}이 없습니다 — 작업을 가져가지 않습니다.")
        if job is None:
            if args.once:
                print(status(store))
                return 0
            time.sleep(POLL)
            continue
        slot = L.OllamaSlot(args.model, args.host)
        t = time.time()
        try:
            msg = enhance(store, job, slot)
        except Exception as e:   # noqa: BLE001 — 한 공고의 실패가 작업기를 멈추지 않게(시도 횟수가 남으면 다시 대기)
            store.finish(job.id, False, f"{type(e).__name__}: {e}"[:500])
            msg = f"실패 {type(e).__name__}: {e}"
        print(f"[{job.id}] {job.sha256[:12]} (시도 {job.attempts}) {time.time() - t:.0f}초 — {msg}")


if __name__ == "__main__":
    sys.exit(main())
