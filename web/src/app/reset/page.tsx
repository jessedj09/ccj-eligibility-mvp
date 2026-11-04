"use client";
// 비밀번호 재설정 — 이메일로 받은 6자리 인증 코드 + 새 비밀번호. 다른 기기의 로그인은 끊긴다.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import AuthCard, { Field, input, primary } from "@/components/AuthCard";
import { AccountError, resetStart, resetVerify } from "@/lib/account";

export default function Reset() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function start(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try { await resetStart(email); setSent(true); } catch (err) { setError((err as AccountError).message); } finally { setBusy(false); }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      await resetVerify(email, code, password);
      router.push("/me");
      router.refresh();
    } catch (err) { setError((err as AccountError).message); } finally { setBusy(false); }
  }

  return (
    <AuthCard title="비밀번호 재설정">
      {!sent ? (
        <form onSubmit={start} className="space-y-4">
          <Field label="가입한 이메일"><input className={input} type="email" required value={email} autoComplete="email"
            onChange={(e) => setEmail(e.target.value)} /></Field>
          <button className={primary} disabled={busy}>{busy ? "보내는 중…" : "인증 코드 받기"}</button>
        </form>
      ) : (
        <form onSubmit={verify} className="space-y-4">
          <p className="text-sm text-slate-700">가입된 이메일이면 6자리 인증 코드를 보냈습니다. 10분 안에 입력해 주세요.</p>
          <Field label="인증 코드"><input className={input} inputMode="numeric" maxLength={6} required value={code}
            autoComplete="one-time-code" onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} /></Field>
          <Field label="새 비밀번호" hint="8자 이상, 영문과 숫자를 함께"><input className={input} type="password" required minLength={8}
            autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <button className={primary} disabled={busy || code.length !== 6}>{busy ? "바꾸는 중…" : "비밀번호 바꾸기"}</button>
        </form>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      <p className="mt-4 text-sm text-slate-600"><Link href="/login" className="underline">로그인으로 돌아가기</Link></p>
    </AuthCard>
  );
}
