# -*- coding: utf-8 -*-
"""profile_form.py — 저장 파일(MasterProfile) → '내 조건으로 공고 찾기' 화면의 입력란 값(D2b).

화면(pages/1_내_조건으로_공고_찾기.py)이 불러오기에 쓴다. streamlit 없이 테스트할 수 있게 분리했다 — 화면이 MasterProfile에 넘기는
항목과 이 표가 어긋나지 않는지는 tests/test_d2b_profile_api.py가, 불러온 결과가 같은 판정을 내는지는 tools/ui_smoke.py가 확인한다.
"""
from typing import Any, Dict

from matcher import MasterProfile

# (위젯 key, 프로필 항목, 종류) — "master.x"는 범위별 항목, 그 밖은 common 항목.
# 종류: raw(그대로) / pick(모름=None) / yes_no / amount(입력 체크 + 금액) / date
WIDGETS = [
    ("m_birth", "master.birth_date", "date"), ("m_marital", "marital_status", "raw"),
    ("m_marriage", "marriage_date", "date"), ("m_size", "household_size", "raw"),
    ("m_head", "house_head_status", "pick"), ("m_dual", "dual_income", "raw"),
    ("m_home_self", "master.home_self", "pick"), ("m_home_house", "master.home_household", "pick"),
    ("m_inc_house", "master.income_household", "amount"), ("m_inc_self", "master.income_self", "amount"),
    ("m_ast_house", "master.assets_household", "amount"), ("m_ast_self", "master.assets_self", "amount"),
    ("m_car_house", "master.car_household", "amount"), ("m_car_self", "master.car_self", "amount"),
    ("m_res", "residence_area", "pick"), ("m_incbase", "income_base_area", "pick"), ("m_school", "school_area", "pick"),
    ("m_sp_res", "spouse_residence_area", "pick"), ("m_sp_inc", "spouse_income_base_area", "pick"),
    ("m_student", "student_status", "pick"), ("m_grad", "grad_or_dropout_date", "date"),
    ("m_employed", "is_employed", "yes_no"), ("m_rookie", "is_social_rookie", "yes_no"),
    ("m_owned5", "owned_home_in_5y", "yes_no"), ("m_welfare", "welfare_status", "pick"),
    ("m_pwelfare", "parent_welfare_status", "pick"), ("m_regpar", "registered_with_parents", "yes_no"),
    ("m_supsp", "is_supported_single_parent", "yes_no"), ("m_benefit", "housing_benefit_status", "pick"),
    ("m_pcount", "parents_count", "pick"), ("m_pinc", "parents_monthly_income", "amount"),
    ("m_past", "parents_total_assets", "amount"), ("m_pcar", "parents_car_value", "amount"),
    ("m_weak", "housing_weak_type", "pick"), ("m_work", "industrial_workplace", "pick"),
    ("m_workarea", "workplace_area", "pick"), ("m_affil", "industrial_affiliation", "pick"),
    ("m_regional", "regional_industry_type", "pick"), ("m_spdis", "disabled_spouse_qualifies", "yes_no"),
    ("m_eparent", "supports_elderly_parent_1y", "yes_no"), ("m_veteran", "veteran_priority_notified", "yes_no"),
]


def widget_state(m: MasterProfile, unknown: str = "모름") -> Dict[str, Any]:
    """불러온 프로필을 입력란 값(session_state key → 값)으로 옮긴다. 자녀는 수(m_kids)와 생년월일(m_kid_i)."""
    out: Dict[str, Any] = {}
    for key, name, kind in WIDGETS:
        v = getattr(m, name[7:]) if name.startswith("master.") else m.common.get(name)
        if kind == "amount":
            out[f"{key}_known"] = v is not None
            if v is not None:
                out[key] = int(v)
        elif kind == "pick":
            out[key] = unknown if v is None else v
        elif kind == "yes_no":
            out[key] = {True: "예", False: "아니오"}.get(v, unknown)
        elif kind == "date":
            if v is not None or key == "m_grad":     # 졸업일은 비워 둘 수 있다
                out[key] = v
        elif v is not None:
            out[key] = v
    kids = m.common.get("children_birth_dates") or []
    out["m_kids"] = len(kids)
    for i, d in enumerate(kids):
        out[f"m_kid_{i}"] = d
    return out
