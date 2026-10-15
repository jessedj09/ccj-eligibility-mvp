"""C1: 행복주택 5건(N4~N8)을 N1/N3 템플릿에서 생성한다. 사용: python tools/gen_c1_notices.py [N4 ...]

- 템플릿 조건을 복제하고, 각 인용문이 대상 PDF의 몇 쪽에 있는지 자동으로 찾는다(계층 대표 문구가 있는 쪽 근처 우선).
- 대상 공고의 표현이 다른 인용문은 OVERRIDES에 원문 문구를 적는다. 찾지 못한 문구는 MISSING으로 보고한다.
- 혼인 7년·6세 이하 기준일: 원문 날짜가 있으면 리터럴, 없으면 LH 관행 공식 + source.derivation.
- 생성 후 반드시 python tools/verify_sources.py 와 pytest(템플릿 동등성 test_c1_notices.py)로 확인한다.
"""
import copy
import re
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import source_verify as sv  # noqa: E402

from pypdf import PdfReader  # noqa: E402
import logging  # noqa: E402
logging.disable(logging.CRITICAL)

TARGETS = [
    dict(nid="N4", pdf="sample_lh/★하남감일위례행복주택예비입주자모집공고문(‘26.10.01.공고).pdf",
         title="하남감일·위례 행복주택", ann="2026-10-01", template="N3", layers=["신혼부부", "한부모"],
         marriage=None, child="2019-10-02",
         unsupported=[{"name": "신혼부부·한부모 주거약자용", "page": 7,
                       "note": "주거약자용 주택형(고령자·장애인·국가유공자 등 추가요건) — 주택형 축 구현 후 지원 예정"}],
         notes=["우선공급은 없고 일반공급만 모집한다(p.1)."]),
    dict(nid="N5", pdf="sample_lh/붙임_부천영상지역전략산업지원행복주택예비입주자모집공고문(2026.08.18.).pdf",
         title="부천영상 지역전략산업지원 행복주택", ann="2026-08-18", template="N3", layers=["대학생", "청년"],
         unsupported=[{"name": "지역전략산업종사자", "page": 6,
                       "note": "선순위 계층. 종사자 자격은 부천시가 신청 후 확인·추천 — 새 계층 구현 후 지원 예정"},
                      {"name": "주거약자(26A1/B1형)", "page": 11,
                       "note": "지역전략산업종사자·청년·대학생 자격 + 주거약자 요건 — 주택형 축 구현 후 지원 예정"}],
         notes=["대학생·청년은 후순위 계층으로, 지역전략산업종사자에게 먼저 공급하고 남은 세대에만 공급한다(p.1-2). "
                "자격이 있어도 공급이 보장되지 않는다."]),
    dict(nid="N6", pdf="sample_lh/서울금천행복주택(산업단지형)예비입주자모집(2026.05.15).pdf",
         title="서울금천 행복주택(산업단지형)", ann="2026-05-15", template="N3",
         layers=["대학생", "청년", "신혼부부", "한부모"], marriage=None, child="2019-05-16",
         unsupported=[{"name": "산업단지근로자", "page": 5, "note": "새 계층 구현 후 지원 예정"},
                      {"name": "고령자", "page": 13, "note": "새 계층 구현 후 지원 예정"}],
         notes=["대학생·청년·신혼부부·한부모는 산업단지근로자를 순위에 따라 선정한 뒤 남은 물량으로 추첨한다(p.7).",
                "같은 날 공고된 서울오류 행복주택과 중복 신청할 수 없다(중복 시 모두 무효, p.1)."]),
    dict(nid="N7", pdf="sample_lh/서울대방신혼희망타운행복주택입주자공고문(정정).pdf",
         title="서울대방 신혼희망타운 행복주택", ann="2026-06-29", template="N1", layers=["신혼부부", "한부모"],
         marriage="2019-06-29", child="2019-06-30",
         unsupported=[{"name": "신혼부부·한부모 주거약자용", "page": 7,
                       "note": "주거약자용 주택형 — 주택형 축 구현 후 지원 예정"}],
         review_note="파일명이 '(정정)'이지만 본문에 정정 표시가 없어 무엇이 정정됐는지 확인하지 못했다(최초 공고 확보 필요).",
         notes=["우선공급(영등포구 등) 자격이 없으면 일반공급으로 넘어가지 않는다(p.7) — 이 판정은 일반공급 자격 기준이다."]),
    dict(nid="N8", pdf="sample_lh/의왕청계2_A1블록_신혼희망타운_행복주택_입주자모집공고문.pdf",
         title="의왕청계2 A1블록 신혼희망타운 행복주택", ann="2026-09-29", template="N1",
         layers=["신혼부부", "한부모"], marriage=None, child=None,
         unsupported=[{"name": "신혼부부·한부모 주거약자용", "page": 8,
                       "note": "주거약자용 주택형 — 주택형 축 구현 후 지원 예정"}],
         notes=["우선공급(의왕시 거주) 자격이 없으면 일반공급으로 넘어가지 않는다(p.7) — 이 판정은 일반공급 자격 기준이다."]),
]

