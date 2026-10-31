import type { Metadata } from "next";
import Link from "next/link";
import ServerWaking from "@/components/ServerWaking";
import "./globals.css";

export const metadata: Metadata = {
  title: "공공주택 자격 판정",
  description: "LH·SH 공고문 원문을 근거로 공공주택 신청 자격을 판정합니다.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3 sm:px-8 sm:py-4">
            <Link href="/" className="text-lg font-bold text-blue-800">공공주택 자격 판정</Link>
            <nav className="flex gap-5 text-sm sm:gap-6">
              <Link href="/" className="text-slate-700 hover:text-blue-700">공고 판정</Link>
              <Link href="/find" className="text-slate-700 hover:text-blue-700">내 조건으로 공고 찾기</Link>
            </nav>
          </div>
        </header>
        <ServerWaking />
        <div className="mx-auto max-w-7xl px-4 py-5 sm:px-8 sm:py-8">{children}</div>
        <footer className="mx-auto max-w-7xl px-4 pb-10 text-xs text-slate-500 sm:px-8">
          판정 근거는 조건별로 표시한 공고문 원문입니다. 최종 자격은 공고 기관의 서류 심사로 확정됩니다. 입력한 정보는 저장하지 않습니다.
        </footer>
      </body>
    </html>
  );
}
