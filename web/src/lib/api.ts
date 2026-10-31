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
  | { by: "none"; reason: string };

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
  announcement_date: string;
  layer: string;
  notes: string[];
  sections: string[];
  section_titles: Record<string, string>;
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

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, init);
  } catch {
    throw new ApiError(0, `판정 서버(${API_BASE})에 연결할 수 없습니다. 서버가 켜져 있는지 확인하세요.`);
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
