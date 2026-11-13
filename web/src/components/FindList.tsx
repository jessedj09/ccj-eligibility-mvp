"use client";
// 흥신소 목록 — 판정 API /find 결과를 묶음별 공고 카드로 보여 준다(판정 로직 없음).
// 묶음 순서·접힘은 서버(result.groups·collapsed)가 정한다: 지원 가능 → 지원 가능(단서) → 추가정보 요청 → 접힘: 실제 공고문 확인필요·지원 어려움·판정 안 함.
import Link from "next/link";
import { useState } from "react";
import { requestAnalysis, type FindCard, type FindGroup, type FindResult } from "@/lib/api";

const TONE: Record<FindGroup, { box: string; badge: string; icon: string }> = {
  eligible: { box: "border-green-300 bg-green-50", badge: "bg-green-700 text-white", icon: "●" },
  likely: { box: "border-green-300 bg-white", badge: "border border-green-700 text-green-800", icon: "◎" },
  needs_info: { box: "border-amber-300 bg-amber-50", badge: "bg-amber-600 text-white", icon: "▲" },
  verify: { box: "border-slate-300 bg-white", badge: "bg-slate-600 text-white", icon: "◇" },
  unlikely: { box: "border-slate-200 bg-slate-50", badge: "bg-slate-400 text-white", icon: "○" },
  unjudged: { box: "border-slate-200 bg-slate-50", badge: "bg-slate-200 text-slate-700", icon: "–" },
};
const LAYER_TEXT: Record<FindGroup, string> = {
  eligible: "지원 가능", likely: "지원 가능(단서)", needs_info: "정보 필요", verify: "공고문 확인", unlikely: "어려움", unjudged: "—",
};

function Schedule({ c }: { c: FindCard }) {
  const s = c.schedule;
  const d = s.days === null ? "" : s.code === "open" ? (s.days === 0 ? " · 오늘 마감" : ` · 마감 D-${s.days}`) : s.code === "upcoming" ? ` · 시작 D-${s.days}` : "";
  const color = s.code === "open" ? "bg-blue-100 text-blue-800" : s.code === "upcoming" ? "bg-violet-100 text-violet-800" : "bg-slate-100 text-slate-700";
  return <span className={`rounded px-1.5 py-0.5 text-xs ${color}`} data-testid="card-schedule">{s.text}{d}</span>;
}

const man = (v: number) => `${(v / 10000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}만`;
const range = (r?: [number, number]) => (r ? (r[0] === r[1] ? `${man(r[0])} 원` : `${man(r[0])}~${man(r[1])} 원`) : null);

function Info({ c }: { c: FindCard }) {
  const i = c.info;
  if (!i) return null;
  const parts = [
    i.address ? `📍 ${i.address}${i.more_addresses ? ` 외 ${i.more_addresses}곳` : ""}` : null,
    range(i.deposit) ? `보증금 ${range(i.deposit)}` : null,
    range(i.rent) ? `월 ${range(i.rent)}` : null,
    i.supply ? `공급 ${i.supply.toLocaleString("ko-KR")}세대` : null,
  ].filter(Boolean);
  if (!parts.length) return null;
  return <p className="mt-1 text-xs text-slate-600" data-testid="card-info">{parts.join(" · ")}</p>;
}

