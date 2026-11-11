"use client";
// 내 조건으로 공고 찾기 — 한 번 입력해 모든 공고·계층을 판정한다(판정 API /match). 입력 양식은 서버(/match/form)가 정한다.
// 입력한 조건은 로그인하지 않으면 서버에 저장하지 않는다 — 내 조건 파일(ccj-profile/1)로 이 기기에 내려받고 다시 불러온다.
// 로그인했으면 '내 조건 등록하기'에 저장한 조건을 불러오거나(?profile=…) 지금 입력을 저장할 수 있다(2026-11-03).
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import MatchList from "@/components/MatchList";
import ProfileForm, { initialValues, toProfile, valuesFrom, type Values } from "@/components/ProfileForm";
import WhatIf from "@/components/WhatIf";
import { AccountError, getMe, getProfile, saveProfile, type Me } from "@/lib/account";
import { ApiError, getMatchForm, match, type Form, type MatchResult, type ProfileFile } from "@/lib/api";
import { fromFile, toFile } from "@/lib/profileFile";
import { revealOnNarrow } from "@/lib/reveal";

const card = "rounded-lg border border-slate-200 bg-white p-5 shadow-sm";

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
  const [me, setMe] = useState<Me | null>(null);
  const [stored, setStored] = useState<{ id: string; alias: string } | null>(null);   // 불러온 저장 조건(덮어쓰기 대상)

  useEffect(() => {
    if (result && reveal.current) {
      reveal.current = false;
      revealOnNarrow(resultsRef.current);
    }
  }, [result]);

  useEffect(() => {
    getMatchForm().then((f) => { setForm(f); setValues(initialValues(f)); }).catch((e: ApiError) => setError(e.message));
    getMe().then(setMe).catch(() => setMe(null));
  }, []);

  // ?profile=… — 내 조건 등록하기에서 고른 조건으로 입력란을 채운다(로그인한 본인 조건만)
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("profile");
    if (!form || !id) return;
    getProfile(id).then((p) => {
      setValues(valuesFrom(form, fromFile(p.profile)));
      setStored({ id: p.id, alias: p.alias });
      setLoaded(`'${p.alias}' 조건으로 입력란을 채웠습니다. 저장하지 않는 민감 항목(수급·장애·국가유공자 등)은 필요하면 직접 넣으세요.`);
    }).catch((e: AccountError) => setError(e.status === 401 ? "로그인이 필요합니다." : e.message));
  }, [form]);

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

  // 피드백 B1: 보류(정보 부족)를 만든 항목 중 지금 비어 있는 것만 결과 아래에서 바로 묻는다.
  // 공고 판정 항목 이름 → 찾기 양식 이름(본인·세대를 따로 묻는 항목은 둘 다)
  const ask = (() => {
    if (!form || !result?.missing_fields) return null;
    const MAP: Record<string, string[]> = {
      home_ownership: ["master.home_self", "master.home_household"], monthly_income: ["master.income_household", "master.income_self"],
      total_assets: ["master.assets_household", "master.assets_self"], car_value: ["master.car_household", "master.car_self"],
      age: ["master.birth_date"], has_children: ["children_birth_dates"], youngest_child_birth_date: ["children_birth_dates"],
    };
    const names = new Set(Object.keys(result.missing_fields).flatMap((f) => MAP[f] ?? [f]));
    const current = toProfile(form, values).profile;
    const fields = form.fields.filter((f) => names.has(f.name) && (current[f.name] === null || current[f.name] === undefined));
    return fields.length ? { ...form, fields, notes: [], collapsed: [] } : null;
  })();

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

  async function store() {
    const alias = stored?.alias ?? prompt("저장할 조건 이름(예: 나, 배우자와 함께)", me?.profiles.length ? "새 조건" : "나");
    if (!alias) return;
    try {
      const p = await saveProfile({ alias, profile: toFile(toProfile(form!, values).profile), status: "done" }, stored?.id);
      setStored({ id: p.id, alias: p.alias });
      setLoaded(`'${p.alias}' 조건으로 저장했습니다(민감 항목은 저장하지 않음).`);
      setError("");
    } catch (e) {
      setError((e as AccountError).message);
    }
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
        <p className="text-sm"><Link href="/find" className="text-blue-700 underline">← 청약 흥신소(지금 모집 중인 공고)</Link></p>
        <h1 className="mt-1 text-xl font-bold sm:text-2xl">자세히 <span className="text-base font-medium text-slate-500">전체 조건으로 모든 등록 공고 보기(지난 공고·What-if)</span></h1>
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
              {me && (
                <button type="button" onClick={store} data-testid="profile-store-account"
                  className="rounded-md border border-blue-700 px-3 py-1.5 text-sm text-blue-700 hover:bg-blue-50">
                  {stored ? `'${stored.alias}'에 저장` : "내 조건에 저장"}
                </button>
              )}
            </div>
            <p className="mt-2 text-xs text-slate-500">
              {me ? <>로그인하면 조건을 <Link href="/me" className="underline">내 조건 등록하기</Link>에 암호화해 저장할 수 있습니다(민감 항목 제외). </>
                : <>로그인하지 않으면 입력한 조건을 서버에 저장하지 않습니다. </>}
              파일로 저장하면 이 기기에만 있고, 다음에 불러오면 입력란이 채워집니다.
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
              {ask && (
                <div className={`${card} border-amber-300`} data-testid="find-questions">
                  <h2 className="mb-1 text-base font-semibold">보류를 줄이려면 — 이 항목만 알려 주세요</h2>
                  <p className="mb-3 text-xs text-slate-600">
                    아래 항목이 비어 있어 일부 공고를 &lsquo;추가 정보 필요&rsquo;로 두었습니다. 아는 대로 넣고 다시 판정하면 그 공고들이 판정됩니다.
                  </p>
                  {stored && me && ask.fields.some((f) => me.not_saved.includes(f.name)) && (
                    <p className="mb-3 text-xs text-amber-800" data-testid="ask-not-saved">
                      수급·장애·국가유공자 같은 민감 항목은 저장한 조건에 넣지 않기 때문에 여기서 다시 묻습니다(입력해도 저장하지 않습니다).
                    </p>
                  )}
                  <ProfileForm form={ask} values={values} onChange={setValues} />
                  <div className="mt-4 flex justify-end">
                    <button type="button" onClick={run} disabled={busy} data-testid="find-rejudge"
                      className="w-full rounded-md bg-amber-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-50 sm:w-auto">
                      다시 판정하기
                    </button>
                  </div>
                </div>
              )}
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
