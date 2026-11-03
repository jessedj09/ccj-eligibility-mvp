# -*- coding: utf-8 -*-
"""mailer.py — 인증 코드 메일 발송(바꿔 끼울 수 있게). CCJ_MAIL_BACKEND로 고른다.

- resend: Resend HTTP API(RESEND_API_KEY, 보내는 주소 CCJ_MAIL_FROM — 도메인 인증 전에는 Resend 계정 본인 주소로만 보내진다).
  도메인은 베타 전에 사서 인증한다(2026-11-03 사용자 결정).
- console: 서버 표준 출력에 메일 내용을 찍는다 — 로컬 개발 전용. 운영(Render)에서는 쓰지 않는다(인증 코드가 로그에 남는다).
- memory: 시험용(보낸 메일을 outbox에 모은다).
- 설정이 없으면 NoMailer — 가입·비밀번호 재설정이 503으로 멈춘다(메일 없이 계정을 만들지 않는다).
"""
import json
import os
import urllib.request
from typing import List, Tuple


class MailUnavailable(Exception):
    pass


class NoMailer:
    def send(self, to: str, subject: str, text: str) -> None:
        raise MailUnavailable("메일 발송이 설정되지 않았습니다(CCJ_MAIL_BACKEND).")


class MemoryMailer:
    def __init__(self):
        self.outbox: List[Tuple[str, str, str]] = []

    def send(self, to: str, subject: str, text: str) -> None:
        self.outbox.append((to, subject, text))


class ConsoleMailer:
    def send(self, to: str, subject: str, text: str) -> None:
        print(f"[mail:console] to={to} subject={subject}\n{text}", flush=True)


class ResendMailer:
    URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, sender: str):
        self.api_key, self.sender = api_key, sender

    def send(self, to: str, subject: str, text: str) -> None:
        body = json.dumps({"from": self.sender, "to": [to], "subject": subject, "text": text}).encode("utf-8")
        req = urllib.request.Request(self.URL, data=body, method="POST",
                                     headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status >= 300:
                    raise MailUnavailable(f"메일 발송 실패({r.status})")
        except OSError as e:
            raise MailUnavailable(f"메일 발송 실패: {type(e).__name__}") from None


def mailer_from_env():
    kind = os.environ.get("CCJ_MAIL_BACKEND", "").strip().lower()
    if kind == "resend":
        key, sender = os.environ.get("RESEND_API_KEY", "").strip(), os.environ.get("CCJ_MAIL_FROM", "").strip()
        return ResendMailer(key, sender) if key and sender else NoMailer()
    if kind == "console":
        return ConsoleMailer()
    return NoMailer()
