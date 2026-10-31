"use client";
// 내 조건으로 공고 찾기 — 한 번 입력해 모든 공고·계층을 판정한다(판정 API /match). 입력 양식은 서버(/match/form)가 정한다.
// 입력한 조건은 서버에 저장하지 않는다 — 내 조건 파일(ccj-profile/1)로 이 기기에 내려받고 다시 불러온다.
import { useEffect, useRef, useState } from "react";
import MatchList from "@/components/MatchList";
import ProfileForm, { initialValues, toProfile, valuesFrom, type Values } from "@/components/ProfileForm";
import WhatIf from "@/components/WhatIf";
import { ApiError, getMatchForm, match, type Form, type MatchResult, type ProfileFile } from "@/lib/api";
import { revealOnNarrow } from "@/lib/reveal";

const MASTER = "master.";
const card = "rounded-lg border border-slate-200 bg-white p-5 shadow-sm";

/** 입력란 항목 → 저장 파일. 'master.x'는 master(모름이면 뺀다), 그 밖은 common(모름은 null 그대로). */
function toFile(profile: Record<string, unknown>): ProfileFile {
  const file: ProfileFile = { schema: "ccj-profile/1", master: {}, common: {} };
  for (const [k, v] of Object.entries(profile)) {
    if (k.startsWith(MASTER)) {
      if (v !== null) file.master[k.slice(MASTER.length)] = v;
    } else file.common[k] = v;
  }
  return file;
}

function fromFile(raw: unknown): Record<string, unknown> {
  const f = raw as Partial<ProfileFile>;
  if (!f || f.schema !== "ccj-profile/1") throw new Error("내 조건 파일 형식이 아닙니다(schema가 'ccj-profile/1'이어야 합니다).");
  const out: Record<string, unknown> = { ...(f.common ?? {}) };
  for (const [k, v] of Object.entries(f.master ?? {})) out[MASTER + k] = v;
  return out;
}

const todayKst = () => new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });

