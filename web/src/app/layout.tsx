import type { Metadata } from "next";
import Link from "next/link";
import ServerWaking from "@/components/ServerWaking";
import "./globals.css";

const SERVICE = "청약 포청천";
const TAGLINE = "청약 지원자격 판정 AI";

export const metadata: Metadata = {
  title: `${SERVICE} — ${TAGLINE}`,
  description: "LH·SH 입주자모집공고문 원문을 근거로 청약 지원 자격을 판정합니다.",
};

// 상단 대표 메뉴 — 이름(아이콘)과 하는 일. '내 조건 등록하기'는 회원가입·로그인 기능을 붙인 뒤 연다(2026-11-01 결정).
const MENU = [
  { href: "/", icon: "⚖️", label: "재판소", desc: "공고문 올리고 지원 자격 판정" },
  { href: "/find", icon: "📜", label: "청약 흥신소", desc: "나에게 맞는 지원 가능 공고" },
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
                <Link key={m.href} href={m.href} title={m.desc} className="group text-slate-700 hover:text-blue-700">
                  <span className="font-medium">{m.icon} {m.label}</span>
                  <span className="ml-1.5 hidden text-xs text-slate-500 group-hover:text-blue-600 lg:inline">{m.desc}</span>
                </Link>
              ))}
              <span className="cursor-not-allowed text-slate-400" aria-disabled="true"
                title="회원가입·로그인 기능을 추가한 뒤 제공할 예정입니다" data-testid="menu-profile">
                내 조건 등록하기 <span className="ml-0.5 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">준비 중</span>
              </span>
            </nav>
          </div>
        </header>
        <ServerWaking />
        <div className="mx-auto max-w-7xl px-4 py-5 sm:px-8 sm:py-8">{children}</div>
        <footer className="mx-auto max-w-7xl px-4 pb-10 text-xs text-slate-500 sm:px-8">
          판정 근거는 조건별로 표시한 공고문 원문입니다. 최종 자격은 공고 기관의 서류 심사로 확정됩니다. 입력한 정보는 저장하지 않습니다.{" "}
          <Link href="/about" className="underline hover:text-blue-700">이용 안내·개인정보 처리</Link>
        </footer>
      </body>
    </html>
  );
}
