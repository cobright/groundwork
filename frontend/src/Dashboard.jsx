import React, { useEffect, useState } from "react";
import { fetchDashboard } from "./api.js";

const STAGES = ["목차", "초고", "검토", "최종"];

function dueLabel(x) {
  if (x.d_day === null || x.d_day === undefined) return { text: "마감 미정", cls: "due-none" };
  if (x.d_day < 0) return { text: `${-x.d_day}일 초과`, cls: "due-over" };
  if (x.d_day === 0) return { text: "오늘 마감", cls: "due-soon" };
  if (x.d_day <= 3) return { text: `D-${x.d_day}`, cls: "due-soon" };
  return { text: `D-${x.d_day}`, cls: "due-ok" };
}

export default function Dashboard({ onOpen }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { load(); }, []);
  async function load() { try { setData(await fetchDashboard()); } catch (e) { setErr(String(e.message || e)); } }

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
            <button key={x.id} className={"dashcard" + (x.overdue ? " overdue" : "")} onClick={() => onOpen(x.id)}>
              <div className="dc-top">
                <div className="dc-name">{x.name || "(무제)"}</div>
                <span className={"duebadge " + d.cls}>{d.text}</span>
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
            </button>
          );
        })}
      </div>
    </div>
  );
}
