"use client";
// 상단 로그인 상태 — 로그인했으면 이메일·로그아웃, 아니면 로그인·회원가입.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getMe, logout } from "@/lib/account";

export default function AccountNav() {
  const [email, setEmail] = useState<string | null | undefined>(undefined);
  const path = usePathname();
  const router = useRouter();

  useEffect(() => {
    getMe().then((m) => setEmail(m?.email ?? null)).catch(() => setEmail(null));
  }, [path]);

  if (email === undefined) return null;
  if (!email) {
    return (
      <span className="flex items-center gap-3 text-sm" data-testid="account-nav">
        <Link href={`/login?next=${encodeURIComponent(path || "/")}`} className="text-slate-700 hover:text-blue-700">로그인</Link>
        <Link href="/signup" className="rounded-md border border-blue-700 px-2.5 py-1 text-blue-700 hover:bg-blue-50">회원가입</Link>
      </span>
    );
  }
  return (
    <span className="flex items-center gap-3 text-sm" data-testid="account-nav">
      <span className="hidden text-slate-500 sm:inline" title="로그인한 계정">{email}</span>
      <button type="button" className="text-slate-700 hover:text-blue-700"
        onClick={async () => { await logout().catch(() => null); setEmail(null); router.push("/"); router.refresh(); }}>
        로그아웃
      </button>
    </span>
  );
}
