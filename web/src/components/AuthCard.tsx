// 회원가입·로그인·비밀번호 재설정 화면의 공통 틀과 입력란.
import type { ReactNode } from "react";

export const input = "w-full rounded-md border border-slate-300 px-3 py-2 text-base sm:text-sm";
export const primary = "w-full rounded-md bg-blue-700 py-2.5 font-semibold text-white hover:bg-blue-800 disabled:opacity-50";

export default function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mx-auto max-w-md">
      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="mb-4 text-xl font-bold">{title}</h1>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}
