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

// 판정이 확인하지 않는 것 — 결론 바로 옆에 둔다(피드백 A1: '지원 가능'을 '당첨 가능'으로 읽지 않게)
const NOT_CHECKED = [
  "공통 결격사유(과거 공공임대 불법 양도·전대 이력, 1세대 중복 신청 등)",
  "순위·배점·추첨과 당첨 여부",
  "서류 심사 — 입력하신 값과 실제 증빙(소득·자산 조회 결과)의 차이",
];

const SOURCE_LABEL = {
  registered: "검증된 등록 규칙(사람이 원문과 대조한 규칙)으로 판정",
  analysis: "자동으로 읽은 공고(올린 공고문에서 읽은 조건)로 판정",
};

export default function ResultView({ result, source }: { result: Result; source?: "registered" | "analysis" }) {
  const d = result.display;
  const checked = result.matched.length + result.failed.length + result.unknown.length + result.review.length;
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
      <div className="grid grid-cols-1 gap-3 rounded-md bg-slate-50 p-3 text-xs text-slate-700 sm:grid-cols-2" data-testid="scope">
        <div>
          <p className="mb-1 font-semibold text-slate-800">이 판정이 확인한 것</p>
          <p>입력하신 정보 기준으로, 이 공고·계층의 신청 자격(필수요건) {checked}개 조건을 공고문 원문과 대조했습니다.</p>
          {source && <p className="mt-1 text-slate-500" data-testid="source">{SOURCE_LABEL[source]}</p>}
          {result.verification && (
            <p className="mt-1 text-slate-600" data-testid="verification">
              검증 상태: <b>{result.verification.label}</b> — {result.verification.note}
            </p>
          )}
          {result.basis && (
            <p className="mt-1 text-slate-400" data-testid="basis">
              {result.basis.judged_at.replace("T", " ").slice(0, 16)} 판정 ·{" "}
              {result.basis.rule_version ?? result.basis.analysis_version} · {result.basis.engine_version}
            </p>
          )}
        </div>
        <div>
          <p className="mb-1 font-semibold text-slate-800">확인하지 않은 것</p>
          <ul className="list-disc space-y-0.5 pl-4">
            {NOT_CHECKED.map((x) => <li key={x}>{x}</li>)}
          </ul>
        </div>
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
