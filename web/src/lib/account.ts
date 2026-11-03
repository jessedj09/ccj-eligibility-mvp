// 회원 기능 호출 — 같은 주소의 중계(/api/account/…, httpOnly 쿠키)로만 부른다. 판정 API 주소를 직접 부르지 않는다.
import type { ProfileFile } from "@/lib/api";

export type ProfileSummary = {
  id: string; alias: string; is_main: boolean; status: "draft" | "done"; filled: number; total: number; updated_at: string;
};
export type StoredProfile = ProfileSummary & { profile: ProfileFile };
export type Me = {
  email: string; created_at: string; consents: Record<string, string>; profiles: ProfileSummary[];
  profile_saving: boolean; not_saved: string[];
};

export class AccountError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(`/api/account/${path}`, {
    method: init?.method ?? (init?.body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json" },
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = (data as { detail?: unknown }).detail;
    throw new AccountError(res.status, typeof d === "string" ? d : "요청을 처리하지 못했습니다.");
  }
  return data as T;
}

/** 로그인 안 했으면 null */
export async function getMe(): Promise<Me | null> {
  try {
    return await call<Me>("me");
  } catch (e) {
    if (e instanceof AccountError && (e.status === 401 || e.status === 503)) return null;
    throw e;
  }
}

export const signupStart = (email: string, password: string, consents: Record<string, boolean>) =>
  call("auth/signup/start", { body: { email, password, consents } });
export const signupVerify = (email: string, code: string) => call("auth/signup/verify", { body: { email, code } });
export const login = (email: string, password: string) => call("auth/login", { body: { email, password } });
export const logout = () => call("auth/logout", { body: {} });
export const resetStart = (email: string) => call("auth/password/start", { body: { email } });
export const resetVerify = (email: string, code: string, new_password: string) =>
  call("auth/password/verify", { body: { email, code, new_password } });
export const withdraw = () => call("me", { method: "DELETE" });

export const getProfile = (id: string) => call<StoredProfile>(`me/profiles/${id}`);
export const saveProfile = (p: { alias: string; profile: ProfileFile; status: "draft" | "done"; is_main?: boolean }, id?: string) =>
  call<StoredProfile>(id ? `me/profiles/${id}` : "me/profiles", { method: id ? "PUT" : "POST", body: p });
export const deleteProfile = (id: string) => call(`me/profiles/${id}`, { method: "DELETE" });

/** 로그인 뒤 돌아갈 곳(같은 사이트 안의 경로만) */
export function nextPath(raw: string | null, fallback = "/me"): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : fallback;
}
