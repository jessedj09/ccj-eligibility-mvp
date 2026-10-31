"use client";
// 공고 판정(메인) — 공고문 PDF를 올리거나 목록에서 골라 계층을 정하고, 필요한 정보만 넣어 판정한다. PC 브라우저 기준 2단 화면.
import { useEffect, useState } from "react";
import ProfileForm, { initialValues, toProfile, type Values } from "@/components/ProfileForm";
import ResultView from "@/components/ResultView";
import {
  ApiError, evaluate, getForm, listNotices, upload,
  type Form, type NoticeSummary, type Result, type Target, type UnsupportedLayer, type UploadResult,
} from "@/lib/api";

type Picked = { target: Target; title: string; layers: string[]; unsupported: UnsupportedLayer[] };

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
  if (j.by === "analysis")
    return (
      <div className="text-sm" data-testid="ident">
        <p>📄 올린 공고문: <b>{j.program}</b> · 공고일 {j.announcement_date}</p>
        <p className="mt-1 text-xs text-slate-600">공고문 원문에서 조건을 읽어 판정합니다.</p>
        {windows}
      </div>
    );
  return (
    <div className="space-y-1 text-sm" data-testid="ident">
      <p className="font-semibold">📄 아직 판정할 수 없는 공고</p>
      <p className="text-slate-700">{j.reason}</p>
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
  const [error, setError] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [picked, setPicked] = useState<Picked | null>(null);
  const [layer, setLayer] = useState("");
  const [form, setForm] = useState<Form | null>(null);
  const [values, setValues] = useState<Values>({});
  const [result, setResult] = useState<Result | null>(null);

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
    setBusy("공고문을 읽고 분석하는 중입니다…");
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
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  const unsupported = picked?.unsupported.find((u) => u.name === layer);

  return (
    <div className="grid grid-cols-[22rem_1fr] gap-8">
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
                <span className="mt-1 text-xs">LH 청약플러스·SH 인터넷청약의 입주자모집공고문 PDF(20MB까지)</span>
                <input type="file" accept="application/pdf,.pdf" className="hidden" data-testid="pdf-input"
                  onChange={(e) => onFile(e.target.files?.[0])} />
              </label>
              {up && <Identified up={up} confirmed={confirmed} onConfirm={onConfirm} />}
            </div>
          ) : (
            <select className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" defaultValue=""
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
        {busy && <p className="rounded-md bg-blue-50 px-4 py-3 text-sm text-blue-900" role="status">{busy}</p>}
        {error && <p className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">{error}</p>}
        {!picked && !busy && (
          <div className={`${card} text-sm text-slate-600`}>
            왼쪽에서 공고문 PDF를 올리거나 목록에서 공고를 고르면, 그 공고의 공급 계층과 필요한 입력 항목이 나옵니다.
          </div>
        )}
        {picked && !layer && <div className={`${card} text-sm text-slate-600`}>왼쪽에서 공급 계층을 고르세요.</div>}
        {unsupported && (
          <div className={`${card} text-sm`}>
            <b>{unsupported.name}</b> 계층은 이 공고에 있지만{unsupported.page ? ` (공고문 p.${unsupported.page})` : ""} 아직 판정을
            지원하지 않습니다. {unsupported.note}
          </div>
        )}
        {form && (
          <div className={card}>
            <div className="mb-4 flex items-baseline justify-between">
              <h2 className="text-base font-semibold">3. 내 정보 — {picked?.title} · {layer}</h2>
              <span className="text-xs text-slate-500">공고일 {form.announcement_date} 기준으로 계산합니다</span>
            </div>
            <ProfileForm form={form} values={values} onChange={setValues} />
            <div className="mt-6 flex justify-end">
              <button type="button" onClick={onJudge} disabled={Boolean(busy)}
                className="rounded-md bg-blue-700 px-6 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50">
                판정하기
              </button>
            </div>
          </div>
        )}
        {result && (
          <div className={card}>
            <h2 className="mb-4 text-base font-semibold">4. 판정 결과</h2>
            <ResultView result={result} />
          </div>
        )}
      </main>
    </div>
  );
}
