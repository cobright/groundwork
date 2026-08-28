import React, { useEffect, useState } from "react";
import { reportApi } from "./api.js";

export default function ReportModal({ pid, onClose }) {
  const [pv, setPv] = useState(null);
  const [author, setAuthor] = useState("");
  const [editName, setEditName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { load(); }, [pid]);
  async function load() {
    try {
      const d = await reportApi.reportPreview(pid);
      setPv(d); setAuthor(d.author || "");
      if (!d.author) { setEditName(true); setNameDraft(""); }
    } catch (e) { setErr(String(e.message || e)); }
  }
  async function saveName() {
    try { const r = await reportApi.putSettings(nameDraft.trim()); setAuthor(r.author_name); setEditName(false); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function saveReport() {
    if (!author) { setEditName(true); setErr("먼저 보고자 이름을 설정하세요."); return; }
    setBusy(true); setErr("");
    try {
      const res = await fetch(reportApi.reportExportUrl(pid), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, status_label: status }),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const cd = res.headers.get("Content-Disposition") || "";
      let fname = "진행보고.json";
      const m = cd.match(/filename\*=UTF-8''([^;]+)/);
      if (m) fname = decodeURIComponent(m[1]);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = fname;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
      onClose(true);
    } catch (e) { setErr(String(e.message || e)); } finally { setBusy(false); }
  }

  return (
    <div className="modal-backdrop" onClick={() => onClose(false)}>
      <div className="modal report-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <p className="eyebrow">진행상황 보고</p>
            <h3>{pv ? pv.facts.name : "업무"}</h3>
          </div>
          <button className="mini" onClick={() => onClose(false)}>✕</button>
        </div>

        {err && <div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}
        {!pv ? <div className="hint" style={{ padding: 16 }}>불러오는 중…</div> : (
          <div className="modal-body">
            {/* 보고자 */}
            <div className="report-author">
              <span className="ra-label">보고자</span>
              {editName ? (
                <span className="ra-edit">
                  <input autoFocus placeholder="이름을 입력하세요" value={nameDraft}
                    onChange={(e) => setNameDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && nameDraft.trim() && saveName()} />
                  <button className="btn sm primary" disabled={!nameDraft.trim()} onClick={saveName}>저장</button>
                </span>
              ) : (
                <span className="ra-name">{author} <button className="linklike" onClick={() => { setNameDraft(author); setEditName(true); }}>이름 변경</button></span>
              )}
            </div>

            {/* 자동 집계 사실(읽기 전용) */}
            <div className="report-facts">
              <div className="rf-head">자동 집계 <span className="rf-note">시스템이 계산한 내용입니다. 수정할 수 없습니다.</span></div>
              {pv.facts_lines.map((ln, i) => <div key={i} className="rf-line">{ln}</div>)}
            </div>

            {/* 사람 입력 */}
            <div className="report-input">
              <label className="ri-label">상태 <span className="opt">(선택)</span></label>
              <div className="status-choices">
                <button className={"chip-btn" + (status === "" ? " on" : "")} onClick={() => setStatus("")}>선택 안 함</button>
                {pv.status_choices.map((s) => <button key={s} className={"chip-btn" + (status === s ? " on" : "")} onClick={() => setStatus(s)}>{s}</button>)}
              </div>

              <label className="ri-label">팀장에게 한마디 <span className="opt">(선택)</span></label>
              <textarea placeholder="시스템에 없지만 전하고 싶은 말이 있으면 적으세요. (예: ○○부서 회신이 늦어 다음 주로 밀립니다)"
                value={message} onChange={(e) => setMessage(e.target.value)} />
            </div>
          </div>
        )}

        <div className="modal-foot">
          <span className="hint">저장하면 보고 파일이 내려받아집니다. 메신저로 팀장·과장에게 보내세요.</span>
          <div className="spacer" />
          <button className="btn ghost" onClick={() => onClose(false)}>취소</button>
          <button className="btn primary" disabled={busy || !pv} onClick={saveReport}>{busy ? "저장 중…" : "보고 파일 저장"}</button>
        </div>
      </div>
    </div>
  );
}
