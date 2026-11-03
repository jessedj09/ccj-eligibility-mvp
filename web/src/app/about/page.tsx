// 이용 안내 — 판정 범위·한계, 개인정보 처리, 올린 공고문 처리, 문의. 베타 공개 전 준비(C9).
import type { Metadata } from "next";

export const metadata: Metadata = { title: "이용 안내 · 청약 포청천" };

const card = "rounded-lg border border-slate-200 bg-white p-5 shadow-sm";

// 지원 범위(피드백 A5) — 새 공고 자동 판정 = src/draft.py PASSING, 등록 공고 = rules/notices
const SCOPE: [string, string, string][] = [
  ["LH 행복주택(신혼희망타운 행복주택 포함)", "판정", "판정"],
  ["LH 청년 매입임대", "판정", "판정"],
  ["LH 신혼·신생아 매입임대 Ⅰ·Ⅱ", "판정", "판정"],
  ["LH 든든전세", "판정", "판정"],
  ["SH 미리내집(신혼·신생아 매입임대)", "판정", "판정"],
  ["SH 장기전세", "판정", "판정"],
  ["SH 장기미임대 매입임대", "판정", "판정"],
  ["LH 국민임대", "판정", "판정"],
  ["SH 국민임대(일반·주거약자)", "판정", "판정"],
  ["SH 영구임대(1순위 신분별)", "판정", "판정"],
  ["LH 고령자복지주택(영구임대형)", "판정", "판정"],
  ["LH 영구임대", "판정", "판정"],
  ["LH 통합공공임대(일반형)", "판정", "판정"],
  ["LH 공공임대(10년·분양전환·50년) 예비입주자", "판정", "판정"],
  ["LH 신혼희망타운(공공분양)", "판정", "판정"],
  ["LH 공공분양(다자녀·노부모·생애최초·신혼부부·신생아 특별공급, 일반공급)", "판정", "판정"],
  ["SH 토지임대부 분양(청년·신혼부부·생애최초·신생아 특별공급, 일반공급)", "판정", "판정"],
  ["입주자격 완화 공고, 통합공공임대 일자리연계형", "—", "판정하지 않음(이유 안내)"],
  ["SH 나눔형 분양, 기관추천 특별공급, 공공임대 최초 입주자 모집", "—", "판정하지 않음(사업 이름만 안내)"],
];

export default function About() {
  return (
    <div className="mx-auto max-w-3xl space-y-5 text-sm leading-relaxed text-slate-800">
      <h1 className="text-xl font-bold sm:text-2xl">이용 안내</h1>
      <p className="text-slate-600">청약 포청천 — 청약 지원자격 판정 AI</p>

      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">무엇을 판정하나요</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>LH·SH 공공임대 입주자모집공고의 <b>신청 자격(필수요건)</b>을 공고문 원문 기준으로 판정합니다.</li>
          <li>순위·가점·추첨·당첨 여부는 판정하지 않습니다.</li>
          <li>등록된 공고는 사람이 원문과 대조해 검증한 규칙으로, 새로 올린 공고는 자동으로 읽은 규칙으로 판정합니다. 자동으로 읽은 공고는
            확실하지 않은 조건이 결론을 바꿀 수 있으면 &lsquo;보류&rsquo;로 두고 확인할 원문 위치를 알려 드립니다.</li>
          <li>아직 판정하지 않는 사업(분양 등)의 공고는 무엇인지만 알려 드립니다.</li>
        </ul>
      </section>

      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">지원 범위</h2>
        <p className="mb-3">사업마다 판정하는 방법이 다릅니다. &lsquo;등록 공고&rsquo;는 사람이 원문과 대조해 검증한 공고이고(목록에서 고르기),
          &lsquo;새 공고 자동 판정&rsquo;은 처음 올린 공고문을 자동으로 읽어 판정하는 것입니다. 원문에서 확인하지 못한 조건이나 판정 틀에
          없는 조건이 있으면 &lsquo;지원 가능&rsquo; 대신 &lsquo;보류&rsquo;로 두고 확인할 원문 위치를 알려 드립니다.</p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[28rem] text-left text-sm" data-testid="scope-table">
            <thead className="border-b border-slate-200 text-xs text-slate-500">
              <tr>
                <th className="py-1.5 pr-3 font-medium">사업</th>
                <th className="py-1.5 pr-3 font-medium">등록 공고 판정</th>
                <th className="py-1.5 font-medium">새 공고 자동 판정</th>
              </tr>
            </thead>
            <tbody>
              {SCOPE.map(([name, registered, auto]) => (
                <tr key={name} className="border-b border-slate-100 align-top">
                  <td className="py-1.5 pr-3">{name}</td>
                  <td className="py-1.5 pr-3">{registered}</td>
                  <td className="py-1.5">{auto}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-500">2026년 11월 기준. 판정하지 않는 공고를 올리면 &lsquo;판정하지 않음&rsquo;과 그 이유를 알려
          드립니다 — 지원 불가라는 뜻이 아닙니다.</p>
      </section>

      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">판정 결과의 한계</h2>
        <p>판정 근거는 조건별로 표시한 공고문 원문입니다. <b>최종 자격은 공고 기관(LH·SH)의 서류 심사로 확정</b>됩니다. 이 서비스의 판정은
          신청 여부를 정하는 데 참고하시고, 신청 전 공고문 원문과 기관 안내(LH 1600-1004 / SH 1600-3456)를 꼭 확인하세요. 접수 일정은 공고 이후
          바뀔 수 있습니다.</p>
      </section>

      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">개인정보 처리</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li><b>입력한 조건(나이·소득·자산 등)은 저장하지 않습니다.</b> 판정할 때 서버로 보내고, 결과를 돌려준 뒤 남기지 않습니다.</li>
          <li>&lsquo;내 조건 파일로 저장&rsquo;은 이 기기(브라우저)에만 파일로 내려받습니다. 서버에는 올라가지 않습니다.</li>
          <li>이용 통계는 날짜별 건수(업로드·판정 수)만 셉니다. 접속 주소(IP)는 저장하지 않습니다.</li>
        </ul>
      </section>

      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">올린 공고문의 처리</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>공고문은 기관이 공개한 문서입니다. 같은 공고를 다른 분이 올렸을 때 바로 판정하도록, 공고문에서 읽은 내용(사업·공고일·조건)과
            분석 결과를 저장합니다.</li>
          <li>LH·SH 공고문 파일은 정확도 확인을 위해 최대 14일 보관한 뒤 지웁니다. 공고문이 아닌 파일은 보관하지 않습니다.</li>
          <li>개인정보가 들어 있는 문서(계약서·증명서 등)는 올리지 마세요.</li>
        </ul>
      </section>

      <section className={card}>
        <h2 className="mb-2 text-base font-semibold">이용 제한</h2>
        <p>공고문 PDF는 20MB까지 올릴 수 있습니다. 처음 올리는 큰 공고문은 분석에 1~2분 걸릴 수 있고, 같은 공고를 다시 올리면 바로 결과가
          나옵니다. 등록된 공고는 &lsquo;목록에서 고르기&rsquo;로 바로 판정할 수 있습니다.</p>
      </section>
    </div>
  );
}
