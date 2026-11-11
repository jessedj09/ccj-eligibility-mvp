"use client";
// 공고 판정(메인) — 공고문 PDF를 올리거나 목록에서 골라 계층을 정하고, 필요한 정보만 넣어 판정한다. PC는 2단, 휴대폰은 1단.
import { useEffect, useMemo, useRef, useState } from "react";
import ProfileForm, { initialValues, toProfile, type Values } from "@/components/ProfileForm";
import UploadProgress from "@/components/UploadProgress";
import ResultView from "@/components/ResultView";
import {
  ApiError, evaluate, getForm, listNotices, upload,
  type Form, type NoticeSummary, type Result, type Target, type UnsupportedLayer, type UploadResult,
} from "@/lib/api";
import { reveal, revealOnNarrow } from "@/lib/reveal";

type Picked = { target: Target; title: string; layers: string[]; unsupported: UnsupportedLayer[] };

const READING = "공고문을 읽고 분석하는 중입니다…";
const MAX_MB = 20;   // 서버 한도(api/main.py MAX_UPLOAD)와 같다 — 넘으면 올리기 전에 알린다(피드백 A6)

/** 기다린 시간(초) — 큰 공고문은 읽는 데 오래 걸려 멈춘 것처럼 보이지 않게. */
const card = "rounded-lg border border-slate-200 bg-white p-4 shadow-sm";

function Identified({ up, confirmed, onConfirm }: { up: UploadResult; confirmed: boolean; onConfirm: (v: boolean) => void }) {
  const j = up.judge;
  const id = up.identification;
  const windows = id.windows.length > 0 && (
    <p className="mt-2 text-xs text-slate-600">
      청약 접수기간: {id.windows.map((w) => `${w.start.replace("T", " ")} ~ ${w.end.replace("T", " ")} (p.${w.page})`).join(" / ")}
    </p>
  );
  if (j.by === "registered")
    return (
      <div className="text-sm" data-testid="ident">
        <p>📄 올린 공고문 = 등록 공고 <b>{j.notice_id} {j.title}</b></p>
        <p className="mt-1 text-xs text-slate-600">원문 파일 일치 — 검증된 규칙으로 판정합니다.</p>
      </div>
    );
  if (j.by === "confirm")
    return (
      <div className="space-y-2 text-sm" data-testid="ident">
        <p>📄 {id.reason}</p>
        <label className="flex items-center gap-2 font-medium">
          <input type="checkbox" checked={confirmed} onChange={(e) => onConfirm(e.target.checked)} />
          등록 공고 {j.notice_id} 원문 기준으로 판정하기
        </label>
        <p className="text-xs text-slate-600">같은 공고를 다시 내려받은 파일이면 결과가 같습니다. 정정 공고면 다를 수 있습니다.</p>
      </div>
    );
  const correction = id.corrects && (
    <p className="text-xs text-amber-800" data-testid="correction">
      등록 공고 {id.corrects}의 정정 공고로 보입니다(파일 이름). 조건이 바뀌었을 수 있어 등록된 규칙이 아니라 이 파일로 판단합니다.
    </p>
  );
  if (j.by === "analysis")
    return (
      <div className="text-sm" data-testid="ident">
        <p>📄 올린 공고문: <b>{j.program}</b> · 공고일 {j.announcement_date}</p>
        <p className="mt-1 text-xs text-slate-600">공고문 원문에서 조건을 읽어 판정합니다.</p>
        {correction}
        {windows}
      </div>
    );
  // '판정하지 않음'은 '지원 불가'와 다르다 — 빨강 대신 회색 ➖(피드백 A2)
  return (
    <div className="space-y-1 rounded-md border-l-4 border-slate-400 bg-slate-50 p-3 text-sm" data-testid="ident">
      <p className="font-semibold text-slate-800" data-testid="none-title">➖ 판정하지 않음 <span className="font-normal text-slate-500">(지원 불가라는 뜻이 아닙니다)</span></p>
      <p className="text-slate-700" data-testid="none-reason">{j.reason}</p>
      {correction}
      {j.supported_programs && j.supported_programs.length > 0 && (
        <p className="text-xs text-slate-600">
          새 공고 자동 판정 지원 사업: {j.supported_programs.join(", ")}. 다른 사업은 정확도를 검증하며 차례로 추가합니다.
        </p>
      )}
      {j.registered ? (
        <p className="text-xs text-slate-600">
          이미 등록된 공고 {j.registered}건은 위 &lsquo;목록에서 고르기&rsquo;로 판정할 수 있습니다.
        </p>
      ) : null}
      {(id.program || id.announcement) && (
        <p className="text-xs text-slate-600">
          {[id.issuer, id.program].filter(Boolean).join(" ")} {id.announcement && `· 공고일 ${id.announcement}`}
        </p>
      )}
      {windows}
    </div>
  );
}

