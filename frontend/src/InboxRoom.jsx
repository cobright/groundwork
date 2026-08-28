import React, { useEffect, useState } from "react";
import { reportApi } from "./api.js";

const STAGES = ["목차", "초고", "검토", "최종"];
const STATUS_CLASS = { "정상 추진": "s-ok", "지연 우려": "s-warn", "협의·대기": "s-info", "보류": "s-hold" };

function dueLabel(x) {
  if (x.d_day === null || x.d_day === undefined) return { text: "마감 미정", cls: "due-none" };
  if (x.d_day < 0) return { text: `${-x.d_day}일 초과`, cls: "due-over" };
  if (x.d_day === 0) return { text: "오늘 마감", cls: "due-soon" };
  if (x.d_day <= 3) return { text: `D-${x.d_day}`, cls: "due-soon" };
  return { text: `D-${x.d_day}`, cls: "due-ok" };
}

export default function InboxRoom() {
  const [data, setData] = useState(null);
  const [folder, setFolder] = useState("");
  const [folderDraft, setFolderDraft] = useState("");
  const [groupBy, setGroupBy] = useState("업무");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [picking, setPicking] = useState(false);

  useEffect(() => { init(); }, []);
  async function init() {
    try { const f = await reportApi.getInboxFolder(); setFolder(f.folder || ""); setFolderDraft(f.folder || ""); if (f.folder) load(); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function load() {
    setLoading(true); setErr("");
    try { setData(await reportApi.readInbox()); }
    catch (e) { setErr(String(e.message || e)); setData(null); } finally { setLoading(false); }
  }
  async function saveFolder(pathValue) {
    const val = (pathValue !== undefined ? pathValue : folderDraft).trim();
    try { const f = await reportApi.setInboxFolder(val); setFolder(f.folder); setFolderDraft(f.folder); await load(); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function pickFolder() {
    setPicking(true); setErr("");
    try {
      const r = await reportApi.pickFolder();
      if (r.available === false) { setErr("이 PC에서는 폴더 선택창을 쓸 수 없습니다. 아래 칸에 경로를 직접 붙여넣어 주세요."); return; }
      if (r.folder) await saveFolder(r.folder);   // 고르면 바로 저장·읽기
    } catch (e) { setErr(String(e.message || e)); } finally { setPicking(false); }
  }

  const reports = data?.reports || [];
  const groups = {};
  reports.forEach((r) => { const k = groupBy === "업무" ? r.project_name : r.author; (groups[k] = groups[k] || []).push(r); });

  return (
    <div className="dash inbox">
      <div className="dashhead">
        <div><p className="eyebrow">받은 보고</p><h2>팀 진행상황</h2></div>
        <span className="hint">메신저로 받은 보고 파일이 쌓이는 폴더를 지정하면, 팀원별·업무별 최신 상태를 모아 봅니다.</span>
        <div className="spacer" />
        <button className="btn sm" disabled={loading || !folder} onClick={load}>{loading ? "읽는 중…" : "새로고침"}</button>
      </div>

      {/* 폴더 지정 */}
      <div className="inboxfolder">
        <span className="if-label">보고 폴더</span>
        <button className="btn primary sm" disabled={picking} onClick={pickFolder}>{picking ? "선택 중…" : "폴더 선택"}</button>
        <input placeholder="또는 경로 직접 입력 (예: C:\\Users\\내이름\\Downloads)" value={folderDraft}
          onChange={(e) => setFolderDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && saveFolder()} />
        <button className="btn sm" onClick={() => saveFolder()}>적용</button>
      </div>
      {folder && <div className="inboxfolder-cur">현재 폴더: <span>{folder}</span></div>}

      {err && <div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}

      {data && (
        <div className="inboxbar">
          <span className="hint">보고 <b>{reports.length}</b>건 · 파일 {data.scanned}개 확인{data.skipped ? ` (형식 외 ${data.skipped}개 제외)` : ""}</span>
          <div className="spacer" />
          <div className="groupswitch">
            <button className={groupBy === "업무" ? "on" : ""} onClick={() => setGroupBy("업무")}>업무별</button>
            <button className={groupBy === "팀원" ? "on" : ""} onClick={() => setGroupBy("팀원")}>팀원별</button>
          </div>
        </div>
      )}

      {!folder && <div className="dashempty">먼저 위에 보고 폴더 경로를 지정하세요. 메신저에서 받은 보고 파일이 그 폴더에 쌓입니다.</div>}
      {data && reports.length === 0 && <div className="dashempty">폴더에서 보고 파일을 찾지 못했습니다. 경로가 맞는지, 파일이 들어와 있는지 확인하세요.</div>}

      {Object.keys(groups).map((g) => (
        <div key={g} className="inboxgroup">
          <div className="ig-head">{g} <span className="ig-count">{groups[g].length}</span></div>
          <div className="dashgrid">
            {groups[g].map((r, i) => {
              const d = dueLabel(r);
              const chips = [
                ["중대·중요", r.severe, "c-crit"],
                ["미해결", r.unresolved - r.severe, "c-warn"],
                ["확인 필요", r.need_flags, "c-warn"],
                ["미확정 근거", r.ev_unconfirmed, "c-warn"],
                ["변경 근거", r.ev_changed, "c-crit"],
                ["회신 대기", r.req_open, "c-info"],
              ].filter(([, n]) => n > 0);
              return (
                <div key={i} className={"dashcard inboxcard" + (r.overdue ? " overdue" : "")}>
                  <div className="dc-top">
                    <div className="dc-name">{groupBy === "업무" ? r.author : r.project_name}</div>
                    <span className={"duebadge " + d.cls}>{d.text}</span>
                  </div>
                  <div className="dc-type">
                    {groupBy === "업무" ? r.doc_type : `${r.doc_type || "문서유형 미정"}`}
                    {r.status_label && <span className={"statuspill " + (STATUS_CLASS[r.status_label] || "")}>{r.status_label}</span>}
                  </div>

                  <div className="stagestrip" title={r.stage_label}>
                    {STAGES.map((s, k) => {
                      const state = r.stage_index > k ? "done" : r.stage_index === k ? "now" : "todo";
                      return <div key={s} className={"stagecell " + state}><span className="sc-seal" />{s}</div>;
                    })}
                  </div>
                  <div className="dc-stagelabel">{r.stage_label} · 본문 <b>{r.bodies_filled}/{r.outline_total}</b></div>

                  {r.message && <div className="inboxmsg">“{r.message}”</div>}
                  {chips.length > 0 && <div className="dc-chips">{chips.map(([label, n, cls]) => <span key={label} className={"dchip " + cls}>{label} <b>{n}</b></span>)}</div>}
                  <div className="inboxmeta">{r.generated_at}</div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
