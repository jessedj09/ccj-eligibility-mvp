// 전 공고 판정 결과 — 화면 3상태(지원 가능 / 보류 / 지원 불가)로 묶고, 묶음 안에서는 접수 중 → 예정 → 마감 순. 판정은 서버가 한 그대로.
import type { MatchItem, MatchResult } from "@/lib/api";

const STATUS_ORDER: Record<string, number> = { OPEN: 0, UPCOMING: 1, CLOSED: 2 };

const GROUPS = [
  { verdict: "ELIGIBLE", title: "✅ 지원 가능", tone: "text-green-800" },
  { verdict: "NEEDS_INFO", title: "🟡 보류 — ⚠️ 추가 정보 필요(더 입력하면 판정)", tone: "text-amber-800" },
  { verdict: "MANUAL_REVIEW", title: "🟡 보류 — 🔍 수동 확인 필요(원문·기관 확인)", tone: "text-amber-800" },
  { verdict: "INELIGIBLE", title: "❌ 지원 불가", tone: "text-red-800" },
] as const;

const short = (m: MatchItem) => m.schedule.text.split(" — ")[0];
// 사업 이름이 이미 기관으로 시작하면(예: "SH 장기전세주택") 기관을 다시 붙이지 않는다
const issuerProgram = (m: MatchItem) =>
  m.issuer && m.program?.startsWith(m.issuer) ? m.program : [m.issuer, m.program].filter(Boolean).join(" ");
const hm = (iso: string) => `${iso.slice(5, 7)}.${iso.slice(8, 10)}. ${iso.slice(11, 16)}`;

function sorted(items: MatchItem[]): MatchItem[] {
  const start = (m: MatchItem) => m.schedule.window?.start ?? "";
  return [...items].sort((a, b) =>
    (STATUS_ORDER[a.schedule.code] ?? 3) - (STATUS_ORDER[b.schedule.code] ?? 3) || start(a).localeCompare(start(b)));
}

function MatchCard({ m }: { m: MatchItem }) {
  const e = m.explanation;
  return (
    <details className="rounded-md border border-slate-200 bg-white" data-testid="match-card">
      <summary className="cursor-pointer px-3 py-2 text-sm">
        <span className="text-slate-600">{short(m)}</span>
        <span className="mx-2 text-slate-300">|</span>
        <span className="text-slate-600">{issuerProgram(m)}</span>
        <span className="mx-2 text-slate-300">|</span>
        <b>{m.title}</b> · {m.layer}
      </summary>
      <div className="space-y-1.5 border-t border-slate-100 px-3 py-3 text-sm text-slate-700">
        <p>
          {m.notice_id} {m.title} — <b>{m.layer}</b>
          {m.eligible_tracks.length > 0 && <> · 충족: {m.eligible_tracks.join(", ")}</>}
        </p>
        <p className="text-xs text-slate-500">{m.schedule.text} (공고일 {m.announcement_date})</p>
        {m.windows.length > 1 && (
          <p className="text-xs text-slate-500">
            접수 일정: {m.windows.map((w) => `${w.label} ${hm(w.start)}~${hm(w.end)}`).join(" / ")}
          </p>
        )}
        {m.schedule_note && <p className="text-xs text-slate-500">🗓️ {m.schedule_note}</p>}
        {e.failed.map((r) => (
          <p key={r.rule_id} className="text-xs">❌ {r.description} <span className="text-slate-500">(근거: {r.source_ref})</span></p>
        ))}
        {e.review.map((r) => (
          <p key={r.rule_id} className="text-xs">🔍 {r.description} — {r.detail}</p>
        ))}
        {e.unknown.map((r) => (
          <p key={r.rule_id} className="text-xs">⚠️ 정보 필요: {r.description}</p>
        ))}
        {e.tracks.filter((t) => t.verdict === "ELIGIBLE").map((t) => (
          <p key={t.track_id} className="text-xs">✅ {t.track_id}: {t.label}</p>
        ))}
        {e.notes.map((n) => (
          <p key={n} className="text-xs text-slate-500">📌 {n}</p>
        ))}
      </div>
    </details>
  );
}

export default function MatchList({ result }: { result: MatchResult }) {
  const by = (v: string) => sorted(result.matches.filter((m) => m.verdict === v));
  const n = (v: keyof MatchResult["counts"]) => result.counts[v] ?? 0;
  const hold = n("NEEDS_INFO") + n("MANUAL_REVIEW");
  const need = Object.entries(result.missing_inputs).slice(0, 6);
  return (
    <div className="space-y-5" data-testid="match-result">
      <div className="grid grid-cols-3 gap-2 sm:gap-4">
        {[["ELIGIBLE", "✅ 지원 가능", n("ELIGIBLE"), "border-green-600"], ["HOLD", "🟡 보류", hold, "border-amber-500"],
          ["INELIGIBLE", "❌ 지원 불가", n("INELIGIBLE"), "border-red-600"]].map(([k, label, v, tone]) => (
          <div key={k} className={`rounded-lg border-l-4 bg-white p-3 shadow-sm sm:p-4 ${tone}`}>
            <p className="text-xs text-slate-600 sm:text-sm">{label}</p>
            <p className="text-2xl font-bold sm:text-3xl" data-testid={`count-${k}`}>{v}</p>
          </div>
        ))}
      </div>
      <p className="text-xs text-slate-600">
        보류 {hold}건 = ⚠️ 추가 정보 필요 {n("NEEDS_INFO")}건(더 입력하면 판정) · 🔍 수동 확인 필요 {n("MANUAL_REVIEW")}건(원문·기관 확인).
        공고·계층(주택형) 단위로 셉니다. 신청 자격(필수요건)만 판정하며 순위·가점·추첨·당첨은 포함하지 않습니다.
        접수 일정은 공고 이후 바뀔 수 있으니 신청 전 원문과 공지사항을 확인하세요.
      </p>
      {need.length > 0 && (
        <p className="rounded-md bg-blue-50 p-3 text-sm text-blue-900" data-testid="missing-inputs">
          이 정보를 더 입력하면 판정할 수 있는 공고가 늘어납니다:{" "}
          {need.map(([k, v], i) => (
            <span key={k}>{i > 0 && ", "}<b>{k}</b>({v}건)</span>
          ))}
        </p>
      )}
      <p className="text-xs text-slate-600">{result.common_note}</p>

      {GROUPS.map(({ verdict, title, tone }) => {
        const items = by(verdict);
        if (!items.length) return null;
        return (
          <section key={verdict} data-testid={`group-${verdict}`}>
            <h3 className={`mb-2 text-base font-semibold ${tone}`}>{title} ({items.length})</h3>
            {verdict === "INELIGIBLE" ? (
              <details className="rounded-md border border-slate-200 bg-white px-3 py-2">
                <summary className="cursor-pointer text-sm">지원 불가 {items.length}건 펼쳐 보기</summary>
                <ul className="mt-2 space-y-1 text-xs text-slate-700">
                  {items.map((m) => (
                    <li key={`${m.notice_id}/${m.layer}`}>
                      {short(m)} {m.notice_id} {m.title} · {m.layer} — {m.explanation.failed[0]?.description ?? ""}
                    </li>
                  ))}
                </ul>
              </details>
            ) : (
              <div className="space-y-2">
                {items.map((m) => <MatchCard key={`${m.notice_id}/${m.layer}`} m={m} />)}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
