# -*- coding: utf-8 -*-
"""PDF 추출 텍스트 캐시(src/source_verify.py) — 캐시를 써도 대조 결과가 같아야 한다."""
import source_verify as sv


def test_cached_text_equals_fresh_extraction(monkeypatch, tmp_path):
    pdf = sv.pdf_path("N2")
    monkeypatch.setattr(sv, "PDF_CACHE", tmp_path)
    fresh = sv.extract_pages(pdf)                       # 추출하고 캐시에 쓴다
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert sv.extract_pages(pdf) == fresh               # 캐시에서 읽는다
    monkeypatch.setenv("CCJ_NO_PDF_CACHE", "1")
    assert sv.extract_pages(pdf) == fresh               # 캐시를 끄고 다시 추출


def test_cache_key_changes_with_content_and_extractor(monkeypatch):
    a = sv._cache_key(b"pdf-a")
    assert a != sv._cache_key(b"pdf-b")
    import pypdf
    monkeypatch.setattr(pypdf, "__version__", "0.0-test")
    assert sv._cache_key(b"pdf-a") != a


def test_broken_cache_file_is_ignored(monkeypatch, tmp_path):
    pdf = sv.pdf_path("N2")
    monkeypatch.setattr(sv, "PDF_CACHE", tmp_path)
    (tmp_path / f"{sv._cache_key(pdf.read_bytes())}.json").write_text("{깨진", encoding="utf-8")
    assert sv.extract_pages(pdf) == sv.pdf_pages("N2")
