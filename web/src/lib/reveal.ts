// 새로 나타난 부분(입력란·결과·오류)이 화면 밖에 생기면 그곳으로 스크롤한다.
// - reveal: 어느 화면에서나 — 공고 판정의 결과·오류는 PC에서도 긴 입력란 아래·위에 생긴다.
// - revealOnNarrow: 휴대폰(1단 배치, lg 미만)에서만 — PC 2단 배치에서는 옆 칸에 바로 보이는 것(입력란, 공고 찾기 결과).
export function reveal(el: HTMLElement | null): void {
  if (!el) return;
  const r = el.getBoundingClientRect();
  if (r.top < 0 || r.top > window.innerHeight * 0.6) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function revealOnNarrow(el: HTMLElement | null): void {
  if (el && window.matchMedia("(max-width: 1023px)").matches) el.scrollIntoView({ behavior: "smooth", block: "start" });
}
