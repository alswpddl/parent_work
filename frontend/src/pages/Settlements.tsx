import { useState } from "react";
import { FileText, Link2, RefreshCw, Send, Wallet } from "lucide-react";
import { openBlobInNewTab } from "../api/client";
import { generateSettlements, listSettlements, sendAllSettlements, sendSettlement, settlementLink, settlementPdf, updateSettlement } from "../api/endpoints";
import type { Settlement } from "../api/types";
import { useToast } from "../components/Toast";
import { Alert, Badge, Button, Card, ConfirmButton, CopyButton, Empty, Field, Input, LoadState, Modal, PageHeader } from "../components/ui";
import { useFeatures } from "../lib/features";
import { dateKo, monthIso, won } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";

const STATUS_TONE = { 생성: "violet", 발송완료: "parcel", 수금완료: "green" } as const;

export default function Settlements() {
  const toast = useToast();
  const { features } = useFeatures();
  const { busy, run } = useAction();
  const [period, setPeriod] = useState(monthIso(-1));
  const list = useAsync(() => listSettlements(period), [period]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [sendFor, setSendFor] = useState<Settlement | "all" | null>(null);
  const fail = (m: string) => toast(m, "error");

  const replace = (s: Settlement) => list.setData((xs) => xs?.map((x) => (x.settlement_id === s.settlement_id ? s : x)));
  const rows = list.data ?? [];
  const total = rows.reduce((a, s) => a + s.total, 0);
  const unpaid = rows.filter((s) => s.status !== "수금완료").reduce((a, s) => a + s.total, 0);

  const generate = (force = false) =>
    run("gen", async () => {
      const r = await generateSettlements(period, force);
      setWarnings(r.warnings);
      list.setData(r.settlements);
      toast(`새로 ${r.created}건 · 다시 계산 ${r.updated}건${r.kept.length ? ` · 발송된 ${r.kept.length}건은 그대로` : ""}`);
    }, fail);

  return (
    <div>
      <PageHeader title="월말 정산" subtitle="한 달 동안 출고한 거래처별 금액을 모아 거래명세표를 만들어요." />
      <Card>
        <div className="flex flex-col gap-3 md:flex-row md:items-end">
          <Field label="정산할 달" className="mb-0 md:w-56">
            <Input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
          </Field>
          <Button icon={<RefreshCw className="h-5 w-5" />} loading={busy === "gen"} onClick={() => generate(false)}>
            명세표 만들기
          </Button>
          {rows.some((s) => s.status === "생성") && (
            <Button variant="parcel" icon={<Send className="h-5 w-5" />} onClick={() => setSendFor("all")}>
              모두 보내기
            </Button>
          )}
        </div>
        {rows.length > 0 && (
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-2xl bg-white p-3">
              <div className="text-sm text-stone-500">합계</div>
              <div className="whitespace-nowrap text-xl font-extrabold md:text-2xl">{won(total)}</div>
            </div>
            <div className="rounded-2xl bg-white p-3">
              <div className="text-sm text-stone-500">아직 안 받은 돈</div>
              <div className="whitespace-nowrap text-xl font-extrabold text-truck md:text-2xl">{won(unpaid)}</div>
            </div>
          </div>
        )}
      </Card>
      {warnings.map((w) => (
        <Alert key={w} tone="warn">{w}</Alert>
      ))}
      <LoadState loading={list.loading} error={list.error} onRetry={list.reload} />
      {!list.loading && rows.length === 0 && <Empty>{period} 정산서가 없어요. [명세표 만들기]를 눌러 주세요.</Empty>}

      {rows.map((s) => (
        <div key={s.settlement_id} className="mb-3 rounded-2xl border border-line bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <div className="text-lg font-extrabold">{s.customer_name}</div>
              <div className="text-sm text-stone-500">{s.order_count}건 · 공급가 {won(s.supply_amount)} · 세액 {won(s.vat)}</div>
            </div>
            <div className="text-right">
              <div className="whitespace-nowrap text-xl font-extrabold md:text-2xl">{won(s.total)}</div>
              <Badge tone={STATUS_TONE[s.status]}>{s.status}{s.status === "수금완료" && s.paid_at ? ` ${dateKo(s.paid_at)}` : ""}</Badge>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="md" variant="ghost" icon={<FileText className="h-5 w-5" />} onClick={() => openBlobInNewTab(() => settlementPdf(s.settlement_id)).catch((e) => fail(String(e)))}>
              PDF 보기
            </Button>
            <Button size="md" variant="parcel" icon={<Send className="h-5 w-5" />} onClick={() => setSendFor(s)}>
              보내기
            </Button>
            <CopyButton size="md" label="링크 복사" text={async () => (await settlementLink(s.settlement_id)).url} onCopied={(ok) => toast(ok ? "명세표 링크를 복사했어요 (30일 유효)." : "복사가 막혔어요.", ok ? "ok" : "error")} />
            {s.status !== "수금완료" ? (
              <Button size="md" icon={<Wallet className="h-5 w-5" />} loading={busy === `paid-${s.settlement_id}`} onClick={() => run(`paid-${s.settlement_id}`, async () => { replace(await updateSettlement(s.settlement_id, { status: "수금완료" })); toast("수금 완료로 표시했어요."); }, fail)}>
                돈 받음
              </Button>
            ) : (
              <ConfirmButton size="md" variant="plain" confirmText="수금 취소할까요?" onConfirm={() => run(`unpaid-${s.settlement_id}`, async () => replace(await updateSettlement(s.settlement_id, { status: "발송완료", paid_at: null })), fail)}>
                <Link2 className="h-4 w-4" /> 수금 취소
              </ConfirmButton>
            )}
          </div>
        </div>
      ))}

      {rows.some((s) => s.status !== "생성") && (
        <div className="mt-2 text-right">
          <ConfirmButton size="sm" variant="plain" confirmText="발송된 것까지 다시 계산할까요?" onConfirm={() => generate(true)}>
            발송된 명세표까지 다시 계산
          </ConfirmButton>
        </div>
      )}

      {sendFor && (
        <SendModal
          target={sendFor}
          canEmail={!!features?.integrations.email}
          canKakao={!!features?.integrations.solapi}
          onClose={() => setSendFor(null)}
          onSend={async (via) => {
            if (sendFor === "all") {
              const rs = await sendAllSettlements(period, via);
              const ok = rs.filter((r) => Object.values(r.results).includes("성공")).length;
              toast(`${rs.length}건 중 ${ok}건 보냈어요.`);
              void list.reload();
            } else {
              const r = await sendSettlement(sendFor.settlement_id, via);
              const msg = Object.entries(r.results).map(([k, v]) => `${k === "email" ? "메일" : "알림톡"}: ${v}`).join(" · ");
              toast(msg, Object.values(r.results).includes("성공") ? "ok" : "error");
              void list.reload();
            }
            setSendFor(null);
          }}
        />
      )}
    </div>
  );
}

function SendModal({ target, canEmail, canKakao, onClose, onSend }: { target: Settlement | "all"; canEmail: boolean; canKakao: boolean; onClose: () => void; onSend: (via: string[]) => Promise<void> }) {
  const [email, setEmail] = useState(canEmail);
  const [kakao, setKakao] = useState(canKakao);
  const [busy, setBusy] = useState(false);
  const via = [email && "email", kakao && "kakao"].filter(Boolean) as string[];
  const one = target !== "all" ? target : null;
  return (
    <Modal
      open
      onClose={onClose}
      title={one ? `${one.customer_name} 명세표 보내기` : "아직 안 보낸 명세표 모두 보내기"}
      footer={<Button block loading={busy} disabled={!via.length} onClick={async () => { setBusy(true); try { await onSend(via); } finally { setBusy(false); } }}>보내기</Button>}
    >
      {!canEmail && !canKakao && <Alert tone="warn">메일·알림톡 설정이 없어서 보낼 수 없어요. [링크 복사]로 직접 카톡에 붙여넣어 주세요.</Alert>}
      <label className="mb-3 flex items-center gap-3 rounded-xl border border-line bg-white p-4">
        <input type="checkbox" className="h-6 w-6" checked={email} disabled={!canEmail} onChange={(e) => setEmail(e.target.checked)} />
        <span>
          <b>이메일</b> (PDF 첨부){one && !one.has_email && <span className="block text-sm text-red-700">이 거래처는 이메일이 등록되지 않았어요</span>}
        </span>
      </label>
      <label className="mb-3 flex items-center gap-3 rounded-xl border border-line bg-white p-4">
        <input type="checkbox" className="h-6 w-6" checked={kakao} disabled={!canKakao} onChange={(e) => setKakao(e.target.checked)} />
        <span>
          <b>카카오 알림톡</b> (명세표 링크){one && !one.has_phone && <span className="block text-sm text-red-700">이 거래처는 전화번호가 없어요</span>}
        </span>
      </label>
    </Modal>
  );
}
