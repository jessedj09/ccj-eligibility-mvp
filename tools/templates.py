# -*- coding: utf-8 -*-
"""사업 템플릿과 파라미터 시트(P1 T3.1, docs/09 §5).

같은 사업은 차수가 바뀌어도 규칙 구조가 같고 공고마다 바뀌는 값 몇 개만 다르다. 그 값의 묶음이 **파라미터 시트**다.

    sheet = {"notice_id", "template", "issuer", "program", "title", "announcement_date", "params", "meta"}
    doc, missing = build(sheet, pdf)          # 시트 + 원문 PDF → 공고 규칙 문서(기존 생성 스크립트 그대로), 찾지 못한 인용문

- 템플릿 = 기존 생성 스크립트의 빌더(tools/gen_*.py). 이 모듈은 그것을 이름으로 묶을 뿐 규칙을 새로 만들지 않는다.
- **정답 시트** = 등록 공고를 만든 생성 스크립트의 PLAN 값(`gold_sheet(nid)`). 정답 시트로 다시 만들면 등록 규칙과 똑같아야 한다
  (tests/test_t31_templates.py) — 템플릿이 정확하다는 증거이고, 추출 정확도 평가(T3.4)의 정답지다.
- `missing`이 비어 있지 않으면 시트의 값 또는 템플릿 문구가 그 공고 원문에 없다는 뜻이다 — 연도별 상수(자산 한도 등)가 바뀐
  새 공고는 여기서 걸린다(검증 관문의 한 축).
- 행복주택 기준 공고 N1(신혼희망타운)·N3(일반)는 템플릿 원본이고 N2는 손으로 만든 공고라 시트가 없다.

사용: python tools/templates.py --check     # 정답 시트로 전부 다시 만들어 등록 규칙과 비교
      python tools/templates.py --export DIR  # 정답 시트를 JSON으로 내보내기(검토용)
"""
import copy
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import source_verify as sv  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C1, C3, C5A = _load("gen_c1_notices"), _load("gen_c3_layers"), _load("gen_c5_housing_weak")
LH, SH, JS = _load("gen_c4_lh"), _load("gen_c4_sh"), _load("gen_c5_jeonse")
PUB = _load("gen_c6_public")


@dataclass(frozen=True)
class Param:
    name: str
    kind: str          # date / text / choice / bool / list / quotes / table / region / layers / weak
    note: str
    critical: bool = True     # 판정에 직접 쓰이는 값(기준일·한도 등) — 인용문에만 쓰이는 값은 False


