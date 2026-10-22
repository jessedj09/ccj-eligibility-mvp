# -*- coding: utf-8 -*-
"""화면(Streamlit) 헤드리스 점검. 사용: python tools/ui_smoke.py   (약 1~3분, 실패 시 종료코드 1)

1) 모든 공고 × 구현된 계층: 기본 입력으로 판정 버튼을 눌러 예외 없이 결과가 나오는지
2) 모든 공고 × 미지원 계층: 판정 버튼 없이 '아직 판정을 지원하지 않습니다' 안내가 나오는지
3) 자녀 입력: '있음'을 고르면 판정 전에 바로 생년월일 칸이 나타나는지(폼 제거 회귀)
4) 출생자녀 가산 경계: N1 신혼부부 4인·가산 자녀 2명 → 자산 413,000,000 충족 / 413,000,001 불충족
5) 지역(C2): N10 대학생 — 거주지·대학 소재지에 따라 충족/불충족, 지역이 필요 없는 공고에는 지역 질문 없음
6) 새 계층(C3): 산업단지근로자·주거급여수급자·지역전략산업종사자·고령자 — 계층 전용 질문과 판정
7) 계층별 입력 안내(주택 소유·소득·자산·나이의 뜻)와 생년월일 → 공고일 기준 만 나이 경계(원문 출생일 범위와 대조)
8) 순위·유형 트랙(C4): 순위별 결과 표시, 사업 전용 질문은 그 계층에서만
9) SH 장기미임대(C4b): 소득이 자격요건이 아니므로 소득을 몰라도 서울 거주면 충족
10) 주거약자용 주택형(C5a): 변형 계층에만 주거약자 유형 질문
11) 장기전세2(C5b): 5년 무소유 질문은 그 사업에만
12) 전체 공고 찾기 페이지(D): 범위가 갈리는 입력(본인 무주택·세대 주택 보유)으로 청년 계층이 신청 가능, 든든전세는 아님
13) 접수 상태(D2): 기준일 2026.10.14.이면 접수 중인 공고만 보이고, 2026.10.22.이면(전부 마감) 안내가 나온다
14) 내 조건 불러오기(D2b): 저장 파일 내용을 입력란에 채우면 그 프로필을 직접 판정한 것과 결과 수가 같다
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

    # 8) 순위·유형 트랙(C4): 청년매입 2순위 탈락·3순위 충족, 신혼·신생아 유형, 든든전세 지역
    at = fresh("N11", "청년")
    at.radio[0].set_value("만 나이").run()
    find(at, "number_input", "나이").set_value(25).run()
    find(at, "number_input", "월소득").set_value(4_000_000).run()
    find(at, "number_input", "총자산").set_value(100_000_000).run()
    find(at, "selectbox", "본인(가구) 복지").select("해당없음").run()
    find(at, "selectbox", "부모의 복지").select("해당없음").run()
    find(at, "selectbox", "지원대상 한부모").select("아니오").run()
    find(at, "selectbox", "소득·자산 검증대상 부모 수").select(2).run()
    find(at, "number_input", "부모 월평균소득").set_value(9_000_000).run()
    find(at, "number_input", "부모 총자산").set_value(100_000_000).run()
    find(at, "number_input", "부모 보유 자동차").set_value(0).run()
    at.button[0].click().run()
    assert not at.exception, at.exception
    youth = results(at)[0][:2]
    tracks = [c.value for c in at.caption if c.value.startswith("충족한 순위")]
    assert youth.startswith("✅") and tracks and "3순위" in tracks[0] and "2순위" not in tracks[0], (youth, tracks)
    at = fresh("N3", "청년")
    assert not [w for w in at.selectbox if w.label.startswith("부모의 복지")], "C4 질문이 행복주택 청년에 나옴"
    at = fresh("N11", "취업준비생")
    assert [w for w in at.date_input if w.label.startswith("대학·고등학교 졸업")], "취업준비생에 졸업일 질문이 없음"
    print("8) C4 트랙 — 청년매입:", youth, tracks[0][:30], "| 행복주택 청년엔 부모 질문 없음 | 취업준비생 졸업일 질문 있음")
    at = fresh("N22", "일반")                       # SH 장기미임대: 소득은 순위 전용 — 몰라도 자격 판정
    at.radio[0].set_value("만 나이").run()
    find(at, "number_input", "나이").set_value(40).run()
    find(at, "selectbox", "본인 거주지").select("서울특별시").run()
    find(at, "checkbox", "월소득(원) 모름").check().run()
    at.button[0].click().run()
    assert not at.exception, at.exception
    vacant = results(at)[0][:2]
    assert vacant.startswith("✅"), vacant
    print("9) SH 장기미임대 — 서울 거주·소득 모름:", vacant)
    weak_q = lambda at: [w for w in at.selectbox if w.label.startswith("주거약자 유형")]
    assert weak_q(fresh("N4", "신혼부부(주거약자용)")) and not weak_q(fresh("N4", "신혼부부")), "주거약자 질문 노출 오류"
    print("10) 주거약자용(C5a): 변형 계층에만 주거약자 유형 질문")
    five_q = lambda at: [w for w in at.selectbox if w.label.startswith("신청자·배우자(예비배우자)가 공고일 기준 최근 5년")]
    assert five_q(fresh("N23", "신혼부부(전용 60㎡ 이하)")) and not five_q(fresh("N26", "일반(전용 60㎡ 이하)"))
    print("11) 장기전세2(C5b): 5년 무소유 질문은 장기전세2에만")

    # 12) 전체 공고 찾기 페이지(D): 부모와 사는 25세 세대원 — 본인 무주택·저소득, 세대는 주택 보유·고소득
    at = AppTest.from_file(str(ROOT / "pages" / "1_내_조건으로_공고_찾기.py"), default_timeout=120).run()
    assert not at.exception, at.exception
    pick = lambda label: [w for w in at.selectbox if w.label.startswith(label)][0]
    at.date_input(key="m_birth").set_value(date(2001, 3, 1)).run()
    [w for w in at.number_input if w.label.startswith("가구원수")][0].set_value(3).run()
    pick("세대주/세대원").select("세대원").run()
    pick("본인 주택 소유").select("무주택").run()
    pick("세대 전원 주택 소유").select("주택보유").run()
    for label, key, value in (("세대 월평균소득", "m_inc_house", 9_000_000), ("본인 월평균소득", "m_inc_self", 3_000_000),
                              ("세대 총자산", "m_ast_house", 600_000_000), ("본인 총자산", "m_ast_self", 20_000_000),
                              ("세대 보유 자동차", "m_car_house", 20_000_000), ("본인 자동차", "m_car_self", 0)):
        [w for w in at.checkbox if w.label.startswith(label)][0].check().run()
        at.number_input(key=key).set_value(value).run()
    pick("본인 거주지").select("서울특별시").run()
    at.button(key="m_run").click().run()
    assert not at.exception, at.exception
    at.radio(key="m_view").set_value("전체 공고(마감 포함)").run()
    assert not at.exception, at.exception
    metrics = {m.label: m.value for m in at.metric}
    youth = [e.label for e in at.expander if e.label.endswith("· 청년")]
    assert int(metrics["✅ 신청 가능"]) >= 6 and len(youth) >= 6, (metrics, youth)
    assert not [e for e in at.expander if "든든전세" in e.label and "✅" in e.label]
    print("12) 전체 공고 찾기(D):", metrics, "| 청년 계층", len(youth), "건 신청 가능")

    # 13) 접수 상태(D2) — 2026.10.14. 12:00에 접수 중: N4(~10.14)·N8·N18·N19(10.13~15)·N17(10.14~16)
    at.radio(key="m_view").set_value("접수 중·예정 공고만").run()
    at.date_input(key="m_at").set_value(date(2026, 10, 14)).run()
    assert not at.exception, at.exception
    # 신청 불가는 묶음 안의 한 줄(캡션), 나머지는 펼침 — 어느 쪽이든 접수 상태가 앞에 붙는다
    labels = [e.label for e in at.expander if " | " in e.label]
    lines = [c.value for c in at.caption if c.value.split(" ")[0] in ("🟢", "🗓️", "⚫")]
    total = sum(int(m.value) for m in at.metric)
    expect = sum(len(ALL_NOTICES[n].layers) for n in ("N4", "N8", "N17", "N18", "N19"))
    assert total == expect, (total, expect)
    assert all(x.startswith("🟢") for x in labels + lines) and labels + lines, (labels, lines)
    at.date_input(key="m_at").set_value(date(2026, 10, 22)).run()
    assert any("접수 중이거나 접수 예정인 공고가 없습니다" in i.value for i in at.info)
    assert sum(int(m.value) for m in at.metric) == 0
    print("13) 접수 상태(D2): 10.14. 접수 중 공고 5건의 계층", total, "개만 표시 / 10.22. 전부 마감 안내")

    # 14) 불러오기(D2b) — 파일 업로드 대신 불러오기가 하는 일(widget_state → session_state)을 그대로 재현한다
    from matcher import MasterProfile, match_all
    from profile_form import widget_state
    from profile_io import master_from_dict, master_to_dict
    # 본인·세대 값이 크게 달라 범위를 잘못 옮기면 판정이 갈리는 프로필(부모와 사는 미혼 청년 + 기혼 세대주 두 가지)
    profiles = [MasterProfile(
        home_self="무주택", home_household="주택보유", income_self=1_000_000, income_household=12_000_000,
        assets_self=10_000_000, assets_household=900_000_000, car_self=0, car_household=50_000_000,
        birth_date=date(2001, 3, 1),
        common=dict(marital_status="미혼", household_size=3, house_head_status="세대원", dual_income=False,
                    children_birth_dates=[], residence_area="서울특별시", school_area="서울특별시", student_status="재학중",
                    parents_count=2, parents_monthly_income=3_000_000, is_employed=True, is_social_rookie=True,
                    registered_with_parents=True, welfare_status="해당없음", parent_welfare_status="해당없음")),
        MasterProfile(
        home_self="무주택", home_household="무주택", income_self=2_500_000, income_household=5_000_000,
        assets_self=30_000_000, assets_household=120_000_000, car_self=0, car_household=15_000_000,
        birth_date=date(1994, 5, 17),
        common=dict(marital_status="혼인중", marriage_date=date(2023, 3, 2), household_size=3, house_head_status="세대주",
                    dual_income=True, children_birth_dates=[date(2025, 1, 9)], residence_area="서울특별시",
                    income_base_area="서울특별시", spouse_residence_area="서울특별시", owned_home_in_5y=False,
                    housing_weak_type="해당없음", supports_elderly_parent_1y=True))]
    for saved in map(master_to_dict, profiles):
        m = master_from_dict(saved)
        at = AppTest.from_file(str(ROOT / "pages" / "1_내_조건으로_공고_찾기.py"), default_timeout=120)
        for k, v in widget_state(m).items():
            at.session_state[k] = v
        at.run()
        assert not at.exception, at.exception
        assert not at.warning, [w.value for w in at.warning]       # value=와 session_state 충돌 경고 없음
        at.button(key="m_run").click().run()
        at.radio(key="m_view").set_value("전체 공고(마감 포함)").run()
        assert not at.exception, at.exception
        got = {m_.label: int(m_.value) for m_ in at.metric}
        direct = [x.verdict for x in match_all(m, ALL_NOTICES)]
        want = {"✅ 신청 가능": direct.count("ELIGIBLE"), "🔍 수동 확인 필요": direct.count("MANUAL_REVIEW"),
                "⚠️ 추가 정보 필요": direct.count("NEEDS_INFO"), "❌ 신청 불가": direct.count("INELIGIBLE")}
        assert got == want, (got, want)
        # 결과 수만이 아니라 어떤 공고·계층이 나왔는지까지(신청 불가를 뺀 펼침 목록) 같아야 한다
        rows = {e.label.split(" | ")[2] for e in at.expander if " | " in e.label}
        rows_want = {f"{x.notice.title} · {x.layer}" for x in match_all(m, ALL_NOTICES) if x.verdict != "INELIGIBLE"}
        assert rows == rows_want, (rows ^ rows_want)
        print("14) 내 조건 불러오기(D2b): 화면 판정 = 직접 판정", got)

    ok, ng = scenario(413_000_000), scenario(413_000_001)
    assert ok and ok[0].startswith("✅") and ng and ng[0].startswith("❌"), (ok, ng)
    print("4) 자녀 가산 경계 413,000,000 →", ok[0], "/ 413,000,001 →", ng[0])


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("실패:", e)
        sys.exit(1)
