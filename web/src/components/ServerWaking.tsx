"use client";
// 서버 시동 안내 — 잠든 판정 서버를 깨우는 동안(첫 요청이 오래 걸릴 때) 화면 위에 띄운다. 언제 띄울지는 lib/api.ts가 정한다.
import { useEffect, useState } from "react";
import { onWaking, wake } from "@/lib/api";

export default function ServerWaking() {
  const [waking, setWaking] = useState(false);
  useEffect(() => {
    const off = onWaking(setWaking);
    wake();
    return off;
  }, []);
  if (!waking) return null;
  return (
    <div role="status" data-testid="server-waking"
      className="sticky top-0 z-20 border-b border-amber-300 bg-amber-50 px-4 py-2.5 text-center text-sm font-medium text-amber-900">
      ⏳ 서버 시동중입니다. 잠시만 기다려주세요.
    </div>
  );
}
