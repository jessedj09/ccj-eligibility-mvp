// 판정 API(api/main.py) 호출과 응답 형식. 화면은 판정 로직을 갖지 않는다 — 받은 결과를 보여 주기만 한다.
export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export type Window = { start: string; end: string; page: number };

export type Identification = {
  status: "REGISTERED" | "SAME_NOTICE_OTHER_FILE" | "UNREGISTERED" | "UNREADABLE";
  notice_id: string | null;
  reason: string;
  issuer: string | null;
  program: string | null;
  announcement: string | null;
  pages: number;
  windows: Window[];
  similar: string[];
};

export type UnsupportedLayer = { name: string; note: string; page: number | null };

type RegisteredJudge = { notice_id: string; title: string; layers: string[]; unsupported_layers: UnsupportedLayer[] };

export type Judge =
  | ({ by: "registered" } & RegisteredJudge)
  | ({ by: "confirm" } & RegisteredJudge)
  | { by: "analysis"; program: string; announcement_date: string; layers: string[]; grades: Record<string, string> }
  | { by: "none"; reason: string; auto_public?: boolean; supported_programs?: string[]; registered?: number };

export type UploadResult = { sha256: string; identification: Identification; judge: Judge };

export type FieldType = "age" | "select" | "tri" | "bool" | "int" | "amount" | "car" | "date" | "children" | "region";

export type Field = {
  name: string;
  label: string;
  type: FieldType;
  section: string;
  options?: (string | number)[];
  default?: string | number | boolean;
  unknown?: boolean;
  nullable?: boolean;
  min?: number;
  max?: number;
  help?: string;
  scope?: string[];
  show_if?: { field: string; in: (string | number)[] };
};

export type Form = {
  announcement_date: string | null; // 찾기 양식(/match/form)은 공고·계층이 없다
  layer: string | null;
  notes: string[];
  sections: string[];
  section_titles: Record<string, string>;
  collapsed?: string[];
  region_options: string[];
  region_groups: Record<string, string[]>;
  unknown: string;
  fields: Field[];
};

export type Reason = { rule_id: string; description: string; source_ref: string };
export type Review = Reason & { code: string; detail: string };
export type Track = { track_id: string; label: string; verdict: string; failed: Reason[]; unknown: Reason[]; review: Review[] };

export type Result = {
  notice_id: string;
  layer: string;
  verdict: "ELIGIBLE" | "INELIGIBLE" | "NEEDS_INFO" | "MANUAL_REVIEW" | "NOT_OFFERED";
  headline: string;
  score: number | null;
  matched: Reason[];
  failed: Reason[];
  unknown: Reason[];
  review: Review[];
  tracks: Track[];
  notes: string[];
  display: { group: string; title: string; icon: string; todo: string };
  checks: { kind: string; page: number | null; text: string }[];
  common_note: string;
};

export type NoticeSummary = {
  notice_id: string;
  title: string;
  issuer: string | null;
  program: string | null;
  announcement_date: string;
  layers: string[];
  schedule: { code: string; text: string; applicable: boolean };
};

export type Target = { notice_id: string } | { sha256: string };

/** 내 조건 저장 파일(ccj-profile/1) — 판정 API /match·/whatif 요청 본문과 같은 형식. 서버는 저장하지 않는다. */
export type ProfileFile = { schema: "ccj-profile/1"; master: Record<string, unknown>; common: Record<string, unknown> };

export type ScheduleStatus = {
  code: "OPEN" | "UPCOMING" | "CLOSED" | "UNKNOWN";
  text: string;
  applicable: boolean;
  window: { label: string; start: string; end: string } | null;
};

export type Explanation = Omit<Result, "display" | "checks" | "common_note">;

export type MatchItem = {
  notice_id: string;
  title: string;
  layer: string;
  verdict: Result["verdict"];
  issuer: string | null;
  program: string | null;
  announcement_date: string;
  display: Result["display"];
  eligible_tracks: string[];
  schedule: ScheduleStatus;
  windows: { label: string; start: string; end: string }[];
  schedule_note: string | null;
  explanation: Explanation;
};

