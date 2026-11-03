// 회원 기능 중계(서버) — 로그인 토큰은 httpOnly 쿠키에만 두고, 판정 API(/auth·/me)에 Authorization: Bearer로 붙여 보낸다.
// 브라우저 스크립트는 토큰을 볼 수 없다(XSS로 토큰을 훔치지 못하게). 로그인·가입 확인·비밀번호 재설정 응답의 token은 쿠키로 옮기고 지운다.
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const API = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const COOKIE = "ccj_session";
const ALLOWED = /^(auth\/(signup\/start|signup\/verify|login|logout|password\/start|password\/verify)|me(\/profiles(\/[0-9a-f-]{36}(\/match)?)?)?)$/;
const ISSUES_TOKEN = new Set(["auth/signup/verify", "auth/login", "auth/password/verify"]);

async function relay(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const path = (await ctx.params).path.join("/");
  if (!ALLOWED.test(path)) return NextResponse.json({ detail: "없는 주소입니다." }, { status: 404 });
  const jar = await cookies();
  const token = jar.get(COOKIE)?.value;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const body = req.method === "GET" || req.method === "DELETE" ? undefined : await req.text();
  let res: Response;
  try {
    res = await fetch(`${API}/${path}`, { method: req.method, headers, body, cache: "no-store" });
  } catch {
    return NextResponse.json({ detail: "판정 서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요." }, { status: 503 });
  }
  const data = await res.json().catch(() => ({}));
  const out = NextResponse.json(ISSUES_TOKEN.has(path) && res.ok ? { ok: true } : data, { status: res.status });
  const secure = process.env.NODE_ENV === "production";
  if (ISSUES_TOKEN.has(path) && res.ok && data.token) {
    out.cookies.set(COOKIE, data.token, { httpOnly: true, secure, sameSite: "lax", path: "/", maxAge: 30 * 24 * 3600 });
  }
  if ((path === "auth/logout" || (path === "me" && req.method === "DELETE") || res.status === 401) && token) {
    out.cookies.set(COOKIE, "", { httpOnly: true, secure, sameSite: "lax", path: "/", maxAge: 0 });
  }
  return out;
}

export { relay as GET, relay as POST, relay as PUT, relay as DELETE };
