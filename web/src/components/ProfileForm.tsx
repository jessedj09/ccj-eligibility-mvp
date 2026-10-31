"use client";
// 판정 API /form이 준 양식대로 입력란을 그린다 — 어떤 항목을 언제 묻는지는 서버(src/form_spec.py)가 정한다.
import { useMemo } from "react";
import type { Field, Form } from "@/lib/api";

export type Values = Record<string, unknown>;
type AgeValue = { mode: "birth" | "age"; birth: string; age: string };
type ChildrenValue = { has: boolean; dates: string[] };

const UNKNOWN = "__unknown__";

export function initialValues(form: Form): Values {
  const v: Values = {};
  for (const f of form.fields) {
    switch (f.type) {
      case "age":
        v[f.name] = { mode: "birth", birth: "", age: "" } satisfies AgeValue;
        break;
      case "children":
        v[f.name] = { has: false, dates: [] } satisfies ChildrenValue;
        break;
      case "bool":
        v[f.name] = Boolean(f.default);
        break;
      case "int":
        v[f.name] = String(f.default ?? f.min ?? "");
        break;
      case "select":
        v[f.name] = f.default !== undefined ? String(f.default) : UNKNOWN;
        break;
      case "tri":
      case "region":
        v[f.name] = UNKNOWN;
        break;
      case "car":
        v[f.name] = { unknown: false, amount: "" };
        break;
      default:
        v[f.name] = "";
    }
  }
  return v;
}

export function visible(f: Field, values: Values): boolean {
  if (!f.show_if) return true;
  return f.show_if.in.map(String).includes(String(values[f.show_if.field]));
}

const digits = (s: string) => s.replace(/[^0-9]/g, "");

/** 입력값 → 판정 API의 profile(HouseholdProfile 항목). 숨긴 항목·모름은 null(또는 뺀다). */
export function toProfile(form: Form, values: Values): { profile: Record<string, unknown>; errors: string[] } {
  const profile: Record<string, unknown> = {};
  const errors: string[] = [];
  for (const f of form.fields) {
    if (!visible(f, values)) continue;
    const v = values[f.name];
    switch (f.type) {
      case "age": {
        const a = v as AgeValue;
        if (a.mode === "birth") {
          if (!a.birth) errors.push("생년월일을 넣어 주세요.");
          else profile.birth_date = a.birth;
        } else {
          if (a.age === "") errors.push("나이를 넣어 주세요.");
          else profile.age = Number(a.age);
        }
        break;
      }
      case "children": {
        const c = v as ChildrenValue;
        if (c.has && c.dates.some((d) => !d)) errors.push("자녀 생년월일(태아는 출산예정일)을 모두 넣어 주세요.");
        profile[f.name] = c.has ? c.dates.filter(Boolean) : [];
        break;
      }
      case "bool":
        profile[f.name] = Boolean(v);
        break;
      case "int":
        profile[f.name] = v === "" ? null : Number(v);
        break;
      case "select": {
        const opt = (f.options ?? []).find((o) => String(o) === v);
        profile[f.name] = v === UNKNOWN || opt === undefined ? null : opt;
        break;
      }
      case "region":
        profile[f.name] = v === UNKNOWN ? null : v;
        break;
      case "tri":
        profile[f.name] = v === "yes" ? true : v === "no" ? false : null;
        break;
      case "amount":
        profile[f.name] = v === "" ? null : Number(digits(String(v)));
        break;
      case "car": {
        const c = v as { unknown: boolean; amount: string };
        profile[f.name] = c.unknown ? "확인불가" : c.amount === "" ? null : Number(digits(c.amount));
        break;
      }
      case "date":
        if (!v && !f.nullable) errors.push(`${f.label}을(를) 넣어 주세요.`);
        profile[f.name] = v || null;
        break;
    }
  }
  return { profile, errors };
}

const input =
  "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600";

function money(s: string): string {
  const d = digits(s);
  return d ? Number(d).toLocaleString("ko-KR") : "";
}