function Card({ c }: { c: FindCard }) {
  const [asked, setAsked] = useState<"" | "busy" | "done" | "fail">("");
  const t = TONE[c.result];
  async function ask() {
    setAsked("busy");
    try {
      await requestAnalysis(c.source, c.external_id);
      setAsked("done");
    } catch {
      setAsked("fail");
    }
  }
  return (
    <li className={`rounded-md border p-3 ${t.box}`} data-testid="find-card" data-result={c.result} data-basis={c.basis}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${t.badge}`} data-testid="card-label">{t.icon} {c.label}</span>
        <Schedule c={c} />
        <span className="text-xs text-slate-500">{[c.issuer, c.kind, c.region].filter(Boolean).join(" · ")}</span>
      </div>
      <div className="mt-1.5 font-medium break-keep">{c.title}</div>
      <Info c={c} />
      <p className="mt-1 text-xs text-slate-600" data-testid="card-basis">{c.basis_note}</p>
      {c.layers.length > 0 && (
        <details className="mt-2 text-sm">
          <summary className="cursor-pointer text-xs text-slate-700">계층별 결과 {c.layers.length}개</summary>
          <ul className="mt-1 space-y-1">
            {c.layers.map((l) => (
              <li key={l.layer} className="text-xs">
                <span className="font-medium">{l.layer}</span> — {LAYER_TEXT[l.result]}
                {l.reasons?.length ? <span className="text-slate-500"> ({l.reasons.join(" / ")})</span> : null}
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        {c.url && <a href={c.url} target="_blank" rel="noreferrer" className="rounded border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50">공식 공고 ↗</a>}
        {c.basis === "preview" && (
          <>
            <Link href={`/?from=${encodeURIComponent(c.title)}`} data-testid="card-upload"
              className="rounded bg-blue-700 px-2 py-1 text-white hover:bg-blue-800">공고문 올리면 바로 확정</Link>
            <button type="button" onClick={ask} disabled={asked === "busy" || asked === "done"} data-testid="card-request"
              className="rounded border border-blue-700 bg-white px-2 py-1 text-blue-700 hover:bg-blue-50 disabled:opacity-60">
              {asked === "done" ? "분석 요청했습니다" : asked === "fail" ? "다시 요청" : "분석 요청"}
            </button>
          </>
        )}
      </div>
      {c.related.length > 0 && (
        <p className="mt-1 text-xs text-slate-500">같은 공고: {c.related.map((r) => r.title).join(" · ")}</p>
      )}
    </li>
  );
}

export default function FindList({ result, children }: { result: FindResult; children?: React.ReactNode }) {
  const by = (g: FindGroup) => result.items.filter((c) => c.result === g);
  const when = result.collected_at ? new Date(result.collected_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : null;
  return (
    <div className="space-y-4" data-testid="find-list">
      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm shadow-sm">
        <div className="flex flex-wrap gap-x-4 gap-y-1" data-testid="find-counts">
          {result.groups.map((g) => (
            <span key={g}>{TONE[g].icon} {result.labels[g]} <b data-testid={`count-${g}`}>{result.counts[g]}</b></span>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          {when ? `공고 목록 기준 ${when}(3시간마다 갱신)` : "등록된 공고 기준"} · 판정 근거는 공고문 원문입니다. 최종 자격은 공고 기관의 서류 심사로 확정됩니다.
        </p>
        {result.notice && <p role="status" className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-900" data-testid="find-notice">{result.notice}</p>}
      </div>
      {children}
      {result.groups.map((g) => {
        const cards = by(g);
        if (!cards.length) return null;
        const body = <ul className="mt-2 space-y-2">{cards.map((c) => <Card key={c.key} c={c} />)}</ul>;
        const head = <>{TONE[g].icon} {result.labels[g]} <span className="text-slate-500">({cards.length})</span></>;
        return result.collapsed.includes(g) ? (
          <details key={g} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm" data-testid={`group-${g}`}>
            <summary className="cursor-pointer font-semibold">{head}</summary>
            {body}
          </details>
        ) : (
          <section key={g} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm" data-testid={`group-${g}`}>
            <h2 className="font-semibold">{head}</h2>
            {body}
          </section>
        );
      })}
      {result.items.length === 0 && (
        <p className="rounded-lg bg-slate-100 p-4 text-sm text-slate-700" data-testid="find-empty">
          이 조건·지역으로 지금 모집 중인 공고가 없습니다. 지역을 &lsquo;전국&rsquo;으로 넓혀 보세요.
        </p>
      )}
    </div>
  );
}
