import type { Metadata } from "next";
import Link from "next/link";
import AccountNav from "@/components/AccountNav";
import ServerWaking from "@/components/ServerWaking";
import "./globals.css";

const SERVICE = "청약 포청천";
const TAGLINE = "청약 지원자격 판정 AI";

export const metadata: Metadata = {
  title: `${SERVICE} — ${TAGLINE}`,
  description: "LH·SH 입주자모집공고문 원문을 근거로 청약 지원 자격을 판정합니다.",
};

// 상단 대표 메뉴 — 이름과 하는 일(이모지 없이 텍스트만, 2026-11-01 결정). '내 조건 등록하기'는 회원가입·로그인과 함께 연다(2026-11-03).
const MENU = [
  { href: "/", label: "재판소", desc: "공고문 올리고 지원 자격 판정" },
  { href: "/find", label: "청약 흥신소", desc: "나에게 맞는 지원 가능 공고" },
  { href: "/me", label: "내 조건 등록하기", desc: "내 조건 저장·관리(로그인)" },
];

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3 sm:px-8 sm:py-4">
            <Link href="/" className="flex items-baseline gap-2" aria-label={`${SERVICE} — ${TAGLINE}`}>
              <span className="text-lg font-bold text-blue-800">{SERVICE}</span>
              <span className="hidden text-xs text-slate-500 sm:inline">{TAGLINE}</span>
            </Link>
            <nav className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm sm:gap-x-7" aria-label="대표 메뉴">
              {MENU.map((m) => (
                <Link key={m.href} href={m.href} title={m.desc} className="group text-slate-700 hover:text-blue-700"
                  data-testid={m.href === "/me" ? "menu-profile" : undefined}>
                  <span className="font-medium">{m.label}</span>
                  <span className="ml-1.5 hidden text-xs text-slate-500 group-hover:text-blue-600 lg:inline">{m.desc}</span>
                </Link>
              ))}
            </nav>
            <div className="ml-auto"><AccountNav /></div>
          </div>
        </header>
        <ServerWaking />
        <div className="mx-auto max-w-7xl px-4 py-5 sm:px-8 sm:py-8">{children}</div>
        <footer className="mx-auto max-w-7xl px-4 pb-10 text-xs text-slate-500 sm:px-8">
          판정 근거는 조건별로 표시한 공고문 원문입니다. 최종 자격은 공고 기관의 서류 심사로 확정됩니다. 판정에 입력한 정보는 저장하지 않고, 로그인해 저장한 내 조건만 암호화해 보관합니다.{" "}
          <Link href="/about" className="underline hover:text-blue-700">이용 안내·개인정보 처리</Link>{" · "}
          <Link href="/privacy" className="underline hover:text-blue-700">개인정보 처리방침</Link>{" · "}
          <Link href="/terms" className="underline hover:text-blue-700">이용약관</Link>
        </footer>
      </body>
    </html>
  );
}
