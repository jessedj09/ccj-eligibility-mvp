# -*- coding: utf-8 -*-
"""pytest가 tests/ 밖의 src/ 모듈을 import할 수 있도록 경로를 추가한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_shared_store():
    """테스트는 운영 저장소(Neon)를 건드리지 않는다 — DB 시험은 test_d4_store.py가 TEST_DATABASE_URL의 임시 스키마에서."""
    import store
    store.reset_store(store.NullStore())
    yield
    store.reset_store(store.NullStore())