# 템플릿 인용문 대신 쓸 대상 공고의 원문 문구(표현이 다른 곳). 쪽은 자동 탐색.
NO_OWN = "'무주택자'란 주택을 소유하고 있지 않은 자를 말함(세대 내 다른 구성원이 주택을 소유해도 신청 가능함)"
OVERRIDES = {
    ("N5", "N5-R5"): ["무주택자로서 아래의 요건", NO_OWN],
    ("N7", "N7-S-child6"): ["(한부모가족) 6세이하(2019.6.30. 이후 출생, 태아포함) 자녀를 둔 한부모인 자"],
    ("N8", "N8-M-duration"): ["혼인기간이 7년 이내(전 배우자였던 사람과 재혼하는 경우 이전 혼인기간 포함)일 것 또는 "
                              "6세 이하 자녀(태아포함)를 둔 자"],
    ("N8", "N8-S-child6"): ["(한부모가족) 6세이하 자녀를 둔 한부모인 자(태아포함)"],
}

# 각 계층의 위치를 잡는 대표 문구(이 문구가 있는 쪽 근처에서 인용문을 찾는다)
ANCHORS = {"대학생": "재학중이거나다음학기에입학또는복학예정일것", "청년": "19세이상39세이하인자",
           "신혼부부": "(신혼부부)혼인중인자", "한부모": "(한부모가족)6세이하"}
DERIV_FN = ("원문이 컷오프 날짜를 적지 않아 LH 관행 공식(혼인 = 공고일−7년 당일, 6세 이하 = 공고일−7년의 다음 날)으로 "
            "공고일에서 도출한다. 이 공식은 LH 공고 N1(2026.7.29)·N7(2026.6.29)의 리터럴 날짜와 일치한다.")


def pages_of(pages, text):
    t = sv.normalize(text)
    return [i + 1 for i, p in enumerate(pages) if t in p]


def pick(found, anchor):
    if not found:
        return None
    return min(found, key=lambda p: (abs(p - anchor), p < anchor))


def relocate(source, pages, anchor, where, missing):
    """source.quote의 각 문구를 대상 PDF에서 찾아 쪽을 다시 매긴다."""
    quotes = []
    first = None
    for q in source.get("quote", []):
        text = q["text"] if isinstance(q, dict) else q
        hint = q["page"] if isinstance(q, dict) else anchor
        p = pick(pages_of(pages, text), hint if isinstance(q, dict) else anchor)
        if p is None:
            missing.append(f"{where}: '{text}'")
            continue
        if first is None:
            first = p
            quotes.append(text)
        elif p == first:
            quotes.append(text)
        else:
            quotes.append({"page": p, "text": text})
    new = {k: v for k, v in source.items() if k != "quote"}
    new["page"] = first if first is not None else anchor
    new["quote"] = quotes
    if "clause" in new:
        # 템플릿 조항 표기에 붙은 쪽 참조(예: "③(+가산표)", "(본인 검증은 p.3)")는 대상 공고와 다를 수 있어 뗀다
        base = new["clause"].split(",")[0].split("(")[0].strip()
        new["clause"] = base or new["clause"].split(";")[0].strip(" ()") or new["clause"]
    return new