# 템플릿별 빈칸(파라미터) 정의. 공통 빈칸: announcement_date(공고일 — 나이·기준일 계산의 기준, 항상 critical)
TEMPLATES: Dict[str, Dict] = {
    "lh.youth_rental": dict(module=LH, builder="youth_rental", issuer="LH", program="청년매입임대", params=[
        Param("birth_range", "text", "청년(19~39세) 출생일 범위 원문 — 예 '1986.06.26. ~ 2007.06.25.'", critical=False),
        Param("under30", "text", "만 30세 미만 기준 출생일 원문 — 예 '1996.06.26.'", critical=False),
    ]),
    "lh.newlywed_rental": dict(module=LH, builder="newlywed_rental", issuer="LH", program="신혼·신생아 매입임대", params=[
        Param("kind", "choice", "Ⅰ(I) / Ⅱ 전세형(II) — 소득·자산 기준표가 다르다"),
        Param("marriage_quote", "text", "혼인 7년 이내 기간 원문", critical=False),
        Param("marriage", "date", "혼인신고일 기준일(이 날 이후)"),
        Param("child6", "date", "6세 이하 자녀 출생 기준일"),
        Param("newborn", "date", "신생아(2년 이내) 출생 기준일"),
        Param("child6_quote", "text", "6세 이하 자녀 기준일 원문", critical=False),
        Param("newborn_quote", "text", "신생아 기준일 원문", critical=False),
    ]),
    "lh.deundeun": dict(module=LH, builder="jeonse", issuer="LH", program="든든전세(비분양전환형)", params=[]),
    "sh.newlywed": dict(module=SH, builder="sh_newlywed", issuer="SH", program="SH 신혼·신생아 매입임대 / 일반주택형 미리내집", params=[
        Param("kind", "choice", "Ⅰ(I) / Ⅱ(II, 미리내집 포함) — 소득 기준표가 다르다"),
        Param("dates", "dates", "기준일 리터럴: marriage(혼인 7년)·child6(6세 이하)·newborn(신생아)·minor(지원대상 한부모 미성년, 있으면)"),
        Param("single_parent_minor", "bool", "지원대상 한부모가족의 '미성년 자녀' 조건이 있는지"),
        Param("quotes", "quotes", "조건별 원문 문장(공고마다 표현이 다름 — 같은 뜻의 문장을 이 공고에서 다시 찾는다)", critical=False),
    ]),
    "sh.vacant": dict(module=SH, builder="sh_vacant", issuer="SH", program="SH 장기미임대 매입임대", params=[]),
    "sh.jeonse2": dict(module=JS, builder="jeonse2", issuer="SH", program="SH 장기전세주택2(미리내집)", params=[
        Param("dates", "dates", "기준일 리터럴: marriage(혼인 7년)·five(5년 무소유)"),
        Param("quotes", "quotes", "조건별 원문 문장", critical=False),
        Param("weak_quote", "text", "주거약자형 주택 신청자격 원문(주거약자형이 있을 때만)", critical=False),
    ]),
    "sh.jeonse": dict(module=JS, builder="jeonse", issuer="SH", program="SH 장기전세주택", params=[
        Param("quotes", "quotes", "조건별 원문 문장 + 자산·자동차 한도 문구, 우선공급 기준일(minor_date)·고령자 우선공급 여부"),
        Param("weak_quote", "text", "주거약자형 주택 신청자격 원문", critical=False),
        Param("income", "table", "면적대(60㎡ 이하/초과)별 소득 상한 원문 금액 — 기준 연도·비율에 따라 공고마다 다름"),
    ]),
    # G2(2026-11-01): 공공임대 새 사업 — 공고마다 바뀌는 값은 공고일뿐(자산·자동차 한도는 리터럴, 다음 해 기준이면 인용문 보류)
    "lh.national_rental": dict(module=PUB, builder="national_rental", issuer="LH", program="국민임대", params=[
        Param("elderly_quote", "text", "고령자 전용 주택형 문구(있으면 65세 이상 계층을 더 만든다)", critical=False),
    ]),
    "lh.permanent_rental": dict(module=PUB, builder="permanent_rental", issuer="LH", program="영구임대", params=[
        Param("city", "region", "거주 요건 시·군(주민등록 등재) — 표준 지역 이름"),
        Param("residence_quote", "text", "거주·무주택세대구성원 요건 문장", critical=False),
        Param("adult_quote", "text", "성년 요건 문장", critical=False),
        Param("weak_quote", "text", "주거약자용 주택형 문구(있으면 주거약자 계층을 더 만든다)", critical=False),
    ]),
    # 통합공공임대 일반형: 공고별 값 없음(날짜 기준은 공고일에서, 소득표·자산 한도는 같은 연도 공고에서 같다)
    "lh.integrated_rental": dict(module=PUB, builder="integrated_rental", issuer="LH", program="통합공공임대", params=[]),
    # G4 공공임대(10년·분양전환·50년) 예비입주자: 거주 지역·청약통장 요건·재당첨 제한 문구를 공고에서 읽는다
    "lh.public_rental": dict(module=PUB, builder="public_rental", issuer="LH", program="공공임대(10년·분양전환·50년) 예비입주자",
                             params=[
        Param("eligibility_quote", "text", "신청 자격 문장('현재 ○○에 거주하는 … 무주택세대구성원')"),
        Param("residence", "choice", "거주 요건 — '수도권' 또는 없음(국내·거주 요건 없음)"),
        Param("account", "choice", "청약통장 요건 — 없음(관계없음) / '가입' / {months, count}(2순위 최소)"),
        Param("account_quote", "text", "청약통장 요건 문장", critical=False),
        Param("adult_quote", "text", "성년 요건 문장", critical=False),
        Param("rewin_quote", "text", "재당첨 제한 문구(있으면 그 조건)", critical=False),
    ]),
    # G3 신혼희망타운(공공분양): 잔여세대 '불문' 단순형 / 정규형(수도권·저축·소득·자산·재당첨·특별공급 이력)
    "lh.newlywed_town_sale": dict(module=PUB, builder="newlywed_town_sale", issuer="LH", program="신혼희망타운(공공분양)",
                                  params=[
        Param("open_quote", "text", "'입주자저축 가입 여부 … 소득 및 자산 요건 불문' 문구(있으면 단순형)", critical=False),
        Param("eligibility_quote", "text", "단순형의 거주·나이 문장", critical=False),
        Param("residence", "choice", "거주 요건 — '수도권' 또는 없음(전국)"),
        Param("layer_quotes", "quotes", "유형(신혼부부·예비신혼부부·한부모)별 자격 문장"),
    ]),
    # G3 LH 공공분양: 다자녀·노부모·생애최초·신혼부부·신생아 특별공급 + 일반공급(전용 60㎡ 이하/초과)
    "lh.public_sale": dict(module=PUB, builder="public_sale", issuer="LH", program="공공분양", params=[
        Param("residence", "choice", "거주 요건 — '수도권' 또는 없음"),
        Param("small", "choice", "전용 60㎡ 이하 주택형이 있는지(일반공급 소득·자산 기준 계층)"),
        Param("large", "choice", "전용 60㎡ 초과 주택형이 있는지"),
    ]),
    # G3-3 SH 토지임대부 분양: 청년·신혼부부·생애최초·신생아 특별공급 + 일반공급, 총자산 기준, 투기과열지구 생애최초 1순위
    "sh.land_sale": dict(module=PUB, builder="sh_land_sale", issuer="SH", program="SH 토지임대부 분양", params=[
        Param("residence", "choice", "거주 요건 — '수도권' 또는 없음"),
        Param("overheated", "choice", "투기과열지구인지(생애최초 1순위 2년·24회 + 세대주 + 5년 내 당첨 없음)"),
    ]),
    # G5 SH 국민임대: 서울 거주 + 국민임대 법령 기준(소득 70%·총자산·자동차), 일반공급(일반·주거약자)
    "sh.national_rental": dict(module=PUB, builder="sh_national_rental", issuer="SH", program="SH 국민임대", params=[
        Param("eligibility_quote", "text", "공통 신청자격 문장('현재 서울특별시에 거주하는 성년자인 무주택세대구성원')"),
        Param("adult_quote", "text", "성년 요건 문장"),
        Param("income_quote", "text", "소득 기준 문장(70% 이하)"),
        Param("near_quote", "text", "서울 밖 일부 시 거주자도 받는 단지 문구(있을 때만)", critical=False),
        Param("weak_quote", "text", "일반공급(주거약자) 신청자격 문구(있으면 주거약자 계층을 더 만든다)", critical=False),
    ]),
    # G5 SH 영구임대: 서울 거주 + 별표3 1순위(가~자), 총자산·자동차 한도는 공고 1건의 리터럴(다르면 보류)
    "sh.permanent_rental": dict(module=PUB, builder="sh_permanent_rental", issuer="SH", program="SH 영구임대", params=[
        Param("eligibility_quote", "text", "공통 신청자격 문장('현재 서울특별시에 거주하는 성년자인 무주택세대구성원으로')"),
        Param("adult_quote", "text", "성년 요건 문장"),
        Param("income_quote", "text", "소득 기준 문장(70% 이하, 1인 90%·2인 80%)"),
        Param("asset_quote", "text", "총자산 한도 문구(판정 틀의 금액과 같아야)"),
        Param("car_quote", "text", "자동차 한도 문구(판정 틀의 금액과 같아야)"),
    ]),
    # G5 LH 고령자복지주택(영구임대형): 65세 이상 + 1순위 생계·의료급여 / 2순위 국가유공자 등 70% / 3순위 일반 50%
    "lh.elderly_welfare": dict(module=PUB, builder="elderly_welfare", issuer="LH", program="고령자복지주택(영구임대형)", params=[
        Param("kind", "choice", "영구임대형인지(제목 '고령자복지주택(영구임대)') — 아니면 자동 판정하지 않는다"),
        Param("eligibility_quote", "text", "공통 신청자격 문장('현재 만65세 이상 … 무주택세대구성원 요건을 만족하고')"),
        Param("merit_quote", "text", "2순위 소득 70% 문구"),
        Param("general_quote", "text", "3순위 소득 50% 문구"),
        Param("asset_quote", "text", "총자산 한도 문구(판정 틀의 금액과 같아야)", critical=False),
        Param("car_quote", "text", "자동차 한도 문구(판정 틀의 금액과 같아야)", critical=False),
    ]),
    "lh.happy_housing": dict(module=C1, builder=None, issuer="LH", program="행복주택", params=[
        Param("base", "choice", "기준 템플릿 — N3(일반 행복주택) / N1(신혼희망타운 행복주택)"),
        Param("layers", "layers", "공급 계층(대학생·청년·신혼부부·한부모 중 이 공고에 있는 것)"),
        Param("marriage", "date", "혼인 7년 기준일 리터럴(원문에 없으면 null — 공고일에서 LH 관행으로 도출)"),
        Param("child", "date", "6세 이하 자녀 출생 기준일 리터럴(원문에 없으면 null)"),
        Param("region", "region", "1순위 지역만 모집하는 경우 계층별 지역 조건(없으면 빈 값)"),
        Param("overrides", "quotes", "템플릿 문구와 표현이 다른 조건의 이 공고 원문 문장", critical=False),
        Param("extra_layers", "layers", "추가 계층(고령자·산업단지근로자·주거급여수급자·지역전략산업종사자)과 위치"),
        Param("weak", "weak", "주거약자용 주택형(있으면 대상 계층·인용문)"),
    ]),
}
_PLAN_TEMPLATE = {(LH, "youth_rental"): "lh.youth_rental", (LH, "newlywed_rental"): "lh.newlywed_rental",
                  (LH, "jeonse"): "lh.deundeun", (SH, "sh_newlywed"): "sh.newlywed", (SH, "sh_vacant"): "sh.vacant",
                  (JS, "jeonse2"): "sh.jeonse2", (JS, "jeonse"): "sh.jeonse",
                  (PUB, "national_rental"): "lh.national_rental", (PUB, "permanent_rental"): "lh.permanent_rental",
                  (PUB, "integrated_rental"): "lh.integrated_rental", (PUB, "public_rental"): "lh.public_rental",
                  (PUB, "newlywed_town_sale"): "lh.newlywed_town_sale", (PUB, "public_sale"): "lh.public_sale",
                  (PUB, "sh_land_sale"): "sh.land_sale", (PUB, "sh_national_rental"): "sh.national_rental",
                  (PUB, "sh_permanent_rental"): "sh.permanent_rental", (PUB, "elderly_welfare"): "lh.elderly_welfare"}
