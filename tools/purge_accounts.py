# -*- coding: utf-8 -*-
"""1년 넘게 로그인하지 않은 회원 계정과 저장한 조건을 지운다(개인정보 처리방침 2절). 사용: python tools/purge_accounts.py [--dry-run]

운영 DB(DATABASE_URL 또는 .streamlit/secrets.toml)에 접속한다 — 운영자 PC나 예약 작업에서만 돌린다. 지운 수만 출력한다(이메일은 출력하지 않음).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import accounts as A  # noqa: E402
from mailer import NoMailer  # noqa: E402
from store import database_url  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="지울 계정 수만 센다")
    a = ap.parse_args(argv)
    url = database_url()
    if not url:
        print("DATABASE_URL이 없습니다.")
        return 2
    acc = A.Accounts(A.PgRepo(url), NoMailer(), None)
    if a.dry_run:
        n = len(acc.repo.inactive_users(acc.clock() - A.timedelta(days=A.INACTIVE_DAYS)))
        print(f"지울 계정 {n}개(1년 넘게 로그인하지 않음)")
        return 0
    print(f"지운 계정 {acc.purge_inactive()}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
