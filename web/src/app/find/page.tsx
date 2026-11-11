"use client";
// 청약 흥신소(주 흐름, 2026-11-10 결정) — 기본 자격조건 → 지금 모집 중인 LH·SH 공고 목록(판정 API /find).
// 첫 화면 양식은 서버(/find/form)가 정하고, 값은 전체 찾기 양식(/match/form) 이름으로 들고 있어 추가 질문·저장 파일·회원 '내 조건'이 그대로 맞는다.
// 입력한 조건은 서버에 저장하지 않는다(로그인해 '내 조건'에 저장한 경우만 — 민감 항목 제외). 지금의 전체 판정은 /find/all('자세히').
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import FindList from "@/components/FindList";
import ProfileForm, { initialValues, toProfile, valuesFrom, type Values } from "@/components/ProfileForm";
import { AccountError, getMe, getProfile, type Me } from "@/lib/account";
import { ApiError, findOpen, getFindForm, getMatchForm, type FindForm, type FindResult, type Form } from "@/lib/api";
import { fromFile, toFile } from "@/lib/profileFile";
import { revealOnNarrow } from "@/lib/reveal";

const card = "rounded-lg border border-slate-200 bg-white p-5 shadow-sm";
const CAPITAL = ["서울특별시", "경기도", "인천광역시"];
type Area = "capital" | "mine" | "all";

// 판정이 묻는 엔진 항목 → 찾기 양식 이름(본인·세대를 따로 묻는 항목은 둘 다)
const ASK: Record<string, string[]> = {
  home_ownership: ["master.home_self", "master.home_household"], monthly_income: ["master.income_household", "master.income_self"],
  total_assets: ["master.assets_household", "master.assets_self"], car_value: ["master.car_household", "master.car_self"],
  age: ["master.birth_date"], has_children: ["children_birth_dates"], youngest_child_birth_date: ["children_birth_dates"],
};

