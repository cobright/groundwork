import React, { useEffect, useState } from "react";
import { api } from "./api.js";

// 보관함(캐비넷) — 지워야 할지는 모르겠으나 지금 관리 대상은 아닌 업무를 넣어두는 곳.
// 삭제는 여기서만 할 수 있다. 그래서 진행 중인 업무는 실수로 지워지지 않는다.
export default function Cabinet({ tick, onChanged }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [err, setErr] = useState("");
  const [delFor, setDelFor] = useState(null);   // 삭제 확인창 대상
  const [preview, setPreview] = useState(null); // 무엇이 사라지는지
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { load(); }, [tick]);
  async function load() {
    try { setItems(await api.listArchived()); } catch (e) { setErr(String(e.message || e)); }
  }

  async function restore(p) {
    try { await api.unarchiveProject(p.id); await load(); onChanged && onChanged(); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function askDelete(p) {
    setDelFor(p); setTyped(""); setPreview(null);
    try { setPreview(await api.deletePreview(p.id)); } catch (e) { setErr(String(e.message || e)); }
  }
  async function confirmDelete() {
    setBusy(true);
    try {
      await api.deleteProject(delFor.id);
      setDelFor(null); await load(); onChanged && onChanged();
    } catch (e) { setErr(String(e.message || e)); }
    finally { setBusy(false); }
  }

  // 비어 있으면 아예 보이지 않는다 — 평소 상황판을 어지럽히지 않도록.
  if (!items.length && !err) return null;

  const nameMatches = delFor && typed.trim() === (delFor.name || "").trim() && typed.trim() !== "";

  return (
    <div className="cabinet">
      <button className="cab-head" onClick={() => setOpen((v) => !v)}>
        <span className="cab-caret">{open ? "▾" : "▸"}</span>
        보관함 <b>{items.length}</b>
        <span className="hint">진행 중이 아닌 업무를 넣어두는 곳입니다. 삭제는 여기서만 합니다.</span>
      </button>

      {err && <div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}

      {open && (
        items.length === 0
          ? <div className="cab-empty">보관함이 비어 있습니다.</div>
          : <div className="cab-list">
              {items.map((p) => (
                <div className="cab-row" key={p.id}>
                  <div className="cab-main">
                    <div className="cab-name">{p.name || "(무제)"}</div>
                    <div className="cab-meta">
                      {p.doc_type || "문서유형 미정"}
                      <span className="cab-when">보관 {(p.archived_at || "").slice(0, 10)}</span>
                    </div>
                    {p.archive_note && <div className="cab-note">“{p.archive_note}”</div>}
                  </div>
                  <div className="cab-btns">
                    <button className="btn sm" onClick={() => restore(p)}>되살리기</button>
                    <button className="btn sm ghost stamp" onClick={() => askDelete(p)}>삭제</button>
                  </div>
                </div>
              ))}
            </div>
      )}

      {delFor && (
        <div className="modal-backdrop" onClick={() => setDelFor(null)}>
          <div className="modal del-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <p className="eyebrow">업무 삭제</p>
                <h3>{delFor.name || "(무제)"}</h3>
              </div>
              <button className="mini" onClick={() => setDelFor(null)}>✕</button>
            </div>
            <div className="modal-body">
              <div className="del-warn">이 업무와 함께 아래가 <b>영구히</b> 사라집니다. 되돌릴 수 없습니다.</div>
              {!preview ? <div className="hint">확인 중…</div> : (
                <>
                  <ul className="del-list">
                    <li>목차 {preview.counts.outline}개 · 작성된 본문 {preview.counts.drafts}개</li>
                    <li>이 업무에 등록한 자료 {preview.counts.resources}건 · 근거 {preview.counts.evidence}건</li>
                    <li>검토의견 {preview.counts.opinions}건 · 자료요청 {preview.counts.requests}건</li>
                    {preview.counts.surveys > 0 && <li>설문 {preview.counts.surveys}건(근거 지도·문항 포함)</li>}
                  </ul>
                  <div className="del-safe">
                    공통자료실 자료는 삭제되지 않습니다{preview.counts.library_refs > 0
                      ? ` (참조 ${preview.counts.library_refs}건만 끊깁니다)` : ""}.
                  </div>
                </>
              )}
              <label className="ri-label">확인을 위해 업무명을 그대로 입력하세요</label>
              <input autoFocus placeholder={delFor.name} value={typed}
                     onChange={(e) => setTyped(e.target.value)}
                     onKeyDown={(e) => e.key === "Enter" && nameMatches && confirmDelete()} />
            </div>
            <div className="modal-foot">
              <button className="btn" onClick={() => setDelFor(null)}>취소</button>
              <button className="btn danger" disabled={!nameMatches || busy} onClick={confirmDelete}>
                {busy ? "삭제 중…" : "영구 삭제"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
