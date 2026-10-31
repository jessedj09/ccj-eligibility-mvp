// 휴대폰(1단 배치)에서는 입력란·결과가 아래로 쌓여 화면 밖에 생긴다 — 새로 나타난 부분으로 스크롤한다.
// PC(2단 배치, lg 이상)에서는 옆에 바로 보이므로 움직이지 않는다.
export function revealOnNarrow(el: HTMLElement | null): void {
  if (el && window.matchMedia("(max-width: 1023px)").matches) el.scrollIntoView({ behavior: "smooth", block: "start" });
}
