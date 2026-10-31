# -*- coding: utf-8 -*-
"""warm_cache.py — 배포 이미지를 만들 때(Dockerfile) 등록 공고 원문의 추출 캐시를 미리 채운다.

자동 분석(src/analysis.py)은 형제 공고 원문의 쪽 텍스트(.cache/pdf_text)와 조항 장부 문장(.cache/ledger_units)을 쓴다.
비어 있으면 첫 업로드가 등록 공고 PDF를 모두 다시 읽느라 느려진다. 캐시 키는 원문 지문이라 결과는 캐시가 없을 때와 같다.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import clause_ledger as CL  # noqa: E402
import source_verify as sv  # noqa: E402
from rule_data import notice_ids  # noqa: E402


def main() -> None:
    t = time.time()
    ids = notice_ids()
    for nid in ids:
        sv.pdf_pages(nid)
        CL.registered_units(nid)
    print(f"warm_cache: 등록 공고 {len(ids)}건, {time.time() - t:.1f}초")


if __name__ == "__main__":
    main()
