"use client";
// 회원가입 — 이메일 + 비밀번호 + 필수 동의 3개(이용약관·개인정보 수집·이용·국외 이전) → 메일로 받은 6자리 인증 코드 입력.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import AuthCard, { Field, input, primary } from "@/components/AuthCard";
import { AccountError, signupStart, signupVerify } from "@/lib/account";

const CONSENTS: [string, React.ReactNode][] = [
  ["terms", <>이용약관에 동의합니다(<Link href="/terms" target="_blank" className="underline">보기</Link>)</>],
  ["privacy", <>개인정보 수집·이용에 동의합니다(<Link href="/privacy" target="_blank" className="underline">보기</Link>)</>],
  ["overseas", <>개인정보 국외 이전(데이터베이스가 싱가포르에 있음)에 동의합니다(<Link href="/privacy#overseas" target="_blank" className="underline">보기</Link>)</>],
];

export default function Signup() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [agree, setAgree] = useState<Record<string, boolean>>({});
  const [sent, setSent] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const all = CONSENTS.every(([k]) => agree[k]);

  async function start(e: React.FormEvent) {
    e.preventDefault();
    if (password !== password2) return setError("비밀번호 확인이 맞지 않습니다.");
    setBusy(true); setError("");
    try {
      await signupStart(email, password, agree);
      setSent(true);
    } catch (err) {
      setError((err as AccountError).message);
    } finally { setBusy(false); }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      await signupVerify(email, code);
      router.push("/me");
      router.refresh();
    } catch (err) {
      setError((err as AccountError).message);
    } finally { setBusy(false); }
  }

  return (
    <AuthCard title="회원가입">
      {!sent ? (
        <form onSubmit={start} className="space-y-4" data-testid="signup-form">
          <Field label="이메일"><input className={input} type="email" required value={email} autoComplete="email"
            onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label="비밀번호" hint="8자 이상, 영문과 숫자를 함께"><input className={input} type="password" required minLength={8}
            autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <Field label="비밀번호 확인"><input className={input} type="password" required value={password2} autoComplete="new-password"
            onChange={(e) => setPassword2(e.target.value)} /></Field>
          <fieldset className="space-y-2 rounded-md bg-slate-50 p-3 text-sm">
            <label className="flex items-center gap-2 font-medium">
              <input type="checkbox" checked={all}
                onChange={(e) => setAgree(Object.fromEntries(CONSENTS.map(([k]) => [k, e.target.checked])))} />
              모두 동의(필수)
            </label>
            {CONSENTS.map(([k, label]) => (
              <label key={k} className="flex items-start gap-2 pl-4 text-slate-700">
                <input type="checkbox" className="mt-1" checked={!!agree[k]} onChange={(e) => setAgree({ ...agree, [k]: e.target.checked })} />
                <span>[필수] {label}</span>
              </label>
            ))}
          </fieldset>
          <button className={primary} disabled={busy || !all}>{busy ? "보내는 중…" : "인증 코드 받기"}</button>
        </form>
      ) : (
        <form onSubmit={verify} className="space-y-4" data-testid="signup-code">
          <p className="text-sm text-slate-700"><b>{email}</b>로 6자리 인증 코드를 보냈습니다. 10분 안에 입력해 주세요.</p>
          <Field label="인증 코드"><input className={input} inputMode="numeric" pattern="\d{6}" maxLength={6} required value={code}
            autoComplete="one-time-code" onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} /></Field>
          <button className={primary} disabled={busy || code.length !== 6}>{busy ? "확인 중…" : "가입 완료"}</button>
          <button type="button" className="w-full text-sm text-slate-600 underline" onClick={() => { setSent(false); setCode(""); }}>
            이메일을 다시 입력하거나 코드를 다시 받기
          </button>
        </form>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      <p className="mt-4 text-sm text-slate-600">이미 가입했나요? <Link href="/login" className="underline">로그인</Link></p>
    </AuthCard>
  );
}
