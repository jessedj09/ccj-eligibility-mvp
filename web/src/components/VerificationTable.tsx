"use client";
// 사업별 검증 상태(R-⑤, 2026-11-14) — 새 공고 자동 판정 사업마다 '독립 검증 완료 / 검증 중 / 정확도 점검 중'.
// 판정 틀이 있으면 판정하고(공개 원칙), 그 판정 방식이 사람의 독립 판단과 얼마나 대조됐는지만 보여 준다. 상태는 API가 계산.
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

type Program = { template: string; program: string; status: string; label: string; note: string };

const TONE: Record<string, string> = {
  verified: "text-green-800",
  in_progress: "text-slate-700",
  paused: "text-amber-800",
};

export default function VerificationTable() {
  const [rows, setRows] = useState<Program[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    fetch(`${API_BASE}/verification`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((j) => setRows(j.programs))
      .catch(() => setFailed(true));
  }, []);
  if (failed) return <p className="text-xs text-slate-500">검증 상태를 불러오지 못했습니다. 잠시 뒤 다시 열어 주세요.</p>;
  if (!rows) return <p className="text-xs text-slate-500">검증 상태를 불러오는 중…</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[22rem] text-left text-sm" data-testid="verification-table">
        <thead className="border-b border-slate-200 text-xs text-slate-500">
          <tr>
            <th className="py-1.5 pr-3 font-medium">새 공고 자동 판정 사업</th>
            <th className="py-1.5 font-medium">검증 상태</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.template} className="border-b border-slate-100 align-top">
              <td className="py-1.5 pr-3">{p.program}</td>
              <td className={`py-1.5 ${TONE[p.status] ?? ""}`}>{p.label}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
