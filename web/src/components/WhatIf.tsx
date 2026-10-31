"use client";
// What-if — 무엇을 바꾸면 지원 가능해지나(PRD v2.1 F19). 판정은 서버(같은 엔진)가 입력만 바꿔 다시 한다(src/whatif.py).
import { useState } from "react";
import {
  ApiError, whatIf,
  type Form, type MatchResult, type ProfileFile, type Scenario, type WhatIfParams, type WhatIfResult,
} from "@/lib/api";

const SCENARIOS: [Scenario, string][] = [
  ["marry", "혼인신고를 하면"], ["prenuptial", "예비신혼부부로 신청하면"], ["move", "거주지를 옮기면"], ["separate", "세대를 분리하면"],
];

const input =
  "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-base sm:text-sm focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600";
const digits = (s: string) => s.replace(/[^0-9]/g, "");
const won = (n: number) => `${n.toLocaleString("ko-KR")}원`;

function Money({ label, value, set }: { label: string; value: string; set: (v: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-slate-800">{label}</span>
      <input inputMode="numeric" className={input} aria-label={label} value={value ? Number(value).toLocaleString("ko-KR") : ""}
        onChange={(e) => set(digits(e.target.value))} />
    </label>
  );
}

function NearMisses({ result }: { result: MatchResult }) {
  const near = result.near_misses;
  if (!near.length) return <p className="text-sm text-slate-600">걸린 조건이 하나뿐인 &lsquo;지원 불가&rsquo; 공고가 없습니다.</p>;
  return (
    <div className="space-y-3" data-testid="near-list">
      <p className="text-xs text-slate-600">
        &lsquo;지원 불가&rsquo; 중 걸린 조건이 하나뿐인 공고·계층 {near.length}건 — 금액 한도로 풀 수 있는 것부터 보입니다.
        한도는 판정 엔진으로 직접 확인한 값(원 단위)입니다.
      </p>
      <div className="max-h-[32rem] space-y-3 overflow-y-auto pr-2">
        {near.slice(0, 40).map((n) => (
          <div key={`${n.notice_id}/${n.layer}`} className="text-sm">
            <p><b>{n.notice_id} {n.title} · {n.layer}</b> — 이 조건만 해결되면 <b>{n.after}</b></p>
            <p className="text-xs text-slate-600">걸린 조건: {n.condition}</p>
            {n.thresholds.map((t) => (
              <p key={t.field} className="text-xs text-slate-700">
                💡 {t.label}({t.scope}) 현재 {won(t.current)} → <b>{won(t.limit)} 이하</b>면 이 조건 충족 (차이 {won(t.gap)})
                {t.review_limit !== null && `, ${won(t.review_limit)} 이하면 수동 확인(원문 해석에 따라 다름)`}
              </p>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function WhatIf({ form, profile, at, onlyOpen, result }: {
  form: Form; profile: ProfileFile; at: string | null; onlyOpen: boolean; result: MatchResult;
}) {
  const today = new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
  const [tab, setTab] = useState<"near" | "scenario">("near");
  const [scenario, setScenario] = useState<Scenario>("marry");
  const [mdate, setMdate] = useState(today);
  const [spUnknown, setSpUnknown] = useState(false);
  const [sp, setSp] = useState({ income: "0", assets: "0", car: "0" });
  const [spHome, setSpHome] = useState(false);
  const [dual, setDual] = useState(false);
  const [region, setRegion] = useState(Object.values(form.region_groups)[0]?.[0] ?? "");
  const [res, setRes] = useState<WhatIfResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const marry = scenario === "marry" || scenario === "prenuptial";

  async function run() {
    const amount = (s: string) => (spUnknown || s === "" ? null : Number(s));
    const params: WhatIfParams = marry
      ? { marriage_date: scenario === "marry" ? mdate : null, spouse_income: amount(sp.income),
          spouse_assets: amount(sp.assets), spouse_car: amount(sp.car), spouse_has_home: spHome, dual_income: dual }
      : scenario === "move" ? { region } : {};
    setBusy(true);
    setError("");
    try {
      setRes(await whatIf(profile, scenario, params, at, onlyOpen));
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  const tabBtn = (k: typeof tab, label: string) => (
    <button type="button" onClick={() => setTab(k)}
      className={`border-b-2 px-3 py-2 text-sm ${tab === k ? "border-blue-700 font-semibold text-blue-800" : "border-transparent text-slate-600"}`}>
      {label}
    </button>
  );

  return (
    <section className="space-y-4" data-testid="whatif">
      <h2 className="text-lg font-semibold">🔀 What-if — 무엇을 바꾸면 지원 가능해지나</h2>
      <p className="text-xs text-slate-600">{result.whatif_caveat}</p>
      {onlyOpen && result.matches.length === 0 && (
        <p className="rounded-md bg-slate-100 p-3 text-sm text-slate-700">
          지금 접수 중·예정인 공고가 없어 비교할 대상이 없습니다. 위 &lsquo;보기&rsquo;에서 &lsquo;전체 공고(마감 포함)&rsquo;를 고르면
          마감된 공고로 비교해 볼 수 있습니다.
        </p>
      )}
      <div className="flex gap-2 border-b border-slate-200">
        {tabBtn("near", "조건 하나만 부족한 공고")}
        {tabBtn("scenario", "시나리오로 비교")}
      </div>
      {tab === "near" ? <NearMisses result={result} /> : (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-4 text-sm">
            {SCENARIOS.map(([k, label]) => (
              <label key={k} className="flex items-center gap-1">
                <input type="radio" name="scenario" checked={scenario === k} onChange={() => { setScenario(k); setRes(null); }} />
                {label}
              </label>
            ))}
          </div>
          {marry && (
            <>
              <p className="text-xs text-slate-600">
                가정: 본인·배우자(·본인 자녀)로 새 세대를 꾸리고(부모 세대에서 분리) 같은 곳에 삽니다.
                세대 소득·자산은 본인+배우자, 주택은 둘 중 하나라도 있으면 보유로 봅니다.
              </p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {scenario === "marry" && (
                  <label className="block text-sm">
                    <span className="mb-1 block font-medium text-slate-800">혼인신고일</span>
                    <input type="date" className={input} value={mdate} onChange={(e) => setMdate(e.target.value)} aria-label="혼인신고일" />
                  </label>
                )}
                <label className="flex items-center gap-2 text-sm sm:col-span-2">
                  <input type="checkbox" checked={spUnknown} onChange={(e) => setSpUnknown(e.target.checked)} />
                  배우자 소득·자산 모름
                </label>
                {!spUnknown && (
                  <>
                    <Money label="배우자 월평균소득(원)" value={sp.income} set={(v) => setSp({ ...sp, income: v })} />
                    <Money label="배우자 총자산(원)" value={sp.assets} set={(v) => setSp({ ...sp, assets: v })} />
                    <Money label="배우자 자동차가액(원, 없으면 0)" value={sp.car} set={(v) => setSp({ ...sp, car: v })} />
                  </>
                )}
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={spHome} onChange={(e) => setSpHome(e.target.checked)} />
                  배우자가 주택 보유
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={dual} onChange={(e) => setDual(e.target.checked)} />
                  맞벌이(본인·배우자 모두 소득)
                </label>
              </div>
            </>
          )}
          {scenario === "move" && (
            <label className="block max-w-sm text-sm">
              <span className="mb-1 block font-medium text-slate-800">옮길 거주지(주민등록)</span>
              <select className={input} value={region} onChange={(e) => setRegion(e.target.value)} aria-label="옮길 거주지">
                {Object.entries(form.region_groups).map(([g, names]) => (
                  <optgroup key={g} label={g}>
                    {names.map((n) => <option key={n} value={n}>{g === "경기도" ? `경기 ${n}` : n}</option>)}
                  </optgroup>
                ))}
              </select>
            </label>
          )}
          {scenario === "separate" && (
            <p className="text-xs text-slate-600">
              가정: 부모 세대에서 분리해 본인(과 본인 자녀)으로 세대를 꾸리고 세대주가 됩니다. 세대 소득·자산·주택은 본인 것만 봅니다
              (대학생 계층의 부모 소득은 등본과 무관하게 계속 합산).
            </p>
          )}
          <button type="button" onClick={run} disabled={busy}
            className="rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50">
            {busy ? "판정 중…" : "이 시나리오로 다시 판정"}
          </button>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          {res && (
            <div className="space-y-3" data-testid="whatif-result">
              <div className="grid grid-cols-3 gap-2 sm:gap-4">
                {([["ELIGIBLE", "✅ 지원 가능"], ["HOLD", "🟡 보류"], ["INELIGIBLE", "❌ 지원 불가"]] as const).map(([k, label]) => {
                  const d = res.after[k] - res.before[k];
                  return (
                    <div key={k} className="rounded-lg border border-slate-200 bg-white p-2.5 sm:p-3">
                      <p className="text-xs text-slate-600 sm:text-sm">{label}</p>
                      <p className="text-xl font-bold sm:text-2xl">{res.after[k]}
                        <span className={`ml-2 text-sm ${d > 0 ? "text-green-700" : d < 0 ? "text-red-700" : "text-slate-400"}`}>
                          {d > 0 ? `+${d}` : d}
                        </span>
                      </p>
                    </div>
                  );
                })}
              </div>
              <p className="text-xs text-slate-600">
                &lsquo;{res.name}&rsquo; 전후 비교 — 지금 {res.before.ELIGIBLE}건 → {res.after.ELIGIBLE}건 지원 가능
                {onlyOpen && " (접수 중·예정 공고만)"}
              </p>
              {res.gained.length > 0 && (
                <div className="text-sm">
                  <p className="font-semibold">새로 지원 가능 {res.gained.length}건</p>
                  {res.gained.map((x) => <p key={`${x.notice_id}/${x.layer}`} className="text-xs">✅ {x.notice_id} {x.title} · {x.layer}</p>)}
                </div>
              )}
              {res.lost.length > 0 && (
                <div className="text-sm">
                  <p className="font-semibold">지원 가능에서 빠지는 {res.lost.length}건</p>
                  {res.lost.map((x) => (
                    <p key={`${x.notice_id}/${x.layer}`} className="text-xs">❌ {x.notice_id} {x.title} · {x.layer} — {x.reason}</p>
                  ))}
                </div>
              )}
              {res.gained.length === 0 && res.lost.length === 0 && (
                <p className="text-sm text-slate-600">이 시나리오로는 지원 가능한 공고가 바뀌지 않습니다.</p>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
