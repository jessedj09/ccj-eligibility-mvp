// 판정 결과 — 화면 3상태(지원 가능 / 보류 / 지원 불가)와 조건별 근거(공고문 쪽·원문). 판정은 서버가 한 그대로.
import type { Reason, Result, Review } from "@/lib/api";

const GROUP_STYLE: Record<string, string> = {
  "지원 가능": "border-green-600 bg-green-50 text-green-900",
  "보류": "border-amber-500 bg-amber-50 text-amber-900",
  "지원 불가": "border-red-600 bg-red-50 text-red-900",
  "해당 없음": "border-slate-400 bg-slate-50 text-slate-800",
};

const TRACK_LABEL: Record<string, string> = {
  ELIGIBLE: "충족",
  INELIGIBLE: "불충족",
  NEEDS_INFO: "정보 부족",
  MANUAL_REVIEW: "수동 확인",
  NOT_OFFERED: "해당 없음",
};

function Reasons({ title, items, tone }: { title: string; items: (Reason | Review)[]; tone: string }) {
  if (!items.length) return null;
  return (
    <div>
      <h4 className={`mb-2 text-sm font-semibold ${tone}`}>{title}</h4>
      <ul className="space-y-1.5 text-sm text-slate-800">
        {items.map((r) => (
          <li key={r.rule_id} className="leading-relaxed">
            {r.description} <span className="text-xs text-slate-500">(근거: {r.source_ref})</span>
            {"detail" in r && r.detail && <div className="mt-0.5 text-xs text-slate-600">{r.detail}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ResultView({ result }: { result: Result }) {
  const d = result.display;
  return (
    <div className="space-y-5" data-testid="result">
      <div className={`rounded-lg border-l-4 p-4 ${GROUP_STYLE[d.group] ?? GROUP_STYLE["해당 없음"]}`}>
        <p className="text-lg font-bold" data-testid="result-title">
          {d.icon} {d.title}
        </p>
        <p className="mt-1 text-sm">{result.headline}</p>
        <p className="mt-2 text-sm opacity-90">{d.todo}</p>
        {result.checks.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm">
            {result.checks.map((c, i) => (
              <li key={i}>🔍 {c.text}</li>
            ))}
          </ul>
        )}
      </div>
      <p className="text-xs text-slate-600">{result.common_note}</p>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <Reasons title="충족한 조건" items={result.matched} tone="text-green-800" />
        <Reasons title="충족하지 못한 조건" items={result.failed} tone="text-red-800" />
        <Reasons title="추가로 입력하면 판정할 수 있는 조건" items={result.unknown} tone="text-amber-800" />
        <Reasons title="자동 확정이 어려운 조건 (수동 확인 필요)" items={result.review} tone="text-amber-800" />
      </div>

      {result.tracks.length > 0 && (
        <div>
          <h4 className="mb-2 text-sm font-semibold text-slate-800">순위·유형별 결과</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs text-slate-500">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">순위·유형</th>
                  <th className="py-1.5 pr-3 font-medium">결과</th>
                  <th className="py-1.5 font-medium">내용</th>
                </tr>
              </thead>
              <tbody>
                {result.tracks.map((t) => (
                  <tr key={t.track_id} className="border-b border-slate-100 align-top">
                    <td className="py-1.5 pr-3 whitespace-nowrap">{t.track_id}</td>
                    <td className="py-1.5 pr-3 whitespace-nowrap">{TRACK_LABEL[t.verdict] ?? t.verdict}</td>
                    <td className="py-1.5 text-slate-700">{t.label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-1 text-xs text-slate-500">순위 안의 경쟁·추첨·배점은 판정하지 않습니다.</p>
        </div>
      )}

      {result.notes.length > 0 && (
        <ul className="space-y-1 text-xs text-slate-500">
          {result.notes.map((n) => (
            <li key={n}>※ {n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
