"use client";
// 공고문 분석 중 표시(2026-11-05 사용자 결정) — 처음 올리는 큰 공고는 서버가 PDF 글자를 읽는 데 1~2분 걸린다(속도는 그대로, 기다림을 보이게).
// 서버는 진행률을 알려 주지 않으므로 막대는 파일 크기로 어림한 '예상' 진행이다 — 끝나기 전에는 95%에서 멈추고, 결과가 오면 사라진다.
import { useEffect, useState } from "react";

const STAGES: [number, string][] = [
  [0, "파일을 보내는 중"],
  [0.08, "공고문 글자를 읽는 중"],
  [0.55, "어떤 공고인지 알아보는 중"],
  [0.75, "신청 자격 조건을 원문과 대조하는 중"],
];

/** 예상 소요(초) — 파일 크기로 어림(처음 올리는 공고 기준, 같은 공고를 다시 올리면 바로 끝난다) */
export function estimateSeconds(bytes: number): number {
  const mb = bytes / 1024 / 1024;
  return Math.min(150, Math.max(15, 10 + mb * 30));
}

export default function UploadProgress({ bytes }: { bytes: number }) {
  const [s, setS] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setS((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const est = estimateSeconds(bytes);
  const frac = Math.min(0.95, 1 - Math.exp((-2 * s) / est));     // 예상 시간에 약 86%, 끝나기 전에는 95%를 넘지 않음
  const stage = [...STAGES].reverse().find(([at]) => frac >= at)?.[1] ?? STAGES[0][1];
  const pct = Math.round(frac * 100);
  return (
    <div className="rounded-md border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900" role="status" aria-live="polite"
      data-testid="busy">
      <div className="flex items-center gap-3">
        <span className="spinner inline-block h-5 w-5 shrink-0 rounded-full border-2 border-blue-300 border-t-blue-700" aria-hidden="true" />
        <span className="font-medium" data-testid="upload-stage">공고문을 읽고 분석하는 중입니다… {stage}</span>
        <span className="ml-auto tabular-nums text-blue-700">{s}초</span>
      </div>
      <div className="mt-3 h-2 w-full overflow-hidden rounded bg-blue-100" role="progressbar" aria-label="분석 진행(예상)"
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} data-testid="upload-progress">
        <div className="h-2 rounded bg-blue-600 transition-[width] duration-1000 ease-linear" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-xs text-blue-800">
        처음 올리는 큰 공고는 1~2분 걸릴 수 있습니다(예상 약 {Math.round(est)}초). 같은 공고를 다시 올리면 바로 나옵니다. 이 화면을 닫지 말고 기다려 주세요.
      </p>
    </div>
  );
}