function FieldControl({ f, form, value, set }: { f: Field; form: Form; value: unknown; set: (v: unknown) => void }) {
  const id = `f-${f.name}`;
  switch (f.type) {
    case "age": {
      const a = value as AgeValue;
      return (
        <div className="space-y-2">
          <div className="flex gap-4 text-sm">
            {(["birth", "age"] as const).map((m) => (
              <label key={m} className="flex items-center gap-1">
                <input type="radio" name={id} checked={a.mode === m} onChange={() => set({ ...a, mode: m })} />
                {m === "birth" ? "생년월일" : "만 나이"}
              </label>
            ))}
          </div>
          {a.mode === "birth" ? (
            <input id={id} type="date" className={input} value={a.birth} max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => set({ ...a, birth: e.target.value })} aria-label="생년월일" />
          ) : (
            <input id={id} type="number" min={0} max={120} className={input} value={a.age} placeholder="공고일 기준 만 나이"
              onChange={(e) => set({ ...a, age: e.target.value })} aria-label="만 나이" />
          )}
        </div>
      );
    }
    case "select":
      return (
        <select id={id} className={input} value={String(value)} onChange={(e) => set(e.target.value)}>
          {f.unknown && <option value={UNKNOWN}>{form.unknown}</option>}
          {(f.options ?? []).map((o) => (
            <option key={String(o)} value={String(o)}>{String(o)}</option>
          ))}
        </select>
      );
    case "region":
      return (
        <select id={id} className={input} value={String(value)} onChange={(e) => set(e.target.value)}>
          <option value={UNKNOWN}>{form.unknown}</option>
          <option value={form.region_options[0]}>{form.region_options[0]}</option>
          {Object.entries(form.region_groups).map(([g, names]) => (
            <optgroup key={g} label={g}>
              {names.map((n) => (
                <option key={n} value={n}>{g === "경기도" ? `경기 ${n}` : n}</option>
              ))}
            </optgroup>
          ))}
        </select>
      );
    case "tri":
      return (
        <select id={id} className={input} value={String(value)} onChange={(e) => set(e.target.value)}>
          <option value={UNKNOWN}>{form.unknown}</option>
          <option value="yes">예</option>
          <option value="no">아니오</option>
        </select>
      );
    case "bool":
      return (
        <label className="flex items-center gap-2 text-sm">
          <input id={id} type="checkbox" checked={Boolean(value)} onChange={(e) => set(e.target.checked)} />
          예
        </label>
      );
    case "int":
      return (
        <input id={id} type="number" className={input} min={f.min} max={f.max} value={String(value)}
          onChange={(e) => set(e.target.value)} />
      );
    case "amount":
      return (
        <div className="flex items-center gap-2">
          <input id={id} inputMode="numeric" className={input} value={money(String(value))} placeholder="모르면 비워 두세요"
            onChange={(e) => set(digits(e.target.value))} />
          <span className="text-sm text-slate-500">원</span>
        </div>
      );
    case "car": {
      const c = value as { unknown: boolean; amount: string };
      return (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <input id={id} inputMode="numeric" className={input} disabled={c.unknown} value={money(c.amount)}
              placeholder="없으면 0, 모르면 비워 두세요" onChange={(e) => set({ ...c, amount: digits(e.target.value) })} />
            <span className="text-sm text-slate-500">원</span>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={c.unknown} onChange={(e) => set({ ...c, unknown: e.target.checked })} />
            자동차가액 확인불가
          </label>
        </div>
      );
    }
    case "date":
      return <input id={id} type="date" className={input} value={String(value)} onChange={(e) => set(e.target.value)} />;
    case "children": {
      const c = value as ChildrenValue;
      const max = f.max ?? 8;
      const latest = new Date(Date.now() + 300 * 864e5).toISOString().slice(0, 10);
      return (
        <div className="space-y-2">
          <div className="flex gap-4 text-sm">
            {[false, true].map((has) => (
              <label key={String(has)} className="flex items-center gap-1">
                <input type="radio" name={id} checked={c.has === has}
                  onChange={() => set({ has, dates: has && c.dates.length === 0 ? [""] : c.dates })} />
                {has ? "있음" : "없음"}
              </label>
            ))}
          </div>
          {c.has && (
            <div className="space-y-2">
              {c.dates.map((d, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="w-16 text-sm text-slate-600">자녀 {i + 1}</span>
                  <input type="date" className={input} value={d} max={latest} aria-label={`자녀 ${i + 1} 생년월일`}
                    onChange={(e) => set({ ...c, dates: c.dates.map((x, j) => (j === i ? e.target.value : x)) })} />
                  <button type="button" className="text-sm text-slate-500 hover:text-red-600"
                    onClick={() => set({ has: c.dates.length > 1, dates: c.dates.filter((_, j) => j !== i) })}>
                    삭제
                  </button>
                </div>
              ))}
              {c.dates.length < max && (
                <button type="button" className="text-sm text-blue-700 hover:underline"
                  onClick={() => set({ ...c, dates: [...c.dates, ""] })}>
                  + 자녀 추가
                </button>
              )}
            </div>
          )}
        </div>
      );
    }
  }
}

export default function ProfileForm({ form, values, onChange }: { form: Form; values: Values; onChange: (v: Values) => void }) {
  const bySection = useMemo(() => {
    const m: Record<string, Field[]> = {};
    for (const f of form.fields) (m[f.section] ??= []).push(f);
    return m;
  }, [form]);

  return (
    <div className="space-y-6">
      {form.notes.length > 0 && (
        <ul className="space-y-1 rounded-md bg-slate-50 p-3 text-sm text-slate-700">
          {form.notes.map((n) => (
            <li key={n}>📌 {n}</li>
          ))}
        </ul>
      )}
      {form.sections.filter((s) => bySection[s]?.length).map((s) => (
        <section key={s}>
          <h3 className="mb-3 border-b border-slate-200 pb-1 text-base font-semibold text-slate-800">
            {form.section_titles[s] ?? s}
          </h3>
          <div className="grid grid-cols-2 gap-x-6 gap-y-5">
            {bySection[s].filter((f) => visible(f, values)).map((f) => (
              <div key={f.name} className={f.type === "children" ? "col-span-2" : ""} data-field={f.name}>
                <label htmlFor={`f-${f.name}`} className="mb-1 block text-sm font-medium text-slate-800">{f.label}</label>
                <FieldControl f={f} form={form} value={values[f.name]}
                  set={(v) => onChange({ ...values, [f.name]: v })} />
                {f.scope && <p className="mt-1 text-xs text-blue-800">이 계층 기준: {f.scope.join(" / ")}</p>}
                {f.help && <p className="mt-1 text-xs text-slate-500">{f.help}</p>}
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
