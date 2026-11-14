# -*- coding: utf-8 -*-
"""test_unseen_messages.py — 처음 보는 실공고 15건(2026-11-08 sample_new)에서 드러난 분류·안내 결함.

- SH '자립준비청년 청년매입임대'·SH 행복주택이 사업 이름표의 LH 고정 때문에 LH 판정 틀로 들어갔다(SH 주소가 있으면 SH).
- 필수 빈칸이 보류라 규칙을 만들지 못하면 화면에 'TypeError youth_rental() missing …'이 그대로 나갔다.
- 막힌 이유가 빈칸 이름(eligibility_quote)으로, 미지원 이유가 '사업 유형을 알아보지 못했습니다'(사업은 알아봤는데)로 나갔다.
"""
import sys
from pathlib import Path

import draft
import notice_candidates as nc

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402


def test_sh_address_wins_over_lh_program_label():
    pages = ["2026.5.29.서울주택도시개발공사자립준비청년2026년상반기청년매입임대주택우선공급입주자모집", "www.i-sh.co.kr"]
    assert nc.classify(pages) == ("SH", "청년매입임대")
    assert nc.classify(["서울주택도시개발공사2026년1차행복주택입주자모집공고", "i-sh.co.kr"]) == ("SH", "행복주택")
    assert nc.classify(["청년매입임대주택입주자모집공고", "LH청약플러스"]) == ("LH", "청년매입임대")


def test_lh_templates_not_used_for_sh_notices():
    assert X.choose_template("SH", "든든전세") is None
    assert X.choose_template("SH", "청년매입임대") == "sh.youth_rental"    # 2026-11-14: SH 전용 틀(LH 틀은 쓰지 않음)
    assert X.choose_template("SH", "행복주택") == "sh.happy_housing"     # 2026-11-10: SH 전용 틀(LH 틀은 쓰지 않음)
    assert X.choose_template("LH", "청년매입임대") == "lh.youth_rental"
    assert X.choose_template("LH", "행복주택") == "lh.happy_housing"
    assert X.choose_template("SH", "SH 장기전세주택") == "sh.jeonse"


def test_self_reliance_youth_variant_blocked():
    msg = X.variant_notice("lh.youth_rental", ["자립준비청년2026년상반기청년매입임대주택우선공급", "…"])
    assert msg and "자립준비청년" in msg and "자동 판정하지 않습니다" in msg
    assert X.variant_notice("lh.youth_rental", ["2026년청년매입임대주택입주자모집"]) is None


def test_build_error_not_shown_raw(monkeypatch):
    def boom(*a, **k):
        raise TypeError("youth_rental() missing 2 required positional arguments")
    monkeypatch.setattr(X, "_build", boom)
    ext = {"template": "lh.youth_rental", "fields": {}, "announcement_date": X.Field(X.FILLED, "2026-05-29")}
    g = X.gate(ext, None, ["2026년청년매입임대주택입주자모집"])
    assert g["doc"] is None and "TypeError" not in g["blocked"] and "자동 판정하지 않습니다" in g["blocked"]
    assert "TypeError" in g["build_error"]          # 도구·로그용 원인은 따로 남긴다


def test_field_labels_for_blocked_reason():
    assert X.field_label("lh.elderly_welfare", "eligibility_quote").startswith("공통 신청자격 문장")
    assert X.field_label("lh.elderly_welfare", "merit_quote") == "2순위 소득 70% 문구"
    assert X.field_label("lh.youth_rental", "announcement_date") == "모집공고일"
    assert X.field_label("lh.youth_rental", "announcement_date: 범위 밖") == "announcement_date: 범위 밖"
    assert X.field_label(None, "layers") == "layers"


def test_unsupported_reason_names_recognized_program():
    assert draft._program_name({"program": "매입임대주택", "issuer": "SH"}) == "SH 매입임대주택"
    assert draft._program_name({"program": "SH 장기전세주택", "issuer": "SH"}) == "SH 장기전세주택"
    assert draft._program_name({"program": "도시형생활주택", "issuer": None}) == "도시형생활주택"
    assert draft._program_name({"program": None, "issuer": "SH"}) is None
    assert "LH 분양주택" in draft.unsupported_reason("LH 분양주택")
    assert "임대 공고만" not in draft.unsupported_reason("LH 분양주택")      # 공공분양 일부는 이미 판정한다


def test_ikgong_type_sale_is_share_sale():
    """'이익공유형 분양주택'은 나눔형의 법령상 이름(고양창릉 S-3 2026.06.30. 본청약) — 나눔형 틀로 가고, 2024.1. 사전청약 기준과
    금액·비율 문구가 달라 필수 값이 보류되어 자동 판정하지 않는다."""
    assert nc.classify(["-1-고양창릉지구S-3블록이익공유형분양주택입주자모집공고❚공급위치:경기도고양시", "LH청약플러스"]) == \
        ("LH", "공공분양(나눔형)")
    assert X.choose_template("LH", "공공분양(나눔형)") == "lh.share_sale"
