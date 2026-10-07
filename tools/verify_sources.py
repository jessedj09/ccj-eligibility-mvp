# -*- coding: utf-8 -*-
"""규칙 데이터의 원문 근거를 공고문 PDF와 대조한다. 사용: python tools/verify_sources.py (불일치가 있으면 종료코드 1)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import source_verify  # noqa: E402

failed = False
for name, rep in source_verify.verify_all().items():
    print(f"{name}: 대조 {rep.checked}건, 도출 설명(PDF 대조 제외) {rep.derivations}건, 불일치 {len(rep.problems)}건")
    for p in rep.problems:
        print("  -", p)
    failed |= not rep.ok
sys.exit(1 if failed else 0)