export type Threshold = {
  field: string;
  label: string;
  scope: string;
  current: number;
  limit: number;
  review_limit: number | null;
  gap: number;
};

export type NearMiss = { notice_id: string; title: string; layer: string; condition: string; after: string; thresholds: Threshold[] };

export type MatchResult = {
  at: string;
  only_open: boolean;
  counts: Partial<Record<Result["verdict"], number>>;
  notices_total: number;
  schedule_counts: { OPEN: number; UPCOMING: number; CLOSED: number };
  missing_inputs: Record<string, number>;
  common_note: string;
  whatif_caveat: string;
  matches: MatchItem[];
  near_misses: NearMiss[];
};

export type Scenario = "marry" | "prenuptial" | "move" | "separate";

export type WhatIfParams = {
  marriage_date?: string | null;
  spouse_income?: number | null;
  spouse_assets?: number | null;
  spouse_car?: number | null;
  spouse_has_home?: boolean;
  dual_income?: boolean;
  region?: string | null;
};

type Counts3 = { ELIGIBLE: number; HOLD: number; INELIGIBLE: number };
type NoticeRef = { notice_id: string; title: string; layer: string };

export type WhatIfResult = {
  scenario: Scenario;
  name: string;
  caveat: string;
  before: Counts3;
  after: Counts3;
  gained: NoticeRef[];
  lost: (NoticeRef & { reason: string })[];
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// 서버 시동 안내 — 판정 서버(Render 무료 요금제)는 15분 쉬면 잠들고, 그 뒤 첫 요청은 20초~1분 걸린다.
// 잠들어 있을 수 있을 때(처음이거나 마지막 응답이 14분 넘게 전) 요청이 SLOW_MS보다 오래 걸리면 화면(ServerWaking)이 안내한다.
// 서버가 깨어 있는데 느린 요청(큰 PDF 올리기 등)에는 안내하지 않는다.
export const SLOW_MS = 2500;
const AWAKE_MS = 14 * 60 * 1000;
let lastResponse = 0;
let waiting = 0;
const listeners = new Set<(waking: boolean) => void>();

export function onWaking(fn: (waking: boolean) => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

function setWaiting(delta: number) {
  waiting += delta;
  listeners.forEach((fn) => fn(waiting > 0));
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  let flagged = false;
  const timer = Date.now() - lastResponse > AWAKE_MS
    ? setTimeout(() => { flagged = true; setWaiting(1); }, SLOW_MS) : undefined;
  try {
    res = await fetch(API_BASE + path, init);
    lastResponse = Date.now();
  } catch {
    throw new ApiError(0, `판정 서버(${API_BASE})에 연결할 수 없습니다. 서버가 켜져 있는지 확인하세요.`);
  } finally {
    clearTimeout(timer);
    if (flagged) setWaiting(-1);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

export function upload(file: File): Promise<UploadResult> {
  const fd = new FormData();
  fd.append("file", file);
  return call("/upload", { method: "POST", body: fd });
}

export function getForm(target: Target, layer: string): Promise<Form> {
  const q = new URLSearchParams({ layer, ...target });
  return call(`/form?${q}`);
}

export function evaluate(target: Target, layer: string, profile: Record<string, unknown>): Promise<Result> {
  return call("/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...target, layer, profile }),
  });
}

export async function listNotices(): Promise<NoticeSummary[]> {
  const j = await call<{ notices: NoticeSummary[] }>("/notices");
  return j.notices;
}

export function getMatchForm(): Promise<Form> {
  return call("/match/form");
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function match(profile: ProfileFile, at: string | null, onlyOpen: boolean): Promise<MatchResult> {
  return call("/match", post({ profile, at, only_open: onlyOpen }));
}

export function whatIf(profile: ProfileFile, scenario: Scenario, params: WhatIfParams, at: string | null,
  onlyOpen: boolean): Promise<WhatIfResult> {
  return call("/whatif", post({ profile, scenario, ...params, at, only_open: onlyOpen }));
}

/** 화면을 열자마자 서버를 깨운다 — 사용자가 입력하는 동안 시동이 끝나게. 실패해도 조용히 둔다(실제 요청이 오류를 보인다). */
export function wake(): void {
  call("/health").catch(() => {});
}
