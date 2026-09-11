import React, { useEffect, useRef, useState } from "react";
import { api, STRICTNESS } from "./api.js";
import { flatNumbers } from "./outlineModel.js";
import { useColumns } from "./Columns.jsx";

const PROVIDERS = [["", "설정대로"], ["openai", "OpenAI"], ["claude", "Claude"], ["gemini", "Gemini"]];

export default function DraftRoom({ pid }) {
  const cols = useColumns("draft", { left: 300, right: 340 }, { left: "목차 항목", right: "근거" });
  const [nodes, setNodes] = useState([]);
  const [numbers, setNumbers] = useState({});
  const [evidence, setEvidence] = useState([]);
  const [uid, setUid] = useState(null);
  const [ctx, setCtx] = useState(null);        // {draft,title,number,card,evidence_count,confirmed_count}
  const [body, setBody] = useState("");
  const [strictness, setStrictness] = useState("엄격");
  const [provider, setProvider] = useState("");
  const [busy, setBusy] = useState(false);
  const [flag, setFlag] = useState("");
  const [err, setErr] = useState("");
  const saveTimer = useRef(null);

  useEffect(() => { if (pid) loadOutline(); }, [pid]);
  async function loadOutline() {
    try {
      const [ol, ev] = await Promise.all([api.getOutline(pid), api.listEvidence(pid)]);
      const ns = ol.nodes || []; setNodes(ns); setNumbers(flatNumbers(ns)); setEvidence(ev);
      if (ns.length && !ns.find((n) => n.uid === uid)) selectNode(ns[0].uid);
      else if (!ns.length) { setUid(null); setCtx(null); }
    } catch (e) { setErr(String(e.message || e)); }
  }
  async function selectNode(u) {
    setUid(u); setErr("");
    try { const d = await api.getDraft(pid, u); setCtx(d); setBody(d.draft.body || ""); setStrictness(d.draft.strictness || "엄격"); setFlag(""); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function generate() {
    if (!uid) return; setBusy(true); setErr("");
    try { const r = await api.generateDraft(pid, uid, strictness, provider); setCtx((c) => ({ ...c, draft: { ...c.draft, ai_suggestion: r.ai_suggestion, strictness: r.strictness, model: r.model } })); }
    catch (e) { setErr(String(e.message || e)); }
    finally { setBusy(false); }
  }
  function applySuggestion() {
    const sug = ctx?.draft?.ai_suggestion || ""; if (!sug) return;
    if (body.trim() && !confirm("현재 본문을 AI 제안으로 바꿀까요? (기존 본문은 사라집니다)")) return;
    setBody(sug); saveBodySoon(sug);
  }
  function appendSuggestion() {
    const sug = ctx?.draft?.ai_suggestion || ""; if (!sug) return;
    const next = body.trim() ? body + "\n\n" + sug : sug; setBody(next); saveBodySoon(next);
  }
  function onBody(v) { setBody(v); saveBodySoon(v); }
  function saveBodySoon(v) {
    setFlag("저장 중…"); clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      try { await api.saveDraftBody(pid, uid, v); setFlag("저장됨"); } catch (e) { setFlag("저장 실패"); setErr(String(e.message || e)); }
    }, 500);
  }

  if (!pid) return <div className="rr-empty">먼저 상단에서 업무를 선택하세요.</div>;
  const linked = evidence.filter((e) => e.node_uid === uid);

  return (
    <div className={"rr" + cols.cls} ref={cols.ref} style={cols.style}>
      {cols.handles}
      {err &&<div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}

      {/* 좌: 목차 항목 선택 */}
      <section className="col left">
        <p className="eyebrow">목차 항목</p>
        {nodes.length === 0 && <div className="hint">먼저 ‘목차 편집’에서 목차를 만드세요.</div>}
        {nodes.map((n) => (
          <div key={n.uid} className={"dnode" + (n.uid === uid ? " sel" : "")} onClick={() => selectNode(n.uid)}>
            <span className="num">{numbers[n.uid]}</span><span className="dtitle">{n.title}</span>
          </div>
        ))}
      </section>

      {/* 중: 초고 작성 */}
      <section className="col center">
        {!ctx ? <div className="rr-empty">왼쪽에서 목차 항목을 선택하세요.</div> : (
          <>
            <div className="chead"><p className="eyebrow m0">{ctx.number} {ctx.title}</p><span className="flagtxt">{flag}</span></div>
            {(ctx.card?.purpose || ctx.card?.message) && (
              <div className="cardmini">
                {ctx.card.purpose && <div><b>목적</b> {ctx.card.purpose}</div>}
                {ctx.card.message && <div><b>핵심 메시지</b> {ctx.card.message}</div>}
              </div>
            )}

            <div className="genbar">
              <select value={strictness} onChange={(e) => setStrictness(e.target.value)}>{STRICTNESS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>{PROVIDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              <button className="btn primary" disabled={busy} onClick={generate}>{busy ? "생성 중…" : "초고 생성"}</button>
            </div>
            {ctx.confirmed_count === 0 && <div className="warnbox">이 목차에 <b>확정된 근거가 없습니다.</b> 엄격 모드에서는 대부분 [확인 필요]로 남습니다. 먼저 ‘자료·근거’에서 근거를 연결·확정하세요.</div>}

            {ctx.draft?.ai_suggestion && (
              <div className="sugbox">
                <div className="sughead"><span>AI 제안 <em>({ctx.draft.strictness}{ctx.draft.model ? " · " + ctx.draft.model : ""})</em></span>
                  <span className="sugbtns"><button className="btn sm" onClick={applySuggestion}>본문에 반영</button><button className="btn sm ghost" onClick={appendSuggestion}>이어붙이기</button></span></div>
                <div className="sugtext">{ctx.draft.ai_suggestion}</div>
                <div className="sugnote">AI 제안은 자동으로 본문에 들어가지 않습니다. 검토 후 반영하세요.</div>
              </div>
            )}

            <p className="eyebrow" style={{ marginTop: 18 }}>본문 (사용자 확정)</p>
            <textarea className="bodyedit" value={body} onChange={(e) => onBody(e.target.value)} placeholder="이 목차의 본문입니다. AI 제안을 반영하거나 직접 작성하세요." />
          </>
        )}
      </section>

      {/* 우: 이 목차에 연결된 근거 */}
      <section className="col right">
        <p className="eyebrow">이 목차의 근거</p>
        {ctx && (
          <div className="evsummary">확정 근거 <b>{ctx.confirmed_count}</b> / 연결 {ctx.evidence_count}건
            <div className="hint">엄격 모드는 확정 근거 안에서만 씁니다.</div></div>
        )}
        {linked.length === 0 && <div className="hint">이 목차에 연결된 근거가 없습니다. ‘자료·근거’에서 근거의 ‘목차 연결’을 이 항목으로 지정하세요.</div>}
        {linked.map((e, i) => (
          <div className="devi" key={e.id}>
            <div className="devitop">{e.ev_no || `E-${String(i + 1).padStart(3, "0")}`} <span className={"est " + (e.source_changed ? "chg" : "")}>{e.status}</span></div>
            <div className="deviclaim">{e.claim || <span className="hint">주장 없음</span>}</div>
            {e.source_changed ? <div className="chgflag">근거 자료 변경됨 — ‘자료·근거’에서 확인</div> : null}
          </div>
        ))}
      </section>
    </div>
  );
}