export default function Find() {
  const [form, setForm] = useState<Form | null>(null);
  const [values, setValues] = useState<Values>({});
  const [loaded, setLoaded] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [judged, setJudged] = useState<ProfileFile | null>(null);
  const [day, setDay] = useState(todayKst());
  const [onlyOpen, setOnlyOpen] = useState(true);
  const [result, setResult] = useState<MatchResult | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const reveal = useRef(false);     // '전체 공고 판정'을 눌렀을 때만 결과로 스크롤(기준일·보기를 바꿀 때는 그대로)

  useEffect(() => {
    if (result && reveal.current) {
      reveal.current = false;
      revealOnNarrow(resultsRef.current);
    }
  }, [result]);

  useEffect(() => {
    getMatchForm().then((f) => { setForm(f); setValues(initialValues(f)); }).catch((e: ApiError) => setError(e.message));
  }, []);

  // 오늘이면 지금 시각, 다른 날이면 그날 12:00(한국 시간) 기준으로 접수 상태를 본다
  const at = day === todayKst() ? null : `${day}T12:00:00+09:00`;

  useEffect(() => {
    if (!judged) return;
    let live = true;
    setBusy(true);
    setError("");
    match(judged, at, onlyOpen)
      .then((r) => live && setResult(r))
      .catch((e: ApiError) => live && setError(e.message))
      .finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [judged, at, onlyOpen]);

  if (!form) {
    return error ? <p role="alert" className="text-sm text-red-700">{error}</p> : <p className="text-sm text-slate-500">양식을 불러오는 중…</p>;
  }

  function run() {
    const { profile, errors } = toProfile(form!, values);
    if (errors.length) {
      setError(errors.join(" "));
      return;
    }
    reveal.current = true;
    setJudged(toFile(profile));
  }

  function save() {
    const blob = new Blob([JSON.stringify(toFile(toProfile(form!, values).profile), null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "내조건.json";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function load(file: File) {
    try {
      setValues(valuesFrom(form!, fromFile(JSON.parse(await file.text()))));
      setLoaded("불러온 조건으로 입력란을 채웠습니다. 필요하면 고친 뒤 판정하세요.");
      setError("");
    } catch (e) {
      setLoaded("");
      setError(`불러오지 못했습니다: ${(e as Error).message}`);
    } finally {
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  const sc = result?.schedule_counts;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">🔎 내 조건으로 공고 찾기</h1>
        <p className="mt-1 text-sm text-slate-600">
          한 번 입력하면 보유한 모든 공고의 계층·주택형을 판정합니다. 모르는 항목은 &lsquo;모름&rsquo;으로 두세요 — 그 정보가 필요한 공고는
          &lsquo;추가 정보 필요&rsquo;로 표시되고, 무엇을 더 입력하면 되는지 알려 드립니다.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="space-y-4 lg:col-span-5">
          <div className={card}>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" onClick={() => fileInput.current?.click()}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">📂 저장한 내 조건 불러오기</button>
              <button type="button" onClick={save} data-testid="profile-save"
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">💾 내 조건 파일로 저장</button>
              <input ref={fileInput} type="file" accept=".json,application/json" className="hidden" data-testid="profile-file"
                onChange={(e) => e.target.files?.[0] && load(e.target.files[0])} />
            </div>
            <p className="mt-2 text-xs text-slate-500">
              입력한 조건은 서버에 저장하지 않습니다(소득·자산 같은 개인정보). 저장한 파일은 이 기기에만 있고, 다음에 불러오면 입력란이 채워집니다.
            </p>
            {loaded && <p className="mt-2 text-sm text-green-800" data-testid="profile-loaded">{loaded}</p>}
          </div>
          <div className={card}>
            <ProfileForm form={form} values={values} onChange={setValues} />
            <button type="button" onClick={run} disabled={busy}
              className="mt-6 w-full rounded-md bg-blue-700 py-2.5 font-semibold text-white hover:bg-blue-800 disabled:opacity-50">
              {busy ? "판정 중…" : "전체 공고 판정"}
            </button>
            {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
          </div>
        </div>

        <div ref={resultsRef} className="scroll-mt-4 space-y-6 lg:col-span-7">
          {!result ? (
            <div className={`${card} text-sm text-slate-600`}>
              <span className="hidden lg:inline">왼쪽</span><span className="lg:hidden">위</span>에 조건을 넣고 &lsquo;전체 공고 판정&rsquo;을
              누르면 공고별 결과가 여기에 나옵니다.
            </div>
          ) : (
            <>
              <div className={card}>
                <h2 className="mb-3 text-lg font-semibold">접수 상태</h2>
                <div className="flex flex-wrap items-center gap-6 text-sm">
                  <label className="flex items-center gap-2">
                    기준일
                    <input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} aria-label="기준일"
                      className="rounded-md border border-slate-300 px-2 py-1 text-base sm:text-sm" />
                  </label>
                  {[[true, "접수 중·예정 공고만"], [false, "전체 공고(마감 포함)"]].map(([v, label]) => (
                    <label key={String(v)} className="flex items-center gap-1">
                      <input type="radio" name="view" checked={onlyOpen === v} onChange={() => setOnlyOpen(v as boolean)} />
                      {label}
                    </label>
                  ))}
                </div>
                {sc && (
                  <p className="mt-2 text-xs text-slate-600" data-testid="schedule-counts">
                    {result.at.slice(0, 16).replace("T", " ")} 기준 — 🟢 접수 중 {sc.OPEN}건 · 🗓️ 접수 예정 {sc.UPCOMING}건 ·
                    ⚫ 마감 {sc.CLOSED}건 (보유 공고 {result.notices_total}건, 접수기간은 공고문 원문 기준)
                  </p>
                )}
                {onlyOpen && result.matches.length === 0 && (
                  <p className="mt-3 rounded-md bg-slate-100 p-3 text-sm text-slate-700" data-testid="none-open">
                    이 기준일에 접수 중이거나 접수 예정인 공고가 없습니다 — 보유한 공고는 모두 접수가 끝났습니다.
                    &lsquo;전체 공고(마감 포함)&rsquo;로 바꾸면 마감된 공고의 판정 결과도 볼 수 있고, 새 공고가 추가되면 여기에 표시됩니다.
                  </p>
                )}
              </div>
              <div className={card}><MatchList result={result} /></div>
              <div className={card}>
                <WhatIf key={JSON.stringify(judged)} form={form} profile={judged!} at={at} onlyOpen={onlyOpen} result={result} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
