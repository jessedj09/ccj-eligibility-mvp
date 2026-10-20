# -*- coding: utf-8 -*-
"""화면(Streamlit) 헤드리스 점검. 사용: python tools/ui_smoke.py   (약 1~3분, 실패 시 종료코드 1)

1) 모든 공고 × 구현된 계층: 기본 입력으로 판정 버튼을 눌러 예외 없이 결과가 나오는지
2) 모든 공고 × 미지원 계층: 판정 버튼 없이 '아직 판정을 지원하지 않습니다' 안내가 나오는지
3) 자녀 입력: '있음'을 고르면 판정 전에 바로 생년월일 칸이 나타나는지(폼 제거 회귀)
4) 출생자녀 가산 경계: N1 신혼부부 4인·가산 자녀 2명 → 자산 413,000,000 충족 / 413,000,001 불충족
5) 지역(C2): N10 대학생 — 거주지·대학 소재지에 따라 충족/불충족, 지역이 필요 없는 공고에는 지역 질문 없음
6) 새 계층(C3): 산업단지근로자·주거급여수급자·지역전략산업종사자·고령자 — 계층 전용 질문과 판정
7) 계층별 입력 안내(주택 소유·소득·자산·나이의 뜻)와 생년월일 → 공고일 기준 만 나이 경계(원문 출생일 범위와 대조)
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
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.sidebar.selectbox[0].select(nid).run()
    at.sidebar.selectbox[1].select(layer).run()
    return at


def find(at, kind, label):
    return [w for w in getattr(at, kind) if w.label.startswith(label)][0]


def _marked(kind, text):
    """판정 박스를 '아이콘 + 문구'로 정규화한다. Streamlit 버전에 따라 문구 앞 이모지가 값에 남거나(1.45)
    아이콘으로 분리돼 빠진다(1.66) — 아이콘 글자 대신 박스 종류와 문구로 판정을 구분한다."""
    text = text.lstrip("✅❌🔍⚠️ ️")
    if kind == "success":
        mark = "✅"
    elif kind == "error":
        mark = "❌"
    else:
        mark = "🔍" if "수동 확인" in text else "⚠️"
    return f"{mark} {text}"


def results(at):
    return ([_marked("success", e.value) for e in at.success] + [_marked("error", e.value) for e in at.error]
            + [_marked("warning", e.value) for e in at.warning])


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

    def region(area, school):
        at = fresh("N10", "대학생")
        at.sidebar.selectbox[2].select("P01").run()     # N3 대학생 ELIGIBLE 샘플 — 지역 외 조건은 모두 충족
        find(at, "selectbox", "본인 거주지").select(area).run()
        find(at, "selectbox", "재학 중").select(school).run()
        at.button[0].click().run()
        assert not at.exception, at.exception
        return results(at)

    r_seoul, r_out, r_school = region("서울특별시", "모름"), region("수원시", "해당없음"), region("수원시", "고양시")
    assert r_seoul[0].startswith("✅") and r_out[0].startswith("❌") and r_school[0].startswith("✅"),         (r_seoul, r_out, r_school)
    at = fresh("N3", "대학생")
    assert not [w for w in at.selectbox if w.label.startswith("본인 거주지")], "지역이 필요 없는 공고에 지역 질문이 나옴"
    print("5) N10 대학생 지역: 서울 →", r_seoul[0][:2], "/ 수원·대학 없음 →", r_out[0][:2], "/ 수원·고양 대학 →", r_school[0][:2],
          "| N3에는 지역 질문 없음")

    def c3(nid, layer, picks, regions=None, age=None):
        at = fresh(nid, layer)
        if age is not None:
            at.radio[0].set_value("만 나이").run()
            find(at, "number_input", "나이").set_value(age).run()
        find(at, "number_input", "월소득").set_value(1_000_000).run()
        find(at, "number_input", "총자산").set_value(100_000_000).run()
        for label, value in picks:
            find(at, "selectbox", label).select(value).run()
        for label, value in (regions or []):
            find(at, "selectbox", label).select(value).run()
        at.button[0].click().run()
        assert not at.exception, at.exception
        return results(at)[0][:2]

    got = {
        "산단 서울 소속": c3("N6", "산업단지근로자", [("근무처 유형", "산업단지 입주기업"), ("그 근무처", "소속")],
                       [("근무처(산업단지", "서울특별시")]),
        "산단 수원": c3("N6", "산업단지근로자", [("근무처 유형", "산업단지 입주기업"), ("그 근무처", "소속")],
                     [("근무처(산업단지", "수원시")]),
        "주거급여 수급자": c3("N10", "주거급여수급자", [("주거급여", "수급자")]),
        "부천 등록예술인": c3("N5", "지역전략산업종사자", [("지역전략산업종사자 유형", "등록 예술인")], age=30),
        "부천 콘텐츠": c3("N5", "지역전략산업종사자", [("지역전략산업종사자 유형", "콘텐츠산업 종사자")], age=30),
        "가좌 고령자 70세": c3("N9", "고령자", [], age=70),
    }
    want = {"산단 서울 소속": "✅", "산단 수원": "❌", "주거급여 수급자": "✅", "부천 등록예술인": "✅",
            "부천 콘텐츠": "🔍", "가좌 고령자 70세": "✅"}
    assert all(got[k].startswith(want[k]) for k in want), got
    at = fresh("N3", "청년")
    assert not [w for w in at.selectbox if w.label.startswith("근무처 유형")], "새 계층 질문이 다른 계층에 나옴"
    print("6) C3 새 계층:", got)

    # 7) 입력 범위 안내(같은 질문의 계층별 뜻)와 생년월일 → 공고일 기준 만 나이
    def captions(nid, layer):
        return [c.value for c in fresh(nid, layer).caption if c.value.startswith("이 계층 기준")]
    stu, mar = captions("N3", "대학생"), captions("N3", "신혼부부")
    assert any("본인" in c for c in stu) and any("세대" in c for c in mar), (stu, mar)
    at = fresh("N5", "청년")                         # 공고일 2026-08-18, 원문 출생일 범위 1986.8.19 ~ 2007.8.18
    ages = {}
    for born in (date(2007, 8, 18), date(2007, 8, 19), date(1986, 8, 19), date(1986, 8, 18)):
        at.date_input(key="birth_date").set_value(born).run()
        ages[str(born)] = [c.value for c in at.caption if c.value.startswith("공고일(")][0]
    assert "만 19세" in ages["2007-08-18"] and "만 18세" in ages["2007-08-19"], ages
    assert "만 39세" in ages["1986-08-19"] and "만 40세" in ages["1986-08-18"], ages
    print("7) 계층별 입력 안내 — 대학생:", stu[0][:40], "… / 신혼부부:", mar[0][:40], "… | 생년월일→만 나이 경계 OK")

    ok, ng = scenario(413_000_000), scenario(413_000_001)
    assert ok and ok[0].startswith("✅") and ng and ng[0].startswith("❌"), (ok, ng)
    print("4) 자녀 가산 경계 413,000,000 →", ok[0], "/ 413,000,001 →", ng[0])


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("실패:", e)
        sys.exit(1)