BASE_NOTICES = ("N1", "N2", "N3")      # 시트 없음(템플릿 원본·손으로 만든 공고)


def _plain(x):
    return json.loads(json.dumps(x, ensure_ascii=False))


def _plan_of(nid: str):
    for module in (LH, SH, JS, PUB):
        for plan in module.PLAN:
            if plan["nid"] == nid:
                return module, plan
    return None, None


def gold_sheet(nid: str) -> Dict:
    """등록 공고를 만든 생성 스크립트의 값 = 정답 파라미터 시트."""
    module, plan = _plan_of(nid)
    if plan is not None:
        tname = _PLAN_TEMPLATE[(module, plan["template"])]
        return _plain({"notice_id": nid, "template": tname, "issuer": TEMPLATES[tname]["issuer"],
                       "program": plan["program"], "title": plan["title"], "announcement_date": plan["ann"],
                       "params": plan["params"],
                       "meta": {"notes": plan["notes"], "unsupported": plan.get("unsupported", []), "key": plan["key"]}})
    target = next((t for t in C1.TARGETS if t["nid"] == nid), None)
    if target is None:
        raise KeyError(f"{nid}: 파라미터 시트가 없는 공고(템플릿 원본·손으로 만든 공고는 {BASE_NOTICES})")
    overrides = {cid.split("-", 1)[1]: q for (n, cid), q in C1.OVERRIDES.items() if n == nid}
    return _plain({
        "notice_id": nid, "template": "lh.happy_housing", "issuer": "LH",
        "program": "행복주택" if target["template"] == "N3" else "행복주택(신혼희망타운)",
        "title": target["title"], "announcement_date": target["ann"],
        "params": {"base": target["template"], "layers": target["layers"], "marriage": target.get("marriage"),
                   "child": target.get("child"), "region": target.get("region", {}), "overrides": overrides,
                   "extra_layers": C3.PLAN.get(nid, {}), "weak": C5A.PLAN.get(nid)},
        "meta": {"notes": target["notes"], "unsupported": target["unsupported"], "pdf": target["pdf"],
                 "review_note": target.get("review_note")}})