def build(t):
    tpl = json.loads((ROOT / "rules" / "notices" / f"{t['template']}.json").read_text(encoding="utf-8"))
    pdf = ROOT / t["pdf"]
    pages = [sv.normalize(p.extract_text() or "") for p in PdfReader(str(pdf)).pages]
    missing = []
    doc = {
        "notice_id": t["nid"], "title": t["title"], "announcement_date": t["ann"],
        "issuer": "LH", "program": "행복주택" if t["template"] == "N3" else "행복주택(신혼희망타운)",
        "version": 1, "valid_from": t["ann"], "supersedes": None,
        "source": {"document": pdf.name, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                   "pages": len(pages)},
        "review": {"status": "DRAFT",
                   "note": f"{t['template']} 템플릿에서 생성(C1). 인용문 쪽수는 원문 대조 도구로 확인. 독립 검토 전."
                           + (" " + t["review_note"] if t.get("review_note") else ""),
                   "log": []},
        "notes": t["notes"],
        "unsupported_layers": t["unsupported"],
        "tables": {}, "layers": {},
    }
    used_tables = set()
    anchors = {}
    for layer in t["layers"]:
        anchor = pick(pages_of(pages, ANCHORS[layer]), 1) or 1
        anchors[layer] = anchor
        conds = []
        for c in tpl["layers"][layer]["conditions"]:
            c = copy.deepcopy(c)
            c["id"] = c["id"].replace(t["template"] + "-", t["nid"] + "-", 1)
            if (t["nid"], c["id"]) in OVERRIDES:
                c["source"]["quote"] = list(OVERRIDES[(t["nid"], c["id"])])
            elif c["id"].endswith(("-duration", "-child6")):
                # 템플릿(N1)의 날짜 문구는 대상 공고 날짜로 바꿔 넣으므로 탐색 대상에서 뺀다
                c["source"]["quote"] = [q for q in c["source"]["quote"]
                                        if "2019" not in (q["text"] if isinstance(q, dict) else q)]
            c["source"] = relocate(c["source"], pages, anchor, f"{layer}/{c['id']}", missing)
            if "table" in c:
                used_tables.add((c["table"], layer))
            cid = c["id"]
            dv = c["source"].get("derivation")
            if dv and "정부 지침" in dv:
                # 템플릿 공고의 쪽 참조(N1 p.5 / N3 p.9)를 이 공고의 해당 조항 쪽으로 바꾼다
                c["source"]["derivation"] = re.sub(r"명시: [^)]*\)", f"명시: 이 공고 p.{c['source']['page']} ③④)", dv)
            if cid.endswith("-duration") or cid.endswith("-child6"):
                c = cutoffs(c, t, pages, anchor, missing)
            conds.append(c)
        doc["layers"][layer] = {"conditions": conds}
    for name, layer in sorted(used_tables):
        if name in doc["tables"]:
            continue
        td = copy.deepcopy(tpl["tables"][name])
        td["source"] = relocate(td["source"], pages, anchors[layer], f"table:{name}", missing)
        td["label"] = re.sub(r"(N\d )?p\.\d+(-\d+)? ?", "", td["label"]).replace("( ", "(").replace("()", "").strip()
        doc["tables"][name] = td
    return doc, missing


def cutoffs(c, t, pages, anchor, missing):
    """혼인 7년·6세 이하 컷오프: 원문 리터럴이 있으면 날짜 리터럴, 없으면 LH 공식 + derivation."""
    lit_m, lit_c = t.get("marriage"), t.get("child")
    s = json.dumps(c["check"], ensure_ascii=False)
    s = s.replace('{"fn": "marriage_cutoff"}', json.dumps({"date": lit_m}) if lit_m else '{"fn": "marriage_cutoff"}')
    s = s.replace('{"fn": "young_child_cutoff"}', json.dumps({"date": lit_c}) if lit_c else '{"fn": "young_child_cutoff"}')
    # N1 템플릿의 날짜 리터럴 → 대상 공고 리터럴(없으면 공식)
    s = s.replace('{"date": "2019-07-29"}', json.dumps({"date": lit_m}) if lit_m else '{"fn": "marriage_cutoff"}')
    s = s.replace('{"date": "2019-07-30"}', json.dumps({"date": lit_c}) if lit_c else '{"fn": "young_child_cutoff"}')
    c["check"] = json.loads(s)
    # 인용문: 템플릿의 날짜 문구(N1 날짜)는 버리고 대상 원문의 날짜 문구를 찾아 넣는다
    keep = [q for q in c["source"]["quote"]
            if "2019" not in (q["text"] if isinstance(q, dict) else q)]
    c["source"]["quote"] = keep
    for lit, suffix in ((lit_m, "이후혼인신고"), (lit_c, "이후출생")):
        if not lit:
            continue
        y, m, d = (int(x) for x in lit.split("-"))
        for cand in (f"{y}.{m}.{d}.{suffix}", f"{y}.{m:02d}.{d:02d}.{suffix}"):
            found = pages_of(pages, cand)
            if found:
                p = pick(found, anchor)
                c["source"]["quote"].append(cand if p == c["source"]["page"] else {"page": p, "text": cand})
                break
        else:
            missing.append(f"{c['id']}: 날짜 문구 {lit} {suffix}")
    c["source"].pop("derivation", None)   # 템플릿의 컷오프 도출 설명(N3 기준)은 대상 공고에 맞지 않는다
    if (lit_m is None and "marriage_cutoff" in s) or (lit_c is None and "young_child_cutoff" in s):
        c["source"]["derivation"] = DERIV_FN
    return c


if __name__ == "__main__":
    only = sys.argv[1:]
    for t in TARGETS:
        if only and t["nid"] not in only:
            continue
        doc, missing = build(t)
        out = ROOT / "rules" / "notices" / f"{t['nid']}.json"
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(t["nid"], t["title"], "layers", list(doc["layers"]), "MISSING", len(missing))
        for m in missing:
            print("   -", m)
