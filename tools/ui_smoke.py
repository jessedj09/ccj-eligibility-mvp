# -*- coding: utf-8 -*-
"""화면(Streamlit) 헤드리스 점검. 사용: python tools/ui_smoke.py   (약 1~3분, 실패 시 종료코드 1)

1) 모든 공고 × 구현된 계층: 기본 입력으로 판정 버튼을 눌러 예외 없이 결과가 나오는지
2) 모든 공고 × 미지원 계층: 판정 버튼 없이 '아직 판정을 지원하지 않습니다' 안내가 나오는지
3) 자녀 입력: '있음'을 고르면 판정 전에 바로 생년월일 칸이 나타나는지(폼 제거 회귀)
4) 출생자녀 가산 경계: N1 신혼부부 4인·가산 자녀 2명 → 자산 413,000,000 충족 / 413,000,001 불충족
"""
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))

from streamlit.testing.v1 import AppTest  # noqa: E402
from notices_data import ALL_NOTICES  # noqa: E402


def fresh(nid, layer):
    at = AppTest.from_file("app.py", default_timeout=60).run()
    at.sidebar.selectbox[0].select(nid).run()
    at.sidebar.selectbox[1].select(layer).run()
    return at


def find(at, kind, label):
    return [w for w in getattr(at, kind) if w.label.startswith(label)][0]


def results(at):
    return [e.value for e in at.success] + [e.value for e in at.error] + [e.value for e in at.warning]


def main():
    count = 0
    for nid, notice in ALL_NOTICES.items():
        for layer in notice.layers:
            at = fresh(nid, layer)
            for preset in at.sidebar.selectbox[2].options:
                at.sidebar.selectbox[2].select(preset).run()
                at.button[0].click().run()
                assert not at.exception, (nid, layer, preset, at.exception)
                assert results(at), (nid, layer, preset, "결과 없음")
                count += 1
        for u in notice.meta.get("unsupported_layers", []):
            at = fresh(nid, u["name"])
            assert not at.exception, (nid, u["name"], at.exception)
            assert any("아직 판정을 지원하지 않습니다" in e.value for e in at.info), (nid, u["name"])
            assert len(at.button) == 0, (nid, u["name"], "미지원 계층에 판정 버튼이 있음")
            count += 1
    print("1·2) 공고·계층·샘플 조합 통과:", count)

    at = fresh("N1", "신혼부부")
    find(at, "selectbox", "자녀").select("있음").run()
    n_dates = len([w for w in at.date_input if w.label.startswith("자녀")])
    assert n_dates == 1, n_dates
    print("3) 자녀 '있음' 선택 직후 생년월일 칸:", n_dates)

    def scenario(assets):
        at = fresh("N1", "신혼부부")
        find(at, "selectbox", "혼인 상태").select("혼인중").run()
        find(at, "number_input", "가구원수").set_value(4).run()
        find(at, "selectbox", "자녀").select("있음").run()
        find(at, "number_input", "자녀 수").set_value(2).run()
        [w for w in at.date_input if w.label.startswith("자녀")][0].set_value(date(2024, 1, 1)).run()
        [w for w in at.date_input if w.label.startswith("자녀")][1].set_value(date(2015, 5, 5)).run()
        find(at, "number_input", "월소득").set_value(1_000_000).run()
        find(at, "number_input", "총자산").set_value(assets).run()
        at.button[0].click().run()
        assert not at.exception, at.exception
        return results(at)

    ok, ng = scenario(413_000_000), scenario(413_000_001)
    assert ok and ok[0].startswith("✅") and ng and ng[0].startswith("❌"), (ok, ng)
    print("4) 자녀 가산 경계 413,000,000 →", ok[0], "/ 413,000,001 →", ng[0])


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("실패:", e)
        sys.exit(1)
