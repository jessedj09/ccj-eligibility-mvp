// 개인정보 처리방침(베타) — 회원가입·내 조건 저장(2026-11-03 결정). 수집 항목·목적·보관·국외 이전·파기·권리.
import type { Metadata } from "next";

export const metadata: Metadata = { title: "개인정보 처리방침 · 청약 포청천" };

const card = "rounded-lg border border-slate-200 bg-white p-5 shadow-sm";
const th = "border-b border-slate-200 py-1.5 pr-3 text-left text-xs font-medium text-slate-500";
const td = "border-b border-slate-100 py-1.5 pr-3 align-top";

export default function Privacy() {
  return (
    <div className="mx-auto max-w-3xl space-y-5 text-sm leading-relaxed text-slate-800">
      <h1 className="text-xl font-bold sm:text-2xl">개인정보 처리방침</h1>
      <p className="text-slate-600">시행일 2026년 11월(베타). 청약 포청천은 판정에 꼭 필요한 정보만, 이용자가 저장을 선택한 경우에만 보관합니다.</p>

      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">1. 수집하는 정보와 목적</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[30rem]">
            <thead><tr><th className={th}>구분</th><th className={th}>항목</th><th className={th}>목적</th></tr></thead>
            <tbody>
              <tr><td className={td}>회원가입(필수)</td><td className={td}>이메일, 비밀번호(복원할 수 없는 형태로 변환해 저장), 동의 일시</td>
                <td className={td}>회원 확인·로그인, 비밀번호 재설정 안내</td></tr>
              <tr><td className={td}>내 조건(선택)</td><td className={td}>생년월일, 혼인 상태·혼인일, 자녀 생년월일, 가구원수, 소득·자산·자동차가액, 주택 소유,
                거주지, 청약통장 가입 정보 등 이용자가 입력한 판정 조건</td><td className={td}>저장한 조건으로 공고 지원 자격 판정</td></tr>
              <tr><td className={td}>판정만 할 때</td><td className={td}>판정에 입력한 조건</td>
                <td className={td}>그 자리에서 판정하고 저장하지 않음</td></tr>
            </tbody>
          </table>
        </div>
        <p className="mt-2">이름·전화번호·주민등록번호는 받지 않습니다. <b>장애·국가유공자·기초생활 수급 등 민감할 수 있는 항목은 저장하지 않고</b>, 판정할 때만
          입력받습니다.</p>
      </section>

      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">2. 보관 기간과 파기</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>회원 탈퇴하면 계정과 저장한 조건을 <b>즉시</b> 지웁니다.</li>
          <li>1년 동안 로그인하지 않은 계정은 계정과 저장한 조건을 지웁니다.</li>
          <li>이메일 인증 코드는 10분 뒤 효력이 없어지고, 로그인 상태는 30일 뒤 끝납니다.</li>
        </ul>
      </section>

      <section className={card} id="overseas">
        <h2 className="mb-2 text-base font-semibold">3. 처리 위탁과 국외 이전</h2>
        <p className="mb-2">회원 정보와 저장한 조건은 아래 업체의 서버에 보관·처리됩니다. 데이터베이스가 국외(싱가포르)에 있어 가입할 때 국외 이전에 동의를 받습니다.</p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[30rem]">
            <thead><tr><th className={th}>업체(국가)</th><th className={th}>하는 일</th><th className={th}>이전 항목·방법</th><th className={th}>보유 기간</th></tr></thead>
            <tbody>
              <tr><td className={td}>Neon(데이터베이스, AWS 싱가포르)</td><td className={td}>회원 정보·저장한 조건 보관</td>
                <td className={td}>1의 회원가입·내 조건 항목, 가입·저장할 때 암호화된 통신으로 전송(내 조건은 암호화해 저장)</td>
                <td className={td}>탈퇴·1년 미접속 파기 때까지</td></tr>
              <tr><td className={td}>Render(판정 서버, 싱가포르)</td><td className={td}>판정·회원 요청 처리</td>
                <td className={td}>요청을 처리하는 동안만(저장하지 않음)</td><td className={td}>처리 즉시</td></tr>
              <tr><td className={td}>Vercel(화면 서버, 미국 등)</td><td className={td}>화면 제공·로그인 상태 전달</td>
                <td className={td}>로그인 상태 쿠키(이메일·조건은 보관하지 않음)</td><td className={td}>로그인 유지 기간(30일)</td></tr>
              <tr><td className={td}>메일 발송 대행(베타 공개 전 확정)</td><td className={td}>인증 코드 메일 발송</td>
                <td className={td}>이메일 주소·인증 코드</td><td className={td}>발송 즉시(업체 보관 정책은 확정 때 적습니다)</td></tr>
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-500">국외 이전에 동의하지 않으면 회원가입을 할 수 없지만, 로그인 없이 판정·공고 찾기는 그대로 이용할 수 있습니다.</p>
      </section>

      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">4. 안전 조치</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>비밀번호는 복원할 수 없는 방식(scrypt)으로만 저장하고, 저장한 조건은 암호화(AES-GCM)해 보관합니다.</li>
          <li>모든 통신은 암호화(HTTPS)하고, 로그인 정보는 화면의 스크립트가 읽을 수 없는 쿠키로만 다룹니다.</li>
          <li>저장한 조건은 본인만 볼 수 있습니다. 운영 기록·통계에는 개인정보를 남기지 않습니다.</li>
        </ul>
      </section>

      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">5. 이용자의 권리</h2>
        <p>&lsquo;내 조건 등록하기&rsquo;에서 저장한 조건을 언제든 보고 고치고 지울 수 있고, 같은 화면에서 회원 탈퇴(즉시 파기)를 할 수 있습니다.
          개인정보 보호책임자와 문의처는 베타 공개 전에 이 방침에 적습니다.</p>
      </section>
    </div>
  );
}