def sheet_ids() -> List[str]:
    from rule_data import notice_ids
    return [n for n in notice_ids() if n not in BASE_NOTICES]


def build(sheet: Dict, pdf: Path, pages: Optional[List[str]] = None) -> Tuple[Dict, List[str]]:
    """파라미터 시트 + 원문 PDF → 공고 규칙 문서와 찾지 못한 인용문 목록(기존 생성 스크립트로 만든다)."""
    pdf = Path(pdf)
    pages = pages if pages is not None else sv.extract_pages(pdf)
    nid, tname, params = sheet["notice_id"], sheet["template"], copy.deepcopy(sheet["params"])
    meta = sheet.get("meta", {})
    if tname == "lh.happy_housing":
        target = dict(nid=nid, pdf=str(pdf), title=sheet["title"], ann=sheet["announcement_date"], template=params["base"],
                      layers=params["layers"], marriage=params["marriage"], child=params["child"],
                      region=params["region"], overrides=params["overrides"], notes=meta.get("notes", []),
                      unsupported=meta.get("unsupported", []), review_note=meta.get("review_note"))
        doc, missing = C1.build(target)
        if params["extra_layers"]:
            missing += C3.apply_layers(doc, nid, params["extra_layers"], pages)
        if params["weak"]:
            missing += C5A.apply_weak(doc, nid, params["weak"], pages)
        return doc, missing
    spec = TEMPLATES[tname]
    plan = dict(nid=nid, title=sheet["title"], ann=sheet["announcement_date"], program=sheet["program"],
                notes=meta.get("notes", []), unsupported=meta.get("unsupported", []),
                template=spec["builder"], params=params)
    return spec["module"].make_doc(plan, pdf, pages)


def pdf_of(nid: str) -> Path:
    return sv.pdf_path(nid)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--export")
    a = ap.parse_args(argv)
    bad = 0
    for nid in sheet_ids():
        sheet = gold_sheet(nid)
        if a.export:
            out = Path(a.export)
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{nid}.json").write_text(json.dumps(sheet, ensure_ascii=False, indent=2), encoding="utf-8")
        if a.check:
            doc, missing = build(sheet, pdf_of(nid))
            same = doc == sv.notice_doc(nid)
            bad += (not same) or bool(missing)
            print(nid, sheet["template"], "같음" if same else "다름", "MISSING", len(missing))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