export default function Home() {
  const [mode, setMode] = useState<"upload" | "list">("upload");
  const [notices, setNotices] = useState<NoticeSummary[]>([]);
  const [up, setUp] = useState<UploadResult | null>(null);
  const [busy, setBusy] = useState("");
  const [uploadBytes, setUploadBytes] = useState(0);
  const [error, setError] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [picked, setPicked] = useState<Picked | null>(null);
  const [layer, setLayer] = useState("");
  const [form, setForm] = useState<Form | null>(null);
  const [values, setValues] = useState<Values>({});
  const [result, setResult] = useState<Result | null>(null);
  const [judgedProfile, setJudgedProfile] = useState<Record<string, unknown> | null>(null);
  const formRef = useRef<HTMLDivElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);

  const [fromNotice, setFromNotice] = useState("");     // 흥신소 예비 판정 카드에서 '공고문 올리면 바로 확정'으로 왔을 때
  useEffect(() => setFromNotice(new URLSearchParams(window.location.search).get("from") ?? ""), []);
  useEffect(() => revealOnNarrow(formRef.current), [form]);
  useEffect(() => reveal(resultRef.current), [result]);
  useEffect(() => reveal(errorRef.current), [error]);

  useEffect(() => {
    if (mode === "list" && notices.length === 0)
      listNotices().then(setNotices).catch((e: ApiError) => setError(e.message));
  }, [mode, notices.length]);

  function reset() {
    setPicked(null);
    setLayer("");
    setForm(null);
    setResult(null);
    setError("");
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    reset();
    setUp(null);
    setConfirmed(false);
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`파일이 너무 큽니다(${(Math.ceil(file.size / 1024 / 1024 * 10) / 10).toFixed(1)}MB). 공고문 PDF는 ${MAX_MB}MB까지 올릴 수 있습니다.`);
      return;
    }
    setUploadBytes(file.size);
    setBusy(READING);
    try {
      const r = await upload(file);
      setUp(r);
      const j = r.judge;
      if (j.by === "registered")
        setPicked({ target: { notice_id: j.notice_id }, title: j.title, layers: j.layers, unsupported: j.unsupported_layers });
      else if (j.by === "analysis")
        setPicked({ target: { sha256: r.sha256 }, title: j.program, layers: j.layers, unsupported: [] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  function onConfirm(v: boolean) {
    setConfirmed(v);
    reset();
    if (v && up && up.judge.by === "confirm") {
      const j = up.judge;
      setPicked({ target: { notice_id: j.notice_id }, title: j.title, layers: j.layers, unsupported: j.unsupported_layers });
    }
  }

  function onPickNotice(nid: string) {
    reset();
    const n = notices.find((x) => x.notice_id === nid);
    if (n) setPicked({ target: { notice_id: n.notice_id }, title: n.title, layers: n.layers, unsupported: [] });
  }

  async function onLayer(l: string) {
    if (!picked) return;
    setLayer(l);
    setForm(null);
    setResult(null);
    setError("");
    if (picked.unsupported.some((u) => u.name === l)) return;   // 아직 지원하지 않는 계층 — 안내만
    try {
      const f = await getForm(picked.target, l);
      setForm(f);
      setValues(initialValues(f));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function onJudge() {
    if (!picked || !form) return;
    const { profile, errors } = toProfile(form, values);
    if (errors.length) {
      setError(errors.join(" "));
      return;
    }
    setError("");
    setBusy("판정하는 중입니다…");
    try {
      setResult(await evaluate(picked.target, layer, profile));
      setJudgedProfile(profile);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  const unsupported = picked?.unsupported.find((u) => u.name === layer);

  // 피드백 B1: '보류 — 추가 정보 필요'를 질문으로 — 정보 부족 조건이 읽는 항목 중 이번에 '모름'으로 보낸 것만 다시 묻는다
  const ask = useMemo(() => {
    if (!result || !form || result.verdict !== "NEEDS_INFO" || !result.questions?.length || !judgedProfile) return null;
    const names = new Set(result.questions.flatMap((q) => q.fields));
    const fields = form.fields.filter((f) => names.has(f.name) && f.type !== "age" &&
      (judgedProfile[f.name] === null || judgedProfile[f.name] === undefined));
    if (!fields.length) return null;
    const asked = new Set(fields.map((f) => f.name));
    // 순위·유형마다 같은 조건(소득·자산 등)이 되풀이되므로 설명이 같은 것은 한 번만
    const seen = new Set<string>();
    const items = result.questions.filter((q) => q.fields.some((x) => asked.has(x)) && !seen.has(q.description) &&
      Boolean(seen.add(q.description)));
    return { form: { ...form, fields, notes: [] }, items };
  }, [result, form, judgedProfile]);

  /** 판정 결과 보관(피드백 B2) — 입력·결과·판정 근거의 판을 이 기기에 파일로. 서버에는 남지 않는다. */
  function saveResult() {
    if (!result) return;
    const file = { format: "ccj-result/1", basis: result.basis, notice: picked?.title, input: judgedProfile, result };
    const blob = new Blob([JSON.stringify(file, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `판정결과_${result.basis?.notice_id ?? "올린공고"}_${layer}_${(result.basis?.judged_at ?? "").slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="space-y-5">
    <h1 className="text-xl font-bold sm:text-2xl">재판소 <span className="text-base font-medium text-slate-500">공고문 올리고 지원 자격 판정</span></h1>
    {fromNotice && (
      <p className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900" data-testid="from-notice">
        &lsquo;{fromNotice}&rsquo; 공고문 PDF를 공식 공고 페이지에서 내려받아 올리면 바로 확정 판정합니다. 한 번 올라온 공고는 분석이 저장돼
        청약 흥신소 목록에서도 모두 &lsquo;이 공고문 기준&rsquo;으로 바뀝니다.
      </p>
    )}
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[22rem_1fr] lg:gap-8">
      <aside className="space-y-4">
        <div className={card}>
          <h2 className="mb-3 text-base font-semibold">1. 공고 고르기</h2>
          <div className="mb-3 flex rounded-md bg-slate-100 p-1 text-sm">
            {(["upload", "list"] as const).map((m) => (
              <button key={m} type="button"
                className={`flex-1 rounded px-2 py-1.5 ${mode === m ? "bg-white font-semibold shadow-sm" : "text-slate-600"}`}
                onClick={() => { setMode(m); reset(); setUp(null); }}>
                {m === "upload" ? "공고문 PDF 올리기" : "목록에서 고르기"}
              </button>
            ))}
          </div>
          {mode === "upload" ? (
            <div className="space-y-3">
              <label className="flex cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-600 hover:border-blue-500 hover:bg-blue-50"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); onFile(e.dataTransfer.files[0]); }}>
                <span className="font-medium text-slate-800">공고문 PDF를 끌어 놓거나 눌러서 고르세요</span>
                <span className="mt-1 text-xs">LH 청약플러스·SH 인터넷청약의 입주자모집공고문 PDF({MAX_MB}MB까지)</span>
                <input type="file" accept="application/pdf,.pdf" className="hidden" data-testid="pdf-input"
                  onChange={(e) => onFile(e.target.files?.[0])} />
              </label>
              {up && <Identified up={up} confirmed={confirmed} onConfirm={onConfirm} />}
            </div>
          ) : (
            <select className="w-full rounded-md border border-slate-300 px-3 py-2 text-base sm:text-sm" defaultValue=""
              onChange={(e) => onPickNotice(e.target.value)} data-testid="notice-select">
              <option value="" disabled>공고를 고르세요</option>
              {notices.map((n) => (
                <option key={n.notice_id} value={n.notice_id}>
                  {n.notice_id} — {n.title} ({n.schedule.text})
                </option>
              ))}
            </select>
          )}
        </div>

        {picked && (
          <div className={card}>
            <h2 className="mb-3 text-base font-semibold">2. 공급 계층</h2>
            <div className="flex flex-wrap gap-2">
              {[...picked.layers, ...picked.unsupported.map((u) => u.name)].map((l) => {
                const off = picked.unsupported.some((u) => u.name === l);
                return (
                  <button key={l} type="button" onClick={() => onLayer(l)}
                    className={`rounded-full border px-3 py-1 text-sm ${layer === l ? "border-blue-700 bg-blue-700 text-white" : "border-slate-300 bg-white hover:border-blue-500"} ${off ? "text-slate-400" : ""}`}>
                    {l}{off && " (아직 지원 안 함)"}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </aside>

      <main className="space-y-6">
        {busy === READING && <UploadProgress bytes={uploadBytes} />}
        {busy && busy !== READING && (
          <p className="rounded-md bg-blue-50 px-4 py-3 text-sm text-blue-900" role="status" data-testid="busy">{busy}</p>
        )}
        {error && <p ref={errorRef} className="scroll-mt-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">{error}</p>}
        {!picked && !busy && (
          <div className={`${card} text-sm text-slate-600`}>
            <span className="hidden lg:inline">왼쪽</span><span className="lg:hidden">위</span>에서 공고문 PDF를 올리거나 목록에서 공고를
            고르면, 그 공고의 공급 계층과 필요한 입력 항목이 나옵니다.
          </div>
        )}
        {picked && !layer && (
          <div className={`${card} text-sm text-slate-600`}>
            <span className="hidden lg:inline">왼쪽</span><span className="lg:hidden">위</span>에서 공급 계층을 고르세요.
          </div>
        )}
        {unsupported && (
          <div className={`${card} text-sm`}>
            <b>{unsupported.name}</b> 계층은 이 공고에 있지만{unsupported.page ? ` (공고문 p.${unsupported.page})` : ""} 아직 판정을
            지원하지 않습니다. {unsupported.note}
          </div>
        )}
        {form && (
          <div ref={formRef} className={`${card} scroll-mt-4`}>
            <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <h2 className="text-base font-semibold">3. 내 정보 — {picked?.title} · {layer}</h2>
              <span className="text-xs text-slate-500">공고일 {form.announcement_date} 기준으로 계산합니다</span>
            </div>
            <ProfileForm form={form} values={values} onChange={setValues} />
            <div className="mt-6 flex justify-end">
              <button type="button" onClick={onJudge} disabled={Boolean(busy)}
                className="w-full rounded-md bg-blue-700 px-6 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50 sm:w-auto">
                판정하기
              </button>
            </div>
          </div>
        )}
        {result && (
          <div ref={resultRef} className={`${card} scroll-mt-4`}>
            <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-base font-semibold">4. 판정 결과</h2>
              <button type="button" onClick={saveResult} data-testid="save-result"
                className="rounded-md border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:border-blue-500">
                결과 파일로 저장
              </button>
            </div>
            <ResultView result={result} source={picked && "notice_id" in picked.target ? "registered" : "analysis"} />
          </div>
        )}
        {ask && (
          <div className={`${card} border-amber-300`} data-testid="questions">
            <h2 className="mb-1 text-base font-semibold">이것만 알려 주시면 바로 판정합니다</h2>
            <p className="mb-3 text-xs text-slate-600">
              아래 항목을 &lsquo;모름&rsquo;으로 두어 판정을 미뤘습니다. 아는 대로 답하고 다시 판정하세요. 해석이 필요한 조건(수동 확인)은
              공고 기관에 문의해야 합니다.
            </p>
            <details className="mb-4 text-sm text-slate-700" open={ask.items.length <= 4}>
              <summary className="cursor-pointer text-xs font-medium text-slate-600">판정을 미룬 조건 {ask.items.length}개 보기</summary>
              <ul className="mt-2 space-y-1">
                {ask.items.map((q) => (
                  <li key={q.rule_id}>· {q.description} <span className="text-xs text-slate-500">(근거: {q.source_ref})</span></li>
                ))}
              </ul>
            </details>
            <ProfileForm form={ask.form} values={values} onChange={setValues} />
            <div className="mt-4 flex justify-end">
              <button type="button" onClick={onJudge} disabled={Boolean(busy)} data-testid="rejudge"
                className="w-full rounded-md bg-amber-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-50 sm:w-auto">
                다시 판정하기
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
    </div>
  );
}
