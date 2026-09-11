import React, { useEffect, useState } from "react";
import { fetchDashboard, api } from "./api.js";
import Cabinet from "./Cabinet.jsx";

const STAGES = ["목차", "초고", "검토", "최종"];

function dueLabel(x) {
  if (x.d_day === null || x.d_day === undefined) return { text: "마감 미정", cls: "due-none" };
  if (x.d_day < 0) return { text: `${-x.d_day}일 초과`, cls: "due-over" };
  if (x.d_day === 0) return { text: "오늘 마감", cls: "due-soon" };
  if (x.d_day <= 3) return { text: `D-${x.d_day}`, cls: "due-soon" };
  return { text: `D-${x.d_day}`, cls: "due-ok" };
}

export default function Dashboard({ onOpen, onChanged }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [archiveFor, setArchiveFor] = useState(null);   // 보관 확인창 대상 업무
  const [archiveNote, setArchiveNote] = useState("");
  const [cabinetTick, setCabinetTick] = useState(0);
  useEffect(() => { load(); }, []);
  async function load() { try { setData(await fetchDashboard()); } catch (e) { setErr(String(e.message || e)); } }

  async function doArchive() {
    try {
      await api.archiveProject(archiveFor.id, archiveNote.trim());
      setArchiveFor(null); setArchiveNote("");
      await load(); setCabinetTick((n) => n + 1);
      onChanged && onChanged();
    } catch (e) { setErr(String(e.message || e)); }
  }

  if (err) return <div className="rr-empty">불러오기 실패: {err}</div>;
  if (!data) return <div className="dash"><div className="hint" style={{ padding: 24 }}>불러오는 중…</div></div>;
  const ps = data.projects;

  const totals = {
    count: ps.length,
    dueSoon: ps.filter((x) => x.d_day !== null && x.d_day <= 3).length,
    severe: ps.reduce((s, x) => s + x.severe, 0),
    waiting: ps.reduce((s, x) => s + x.req_open, 0),
  };

  return (
    <div className="dash">
      <div className="dashhead">
        <div>
          <p className="eyebrow">상황판</p>
          <h2>진행 중인 과업</h2>
        </div>
        <div className="spacer" />
        <button className="btn sm ghost" onClick={load}>새로고침</button>
      </div>

      <div className="statstrip">
        <div className="stat"><span className="stat-n">{totals.count}</span><span className="stat-l">전체 과업</span></div>
        <div className={"stat" + (totals.dueSoon ? " hot" : "")}><span className="stat-n">{totals.dueSoon}</span><span className="stat-l">마감 임박·초과</span></div>
        <div className={"stat" + (totals.severe ? " crit" : "")}><span className="stat-n">{totals.severe}</span><span className="stat-l">중대·중요 미해결</span></div>
        <div className="stat"><span className="stat-n">{totals.waiting}</span><span className="stat-l">자료 회신 대기</span></div>
      </div>

      {/* 막힌 곳 — 숫자는 위 칩에도 있지만, 흩어져 있으면 '무엇부터 손대야 하나'가 안 보인다.
          여기서는 업무를 가로질러 모으고 **할 일**을 한 줄씩 붙인다. 누르면 그 자리로 간다. */}
      {(data.blocked || []).length > 0 && (
        <div className="blockbox">
          <div className="blockhead">
            <p className="eyebrow m0">지금 막힌 곳 ({data.blocked.length})</p>
            <span className="hint">위에서부터 손대시면 됩니다.</span>
          </div>
          <ul className="blocklist">
            {data.blocked.map((b, i) => (
              <li key={i} className={"b-r" + b.rank}>
                <button className="blockrow" onClick={() => onOpen(b.project_id, b.tab)}>
                  <span className="bkind">{b.kind}{b.rank >= 2 ? ` ${b.count}건` : ""}</span>
                  <span className="bproj">{b.project_name}</span>
                  <span className="bwhat">{b.what}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {ps.length === 0 && <div className="dashempty">아직 등록된 과업이 없습니다. 오른쪽 위 ‘+ 새 업무’로 첫 과업을 시작하세요.</div>}

      <div className="dashgrid">
        {ps.map((x) => {
          const d = dueLabel(x);
          const chips = [
            ["중대·중요 미해결", x.severe, "c-crit"],
            ["미해결 의견", x.unresolved - x.severe, "c-warn"],
            ["확인 필요", x.need_flags, "c-warn"],
            ["미확정 근거", x.ev_unconfirmed, "c-warn"],
            ["변경된 근거", x.ev_changed, "c-crit"],
            ["회신 대기", x.req_open, "c-info"],
            ["요청 초과", x.req_overdue, "c-crit"],
          ].filter(([, n]) => n > 0);
          return (
            // 버튼 안에 버튼을 넣을 수 없어(무효 HTML) 카드는 div 로 두고 키보드 조작을 붙인다.
            <div key={x.id} role="button" tabIndex={0}
                 className={"dashcard" + (x.overdue ? " overdue" : "")}
                 onClick={() => onOpen(x.id)}
                 onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(x.id); } }}>
              <div className="dc-top">
                <div className="dc-name">{x.name || "(무제)"}</div>
                <span className={"duebadge " + d.cls}>{d.text}</span>
                <button className="archivebtn" title="지금 관리 대상이 아니면 보관함에 넣어 두세요"
                        onClick={(e) => { e.stopPropagation(); setArchiveFor(x); setArchiveNote(""); }}>보관</button>
              </div>
              <div className="dc-type">{x.doc_type || "문서유형 미정"}</div>

              {/* 결재란식 단계 띠 */}
              <div className="stagestrip" title={x.stage_label}>
                {STAGES.map((s, i) => {
                  const state = x.stage_index > i ? "done" : x.stage_index === i ? "now" : "todo";
                  return <div key={s} className={"stagecell " + state}><span className="sc-seal" />{s}</div>;
                })}
              </div>
              <div className="dc-stagelabel">{x.stage_label} · 본문 <b>{x.bodies_filled}/{x.outline_total}</b></div>

              {chips.length > 0
                ? <div className="dc-chips">{chips.map(([label, n, cls]) => <span key={label} className={"dchip " + cls}>{label} <b>{n}</b></span>)}</div>
                : <div className="dc-clear">지금 처리할 항목 없음</div>}
            </div>
          );
        })}
      </div>

      <Cabinet tick={cabinetTick} onChanged={() => { load(); onChanged && onChanged(); }} />

      {archiveFor && (
        <div className="modal-backdrop" onClick={() => setArchiveFor(null)}>
          <div className="modal archive-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <p className="eyebrow">보관함에 넣기</p>
                <h3>{archiveFor.name || "(무제)"}</h3>
              </div>
              <button className="mini" onClick={() => setArchiveFor(null)}>✕</button>
            </div>
            <div className="modal-body">
              <p className="hint">상황판에서 내려두기만 합니다. <b>지워지지 않으며</b> 언제든 되살릴 수 있습니다.
                삭제는 보관함 안에서만 할 수 있습니다.</p>
              <label className="ri-label">왜 보관하나요 <span className="opt">(선택)</span></label>
              <input autoFocus placeholder="예: 공모 탈락, 내년 재검토 / ○○부서 협의 대기"
                     value={archiveNote} onChange={(e) => setArchiveNote(e.target.value)}
                     onKeyDown={(e) => e.key === "Enter" && doArchive()} />
            </div>
            <div className="modal-foot">
              <button className="btn" onClick={() => setArchiveFor(null)}>취소</button>
              <button className="btn primary" onClick={doArchive}>보관함에 넣기</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
