// 발송 기록 목록 — 처음엔 5건만, 나머지는 '더보기'로 접어 둬요
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { MessageLog } from "../api/types";
import { Badge, Empty, cx } from "./ui";

const SHOW = 5;

export function MessageLogList({ items, compact }: { items: MessageLog[]; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  if (!items.length) return <Empty>아직 보낸 메시지가 없어요.</Empty>;
  const shown = open ? items : items.slice(0, SHOW);
  const fail = items.filter((m) => m.result === "실패").length;
  return (
    <div>
      <ul className="divide-y divide-line">
        {shown.map((m, i) => (
          <li key={`${m.ts}-${i}`} className={cx("py-2.5", compact && "py-2")}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="font-semibold">
                  {m.kind}
                  {!compact && <span className="ml-1.5 text-sm font-normal text-stone-500">{m.channel} → {m.to}</span>}
                </div>
                <div className="text-sm text-stone-500 tabular-nums">{m.ts}</div>
              </div>
              <Badge tone={m.result === "성공" ? "green" : m.result === "실패" ? "red" : "gray"}>{m.result}</Badge>
            </div>
            {m.error && <div className="mt-0.5 break-keep text-sm text-bad">{m.error}</div>}
          </li>
        ))}
      </ul>
      {items.length > SHOW && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="mt-1 flex w-full items-center justify-center gap-1 rounded-lg py-2.5 text-[15px] font-semibold text-stone-600 hover:bg-stone-50"
        >
          {open ? "접기" : `더보기 ${items.length - SHOW}건${!open && fail ? ` (실패 ${items.slice(SHOW).filter((m) => m.result === "실패").length}건 포함)` : ""}`}
          <ChevronDown className={cx("h-4 w-4 transition-transform", open && "rotate-180")} />
        </button>
      )}
    </div>
  );
}
