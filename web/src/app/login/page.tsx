"use client";
// 로그인 — 이메일 + 비밀번호. 로그인하면 원래 보던 화면(?next=)으로 돌아간다.
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import AuthCard, { Field, input, primary } from "@/components/AuthCard";
import { AccountError, login, nextPath } from "@/lib/account";

function LoginForm() {
  const router = useRouter();
  const next = nextPath(useSearchParams().get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      await login(email, password);
      router.push(next);
      router.refresh();
    } catch (err) {
      setError((err as AccountError).message);
    } finally { setBusy(false); }
  }

  return (
    <AuthCard title="로그인">
      <form onSubmit={submit} className="space-y-4" data-testid="login-form">
        <Field label="이메일"><input className={input} type="email" required value={email} autoComplete="email"
          onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="비밀번호"><input className={input} type="password" required value={password} autoComplete="current-password"
          onChange={(e) => setPassword(e.target.value)} /></Field>
        <button className={primary} disabled={busy}>{busy ? "확인 중…" : "로그인"}</button>
      </form>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      <div className="mt-4 flex justify-between text-sm text-slate-600">
        <Link href="/reset" className="underline">비밀번호를 잊었어요</Link>
        <Link href="/signup" className="underline">회원가입</Link>
      </div>
    </AuthCard>
  );
}

export default function Login() {
  return <Suspense><LoginForm /></Suspense>;
}
