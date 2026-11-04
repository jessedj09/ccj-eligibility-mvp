// 이용약관(베타) — 판정 결과의 성격·회원의 의무·서비스 변경.
import type { Metadata } from "next";

export const metadata: Metadata = { title: "이용약관 · 청약 포청천" };

const card = "rounded-lg border border-slate-200 bg-white p-5 shadow-sm";

export default function Terms() {
  return (
    <div className="mx-auto max-w-3xl space-y-5 text-sm leading-relaxed text-slate-800">
      <h1 className="text-xl font-bold sm:text-2xl">이용약관</h1>
      <p className="text-slate-600">시행일 2026년 11월(베타).</p>
      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">1. 서비스</h2>
        <p>청약 포청천은 LH·SH 입주자모집공고문을 근거로 이용자가 입력한 조건의 신청 자격(필수요건)을 판정해 보여 주는 서비스입니다. 순위·가점·추첨·당첨
          여부는 판정하지 않습니다.</p>
      </section>
      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">2. 판정 결과의 성격</h2>
        <p>판정 결과는 공고문 원문을 근거로 한 참고 정보입니다. <b>최종 자격은 공고 기관(LH·SH)의 서류 심사로 확정</b>되며, 이용자는 신청 전 공고문 원문과
          기관 안내를 확인해야 합니다. 서비스는 이용자가 입력한 정보가 사실과 다르거나 공고가 바뀌어 생긴 결과에 대해 책임지지 않습니다.</p>
      </section>
      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">3. 회원</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>회원은 본인의 이메일로 가입하고, 비밀번호를 다른 사람과 공유하지 않습니다.</li>
          <li>회원은 언제든 탈퇴할 수 있고, 탈퇴하면 계정과 저장한 조건이 즉시 지워집니다.</li>
          <li>다른 사람의 정보를 입력하거나 서비스를 비정상적으로 이용(자동 대량 요청 등)하면 이용을 제한할 수 있습니다.</li>
        </ul>
      </section>
      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">4. 변경</h2>
        <p>베타 기간에는 기능과 약관이 바뀔 수 있습니다. 약관이 바뀌면 시행 전에 화면으로 알립니다.</p>
      </section>
    </div>
  );
}
