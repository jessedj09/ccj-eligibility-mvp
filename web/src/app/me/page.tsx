"use client";
// 내 조건 등록하기 — 로그인한 사용자의 조건을 여러 개 저장(별칭·대표·작성 중/완료·완성도). 잡코리아 이력서 등록을 참고했다(2026-11-03).
// 입력 양식은 청약 흥신소와 같고(/match/form), 민감 항목(수급·장애·국가유공자 등)은 저장하지 않아 양식에서 뺀다 — 판정 때 따로 입력.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import ProfileForm, { initialValues, toProfile, valuesFrom, type Values } from "@/components/ProfileForm";
import { AccountError, deleteProfile, getMe, getProfile, saveProfile, withdraw, type Me, type ProfileSummary } from "@/lib/account";
import { getMatchForm, type Form } from "@/lib/api";
import { fromFile, toFile } from "@/lib/profileFile";

const card = "rounded-lg border border-slate-200 bg-white p-5 shadow-sm";
const btn = "rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50";

function Meter({ p }: { p: ProfileSummary }) {
  const pct = p.total ? Math.round((p.filled / p.total) * 100) : 0;
  return (
    <div className="flex items-center gap-2 text-xs text-slate-500" title="입력한 항목 수(모르는 항목은 판정 때 '추가 정보 필요'로 묻습니다)">
      <div className="h-1.5 w-24 rounded bg-slate-200"><div className="h-1.5 rounded bg-blue-600" style={{ width: `${pct}%` }} /></div>
      완성도 {pct}% ({p.filled}/{p.total})
    </div>
  );
}