export default function Find() {
  const [basic, setBasic] = useState<FindForm | null>(null);
  const [full, setFull] = useState<Form | null>(null);
  const [values, setValues] = useState<Values>({});
  const [kind, setKind] = useState("둘 다");
  const [area, setArea] = useState<Area>("capital");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<FindResult | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [autoRun, setAutoRun] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const at = useRef<string | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("at");      // 기준일(점검·지난 날 보기) — 없으면 지금
    at.current = q && /^\d{4}-\d{2}-\d{2}$/.test(q) ? `${q}T12:00:00+09:00` : null;
    Promise.all([getFindForm(), getMatchForm()]).then(([b, f]) => {
      setBasic(b);
      setFull(f);
      setValues(initialValues(f));
      setKind(b.filters.kind.default);
    }).catch((e: ApiError) => setError(e.message));
    getMe().then(setMe).catch(() => setMe(null));
  }, []);

  // 저장한 조건으로 바로 목록: ?profile=… 이 있으면 그것, 로그인했고 대표 조건(완성)이 있으면 그것
  useEffect(() => {
    if (!full) return;
    const id = new URLSearchParams(window.location.search).get("profile")
      ?? me?.profiles.find((p) => p.is_main && p.status === "done")?.id;
    if (!id) return;
    getProfile(id).then((p) => {
      setValues(valuesFrom(full, fromFile(p.profile)));
      setLoaded(`'${p.alias}' 조건으로 입력란을 채웠습니다. 저장하지 않는 민감 항목(수급·장애·국가유공자 등)은 필요하면 직접 넣으세요.`);
      setAutoRun(true);
    }).catch((e: AccountError) => e.status === 401 ? null : setError(e.message));
  }, [full, me]);

  const sido = useMemo(() => {
    const r = values["residence_area"];
    if (typeof r !== "string" || !full) return null;
    if ((full.region_groups["경기도"] ?? []).includes(r)) return "경기도";
    return full.region_options.includes(r) && r !== "해당없음" ? r : null;
  }, [values, full]);

  const regions = area === "all" ? null : area === "capital" ? CAPITAL : sido ? [sido] : null;

  async function run(scroll = true) {
    if (!full) return;
    const { profile, errors } = toProfile(full, values);
    if (errors.length) {
      setError(errors.join(" "));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const r = await findOpen(toFile(profile), { at: at.current, regions, kind: kind === "둘 다" ? null : kind });
      setResult(r);
      if (scroll) setTimeout(() => revealOnNarrow(listRef.current), 0);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  // 저장 조건을 불러왔으면 한 번 바로 판정, 거르기를 바꾸면 다시
  useEffect(() => {
    if (autoRun) {
      setAutoRun(false);
      run(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun]);
  useEffect(() => {
    if (result) run(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, area]);

  const ask = useMemo(() => {
    if (!full || !result?.questions.length) return null;
    const names = new Set(result.questions.flatMap((q) => ASK[q.field] ?? [q.field]));
    const current = toProfile(full, values).profile;
    const fields = full.fields.filter((f) => names.has(f.name) && (current[f.name] === null || current[f.name] === undefined));
    return fields.length ? { ...full, fields, notes: [], collapsed: [], sections: [...new Set(fields.map((f) => f.section))] } : null;
  }, [full, result, values]);

  if (!basic || !full) {
    return error ? <p role="alert" className="text-sm text-red-700">{error}</p> : <p className="text-sm text-slate-500">양식을 불러오는 중…</p>;
  }
  const basicForm: Form = { ...basic, fields: basic.fields };
  const areaLabel: Record<Area, string> = { capital: "수도권(서울·경기·인천)", mine: sido ? `내 시·도(${sido})` : "내 시·도(거주지 선택)", all: "전국" };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">청약 흥신소 <span className="text-base font-medium text-slate-500">지금 지원 가능한 LH·SH 공고</span></h1>
        <p className="mt-1 text-sm text-slate-600">
          기본 조건만 넣으면 지금 모집 중인 공고 중 지원할 수 있는 공고를 골라 드립니다. 모르는 항목은 &lsquo;모름&rsquo;으로 두세요 —
          그 정보가 필요한 공고는 &lsquo;지원가능 판단을 위한 추가정보 요청&rsquo;으로 묶어 무엇을 더 넣으면 되는지 알려 드립니다.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="space-y-4 lg:col-span-5">
          <div className={card} data-testid="find-basic">
            {loaded && <p className="mb-3 text-sm text-green-800" data-testid="profile-loaded">{loaded}</p>}
            <ProfileForm form={basicForm} values={values} onChange={setValues} />
            <fieldset className="mt-5 space-y-2 text-sm">
              <legend className="mb-1 font-medium">{basic.filters.kind.label}</legend>
              <div className="flex flex-wrap gap-4">
                {basic.filters.kind.options.map((o) => (
                  <label key={o} className="flex items-center gap-1">
                    <input type="radio" name="kind" checked={kind === o} onChange={() => setKind(o)} />{o}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="mt-4 space-y-2 text-sm">
              <legend className="mb-1 font-medium">지역</legend>
              <div className="flex flex-wrap gap-4">
                {(["capital", "mine", "all"] as Area[]).map((a) => (
                  <label key={a} className="flex items-center gap-1">
                    <input type="radio" name="area" checked={area === a} onChange={() => setArea(a)} />{areaLabel[a]}
                  </label>
                ))}
              </div>
            </fieldset>
            <button type="button" onClick={() => run()} disabled={busy} data-testid="find-run"
              className="mt-6 w-full rounded-md bg-blue-700 py-2.5 font-semibold text-white hover:bg-blue-800 disabled:opacity-50">
              {busy ? "찾는 중…" : "지금 지원 가능한 공고 찾기"}
            </button>
            {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
            <p className="mt-3 text-xs text-slate-500">
              {me ? <>저장한 조건은 <Link href="/me" className="underline">내 조건 등록하기</Link>에서 고칠 수 있습니다. </>
                : <>입력한 조건은 서버에 저장하지 않습니다. </>}
              전체 조건·지난 공고·What-if는 <Link href="/find/all" className="underline" data-testid="find-all-link">자세히</Link>에서 봅니다.
            </p>
          </div>
        </div>

        <div ref={listRef} className="scroll-mt-4 space-y-6 lg:col-span-7">
          {!result ? (
            <div className={`${card} text-sm text-slate-600`}>
              <span className="hidden lg:inline">왼쪽</span><span className="lg:hidden">위</span>에 기본 조건을 넣고 &lsquo;지금 지원 가능한 공고
              찾기&rsquo;를 누르면 지금 모집 중인 공고가 여기에 나옵니다.
            </div>
          ) : (
            <FindList result={result}>
              {ask && (
                <div className={`${card} border-amber-300`} data-testid="find-questions">
                  <h2 className="mb-1 text-base font-semibold">이것만 알려 주시면 더 판정합니다</h2>
                  <p className="mb-3 text-xs text-slate-600">
                    {result.questions.map((q) => `${q.label}(공고 ${q.notices}건)`).join(" · ")} — 아는 대로 넣고 다시 찾으면 그 공고들이 판정됩니다.
                  </p>
                  <ProfileForm form={ask} values={values} onChange={setValues} />
                  <div className="mt-4 flex justify-end">
                    <button type="button" onClick={() => run(false)} disabled={busy} data-testid="find-rejudge"
                      className="w-full rounded-md bg-amber-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-50 sm:w-auto">
                      다시 찾기
                    </button>
                  </div>
                </div>
              )}
            </FindList>
          )}
        </div>
      </div>
    </div>
  );
}
