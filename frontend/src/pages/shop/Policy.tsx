// 이용약관 · 개인정보처리방침 · 교환·반품 안내 — 공장 설정값(상호·대표·사업자번호…)을 채워 넣은 기본 문구
// 빈 설정은 '(등록 예정)' 대신 그 줄을 빼요. 교환·반품은 관리자에서 고친 글이 있으면 그걸 보여 줘요.
import type { ReactNode } from "react";
import type { ShopInfo } from "../../api/types";

export type PolicyKind = "terms" | "privacy" | "refund";
export const POLICY_TITLE: Record<PolicyKind, string> = { terms: "이용약관", privacy: "개인정보처리방침", refund: "교환·반품 안내" };

function Sec({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="border-t border-line py-4 first:border-t-0">
      <h2 className="mb-2 font-bold text-ink">
        제{n}조 {title}
      </h2>
      <div className="space-y-1.5 break-keep text-[15px] leading-relaxed text-stone-700">{children}</div>
    </section>
  );
}

export const DEFAULT_REFUND = [
  "받으신 날부터 7일 안에 전화로 교환·반품을 신청할 수 있어요.",
  "마음이 바뀐 경우: 뚜껑을 열지 않은 상품만 받아요. 오가는 택배비는 손님이 내요.",
  "상품이 잘못 왔거나 깨지거나 상한 경우: 사진과 함께 알려 주시면 택배비는 공장이 내고, 같은 상품으로 바꿔 드리거나 환불해 드려요.",
  "열어서 쓰셨거나, 시간이 지나 다시 팔 수 없게 된 경우에는 식품 특성상 교환·반품이 어려워요.",
  "환불은 돌아온 상품을 확인한 뒤 3영업일 안에 해 드려요. 계좌로 입금하셨으면 계좌로, 카드로 결제하셨으면 카드 결제를 취소해 드려요.",
].join("\n");

export function PolicyBody({ kind, info }: { kind: PolicyKind; info: ShopInfo }) {
  const b = info.business ?? {};
  const name = b["상호"] || info.factory_name;
  const contact = [info.factory_phone, info.contact_hours && `(${info.contact_hours})`].filter(Boolean).join(" ");

  if (kind === "refund")
    return (
      <div>
        <ul className="space-y-2.5">
          {(info.refund_policy || DEFAULT_REFUND)
            .split("\n")
            .filter((l) => l.trim())
            .map((l) => (
              <li key={l} className="flex gap-2.5 break-keep leading-relaxed">
                <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" aria-hidden />
                <span>{l.replace(/^[-·•]\s*/, "")}</span>
              </li>
            ))}
        </ul>
        {contact && <p className="mt-5 rounded-xl bg-white p-4 text-[15px]">교환·반품 신청: <b>{contact}</b></p>}
      </div>
    );

  if (kind === "privacy")
    return (
      <div>
        <p className="mb-2 break-keep text-[15px] text-stone-600">{name}(이하 '공장')은 손님의 개인정보를 아래와 같이 처리해요.</p>
        <Sec n={1} title="모으는 정보">
          <p>주문할 때: 성함, 상호(선택), 휴대폰 번호, 받는 주소, 요청사항</p>
          <p>카카오·구글로 로그인할 때: 그 서비스의 회원번호와 이름(별명)</p>
          <p>카드로 결제할 때: 결제 승인 번호 (카드 번호는 결제대행사가 처리하고 공장은 받지 않아요)</p>
        </Sec>
        <Sec n={2} title="쓰는 곳">
          <p>주문 확인, 상품 포장·배송, 입금·배송 안내 연락, 교환·반품 처리, 다음 주문 때 주소 불러오기</p>
        </Sec>
        <Sec n={3} title="보관 기간">
          <p>{info.privacy_retention || "주문일로부터 1년"} 보관한 뒤 지워요. 다만 전자상거래법에 따라 계약·결제 기록은 5년, 소비자 불만·분쟁 처리 기록은 3년 보관해요.</p>
        </Sec>
        <Sec n={4} title="다른 곳에 주는 정보">
          <p>배송을 위해 택배사·화물 기사님께 받는 분 성함, 휴대폰 번호, 주소를 전해요. 그 밖에는 손님 동의나 법에 정한 경우가 아니면 주지 않아요.</p>
        </Sec>
        <Sec n={5} title="맡겨서 처리하는 곳">
          <p>주문 기록 저장: Google(구글 스프레드시트) · 주문서 운영: Vercel, Render</p>
          <p>문자·알림톡 발송: 솔라피 · 카드 결제: 토스페이먼츠 · 로그인: 카카오, Google</p>
        </Sec>
        <Sec n={6} title="지우는 방법">
          <p>보관 기간이 지나면 기록을 지워요. 손님이 원하시면 언제든 열람·수정·삭제·처리 정지를 요청할 수 있어요.</p>
        </Sec>
        <Sec n={7} title="개인정보 보호책임자">
          <p>{b["개인정보 보호책임자"] || contact || name}</p>
        </Sec>
      </div>
    );

  return (
    <div>
      <Sec n={1} title="목적">
        <p>이 약관은 {name}(이하 '공장')이 운영하는 온라인 주문서에서 상품을 사고팔 때의 약속을 정해요.</p>
      </Sec>
      <Sec n={2} title="주문">
        <p>손님이 주문서를 보내고 공장이 확인하면 계약이 이뤄져요. 품절·주소 오류 등으로 보낼 수 없으면 공장이 연락드리고 주문을 취소할 수 있어요.</p>
      </Sec>
      <Sec n={3} title="결제">
        <p>안내된 계좌로 입금하거나 카드·간편결제로 낼 수 있어요. 입금을 확인한 뒤 포장해서 보내 드려요.</p>
      </Sec>
      <Sec n={4} title="배송">
        <p>주문서에 적힌 받는 날에 맞춰 택배 또는 화물로 보내요. 양이 많으면 화물로 보내고 운임은 따로 안내해요.</p>
      </Sec>
      <Sec n={5} title="취소·교환·반품">
        <p>포장을 시작하기 전에는 마이페이지나 주문 조회에서 직접 취소할 수 있어요. 교환·반품은 '교환·반품 안내'를 따라요.</p>
      </Sec>
      <Sec n={6} title="개인정보">
        <p>손님 정보는 '개인정보처리방침'에 따라 다뤄요.</p>
      </Sec>
      <Sec n={7} title="문의">
        <p>{contact || name}</p>
      </Sec>
    </div>
  );
}