export default function MyProfiles() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [form, setForm] = useState<Form | null>(null);
  const [editing, setEditing] = useState<{ id?: string; alias: string; values: Values; is_main: boolean } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => getMe().then(setMe).catch((e: AccountError) => setError(e.message)), []);

  useEffect(() => {
    getMe().then((m) => {
      if (!m) router.replace("/login?next=/me");
      setMe(m);
    }).catch((e: AccountError) => setError(e.message));
  }, [router]);

  useEffect(() => {
    if (!me) return;
    getMatchForm().then((f) => setForm({ ...f, fields: f.fields.filter((x) => !me.not_saved.includes(x.name)) }))
      .catch((e: Error) => setError(e.message));
  }, [me]);

  if (me === undefined || (me && !form)) return <p className="text-sm text-slate-500">불러오는 중…</p>;
  if (!me) return null;

  async function open(id?: string) {
    setError("");
    if (!id) return setEditing({ alias: me!.profiles.length ? "새 조건" : "나", values: initialValues(form!), is_main: false });
    try {
      const p = await getProfile(id);
      setEditing({ id, alias: p.alias, values: valuesFrom(form!, fromFile(p.profile)), is_main: p.is_main });
    } catch (e) { setError((e as AccountError).message); }
  }

  async function save(status: "draft" | "done") {
    if (!editing) return;
    const { profile, errors } = toProfile(form!, editing.values);
    if (status === "done" && errors.length) return setError(errors.join(" "));
    setBusy(true); setError("");
    try {
      await saveProfile({ alias: editing.alias, profile: toFile(profile), status, is_main: editing.is_main }, editing.id);
      setEditing(null);
      await refresh();
    } catch (e) { setError((e as AccountError).message); } finally { setBusy(false); }
  }

  async function makeMain(p: ProfileSummary) {
    try {
      const full = await getProfile(p.id);
      await saveProfile({ alias: full.alias, profile: full.profile, status: full.status, is_main: true }, p.id);
      await refresh();
    } catch (e) { setError((e as AccountError).message); }
  }

  async function remove(p: ProfileSummary) {
    if (!confirm(`'${p.alias}' 조건을 지울까요? 되돌릴 수 없습니다.`)) return;
    try { await deleteProfile(p.id); await refresh(); } catch (e) { setError((e as AccountError).message); }
  }

  async function leave() {
    if (!confirm("회원 탈퇴하면 계정과 저장한 조건이 모두 바로 지워지고 되돌릴 수 없습니다. 탈퇴할까요?")) return;
    try { await withdraw(); router.push("/"); router.refresh(); } catch (e) { setError((e as AccountError).message); }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">내 조건 등록하기</h1>
        <p className="mt-1 text-sm text-slate-600">
          조건을 여러 개 저장해 두고(예: 나 / 배우자와 함께 / 내년 결혼 가정) 청약 흥신소에서 바로 판정하세요. 저장한 조건은 암호화해 보관하며
          본인만 볼 수 있습니다. 장애·국가유공자·수급자 같은 민감 항목은 저장하지 않으니 판정할 때 따로 입력해 주세요.
        </p>
      </div>
      {!me.profile_saving && (
        <p role="alert" className="rounded-md bg-amber-50 p-3 text-sm text-amber-800">조건 저장 기능을 준비 중입니다. 잠시 뒤 다시 이용해 주세요.</p>
      )}
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}

      {editing ? (
        <div className={card} data-testid="profile-editor">
          <div className="mb-4 flex flex-wrap items-end gap-4">
            <label className="text-sm">
              <span className="mb-1 block font-medium text-slate-700">조건 이름</span>
              <input className="rounded-md border border-slate-300 px-3 py-1.5 text-base sm:text-sm" maxLength={40} value={editing.alias}
                onChange={(e) => setEditing({ ...editing, alias: e.target.value })} data-testid="profile-alias" />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={editing.is_main} onChange={(e) => setEditing({ ...editing, is_main: e.target.checked })} />
              대표 조건으로
            </label>
          </div>
          <ProfileForm form={form!} values={editing.values} onChange={(v) => setEditing({ ...editing, values: v })} />
          <div className="mt-6 flex flex-wrap justify-end gap-3">
            <button type="button" className={btn} onClick={() => setEditing(null)}>취소</button>
            <button type="button" className={btn} disabled={busy} onClick={() => save("draft")} data-testid="profile-draft">임시 저장</button>
            <button type="button" disabled={busy} onClick={() => save("done")} data-testid="profile-store"
              className="rounded-md bg-blue-700 px-5 py-1.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50">저장</button>
          </div>
        </div>
      ) : (
        <div className={card}>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">저장한 조건 {me.profiles.length}개</h2>
            <button type="button" className={btn} onClick={() => open()} disabled={!me.profile_saving} data-testid="profile-new">+ 새 조건</button>
          </div>
          {me.profiles.length === 0 ? (
            <p className="text-sm text-slate-600">아직 저장한 조건이 없습니다. &lsquo;새 조건&rsquo;으로 시작하거나 청약 흥신소에서 입력한 뒤 저장하세요.</p>
          ) : (
            <ul className="divide-y divide-slate-100" data-testid="profile-list">
              {me.profiles.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div>
                    <div className="font-medium">
                      {p.alias}
                      {p.is_main && <span className="ml-2 rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-800">대표</span>}
                      {p.status === "draft" && <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">작성 중</span>}
                    </div>
                    <Meter p={p} />
                    <div className="text-xs text-slate-400">수정 {p.updated_at.slice(0, 10)}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {p.status === "done" && (
                      <Link href={`/find?profile=${p.id}`} className="rounded-md bg-blue-700 px-3 py-1.5 text-sm text-white hover:bg-blue-800">
                        이 조건으로 공고 찾기
                      </Link>
                    )}
                    <button type="button" className={btn} onClick={() => open(p.id)}>수정</button>
                    {!p.is_main && <button type="button" className={btn} onClick={() => makeMain(p)}>대표로</button>}
                    <button type="button" className={`${btn} text-red-700`} onClick={() => remove(p)}>삭제</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className={`${card} text-sm text-slate-600`}>
        <h2 className="mb-2 text-base font-semibold text-slate-800">계정</h2>
        <p>{me.email} · 가입 {me.created_at.slice(0, 10)}</p>
        <p className="mt-1">1년 동안 로그인하지 않으면 계정과 저장한 조건을 지웁니다. 자세한 내용은{" "}
          <Link href="/privacy" className="underline">개인정보 처리방침</Link>을 보세요.</p>
        <button type="button" onClick={leave} className="mt-3 text-sm text-red-700 underline" data-testid="withdraw">회원 탈퇴</button>
      </div>
    </div>
  );
}
