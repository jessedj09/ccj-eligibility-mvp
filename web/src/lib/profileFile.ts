// 입력란 값 ↔ 내 조건 형식(ccj-profile/1). 청약 흥신소(파일 저장·불러오기)와 내 조건 등록하기(서버 저장)가 같이 쓴다.
import type { ProfileFile } from "@/lib/api";

const MASTER = "master.";

/** 입력란 항목 → 저장 형식. 'master.x'는 master(모름이면 뺀다), 그 밖은 common(모름은 null 그대로). */
export function toFile(profile: Record<string, unknown>): ProfileFile {
  const file: ProfileFile = { schema: "ccj-profile/1", master: {}, common: {} };
  for (const [k, v] of Object.entries(profile)) {
    if (k.startsWith(MASTER)) {
      if (v !== null) file.master[k.slice(MASTER.length)] = v;
    } else file.common[k] = v;
  }
  return file;
}

export function fromFile(raw: unknown): Record<string, unknown> {
  const f = raw as Partial<ProfileFile>;
  if (!f || f.schema !== "ccj-profile/1") throw new Error("내 조건 파일 형식이 아닙니다(schema가 'ccj-profile/1'이어야 합니다).");
  const out: Record<string, unknown> = { ...(f.common ?? {}) };
  for (const [k, v] of Object.entries(f.master ?? {})) out[MASTER + k] = v;
  return out;
}
