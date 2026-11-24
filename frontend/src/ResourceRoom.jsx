import React, { useEffect, useState } from "react";
import { PROVIDERS, api, RESOURCE_KINDS, EVIDENCE_STATUS } from "./api.js";
import { flatNumbers } from "./outlineModel.js";
import { useColumns } from "./Columns.jsx";

const STATE_LABEL = { "분석 전": "분석 전", "분석 완료": "분석 완료(미확정)", "재분석 필요": "재분석 필요", "사용자 확정": "확정됨" };
const EMPTY = { name: "", kind: "외부자료", source_org: "", base_date: "", text: "", note: "" };

export default function ResourceRoom({ pid }) {
  const cols = useColumns("resources", { left: 300, right: 340 }, { left: "자료 목록", right: "근거표" });
  const [resources, setResources] = useState([]);
  const [evidence, setEvidence] = useState([]);
  const [outline, setOutline] = useState([]);
  const [selId, setSelId] = useState(null);
  const [provider, setProvider] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);   // 파일 읽기는 AI 분석과 다른 일이다
  const [showText, setShowText] = useState(false);     // 파일에서 읽은 내용 펼치기
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ ...EMPTY });   // 신규 등록 폼
  const [edit, setEdit] = useState({ ...EMPTY });    // 선택 자료 수정 폼
  const [importOpen, setImportOpen] = useState(false);
  const [libQuery, setLibQuery] = useState("");
  const [libResults, setLibResults] = useState([]);
  const [depts, setDepts] = useState([]);
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [promoteDept, setPromoteDept] = useState(null);
  // 담당자 진술: 진술문 → 주장 후보(제안) → 사람이 골라 채택
  const [stmtOpen, setStmtOpen] = useState(false);
  const [stmtText, setStmtText] = useState("");
  const [stmtRid, setStmtRid] = useState(null);
  const [pickMap, setPickMap] = useState({});     // `${자료 id}:${후보 순번}` → 골랐는가(사람이 바꾼 것만)
  const [adoptNode, setAdoptNode] = useState("");  // 비우면 회신을 부른 요청의 목차
  const [adoptNote, setAdoptNote] = useState("");
  const [stmtClaims, setStmtClaims] = useState([]);   // [{claim, quote, opinion, pick}]
  const [stmtNode, setStmtNode] = useState("");
  const [stmtNote, setStmtNote] = useState("");

  useEffect(() => { if (pid) reload(); }, [pid]);
  useEffect(() => { api.listDepartments().then((d) => { setDepts(d); if (d.length) setPromoteDept(d[0].id); }).catch(() => {}); }, []);
  const sel = resources.find((r) => r.id === selId) || null;
  const selLib = sel && sel.source === "library";
  const selProj = sel && sel.source === "project";        // 다른 업무에서 빌려온 자료(보고전 뽑기)
  const selRef = selLib || selProj;                        // 빌려온 것 = 여기서 고칠 수 없다
  useEffect(() => {
    if (sel) setEdit({ name: sel.name, kind: sel.kind, source_org: sel.source_org, base_date: sel.base_date, text: sel.text, note: sel.note || "" });
    setShowText(false);   // 자료를 바꾸면 읽은 내용은 다시 접는다
  }, [selId]); // eslint-disable-line

  async function reload() {
    try {
      const [rs, ev, ol] = await Promise.all([api.listResources(pid), api.listEvidence(pid), api.getOutline(pid)]);
      setResources(rs); setEvidence(ev); setOutline(ol.nodes || []);
      if (rs.length && !rs.find((r) => r.id === selId)) setSelId(rs[0].id);
    } catch (e) { setErr(String(e.message || e)); }
  }
  async function searchLib() {
    try { const rs = await api.listLibResources(null, libQuery); const have = new Set(resources.map((r) => r.id)); setLibResults(rs.filter((r) => !have.has(r.id))); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function importRef(rid) {
    try { await api.addResourceRef(pid, rid); await reload(); setLibResults((v) => v.filter((r) => r.id !== rid)); setSelId(rid); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function unlinkRef() {
    if (!sel) return;
    if (!confirm("이 공통자료 참조를 이 업무에서 해제할까요? (원본은 공통자료실에 그대로 남습니다)")) return;
    try { await api.removeResourceRef(pid, sel.id); setSelId(null); await reload(); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function doPromote() {
    if (!sel || !promoteDept) return;
    const deptName = depts.find((d) => d.id === promoteDept)?.name || "부서";
    if (!confirm(`‘${sel.name}’을(를) 공통자료실 [${deptName}] 폴더로 승격합니다.\n이 자료의 원본이 공통자료실로 옮겨가고, 이 업무는 참조로 바뀝니다. 다른 업무에서도 쓸 수 있게 됩니다. 계속할까요?`)) return;
    try { await api.promoteResource(pid, sel.id, promoteDept); setPromoteOpen(false); await reload(); }
    catch (e) { setErr(String(e.message || e)); }
  }
  const numberMap = flatNumbers(outline);
  const dirty = sel && (edit.name !== sel.name || edit.kind !== sel.kind || edit.source_org !== sel.source_org
    || edit.base_date !== sel.base_date || edit.text !== sel.text || edit.note !== (sel.note || ""));

  // 파일로 자료 등록. 읽어서 본문에 담기까지만 하고 분석은 사람이 누른다(원칙 1).
  async function uploadFile(file) {
    setUploading(true); setErr("");
    try {
      const r = await api.uploadResource(pid, file, form);
      setForm({ ...EMPTY, kind: form.kind }); await reload(); setSelId(r.id);
      if (r.file?.read_note) alert(`‘${file.name}’ 을(를) 읽어 등록했습니다.\n\n${r.file.read_note}`);
    } catch (e) { setErr(String(e.message || e)); } finally { setUploading(false); }
  }
  async function addResource() {
    if (!form.text.trim() && !form.name.trim()) { alert("자료명이나 본문 중 하나는 입력하세요."); return; }
    try { const r = await api.addResource(pid, form); setForm({ ...EMPTY, kind: form.kind }); await reload(); setSelId(r.id); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function saveEdit() {
    if (!sel || !dirty) return;
    try { await api.updateResource(pid, sel.id, edit); await reload(); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function removeResource(rid) {
    if (!confirm("이 자료를 삭제할까요? 연결된 분석도 함께 삭제됩니다.")) return;
    await api.deleteResource(pid, rid); if (selId === rid) setSelId(null); await reload();
  }
  async function runAnalyze() {
    if (!sel) return; setBusy(true); setErr("");
    try { await api.analyzeResource(pid, sel.id, provider); await reload(); }
    catch (e) { setErr(String(e.message || e)); }
    finally { setBusy(false); }
  }
  async function confirmA() {
    // 회신이 요청과 다르면(분석이 '요청한 ○○은 이 자료에 없습니다') 한 번 묻는다. 막지는 않는다 — 판단은 사람이.
    const miss = arr(sel.analysis?.asked_missing);
    const ask = `요청한 것 ${miss.length}가지가 이 회신 자료에 없습니다.\n\n${miss.join("\n")}\n\n`
      + "그래도 이 자료를 근거로 확정할까요?\n(다른 파일이 왔다면 ‘취소’ 후 ‘재요청으로 되돌리기’를 누르세요)";
    if (miss.length && !confirm(ask)) return;
    try { await api.confirmAnalysis(pid, sel.id, miss.length > 0); await reload(); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function reopenRequest() {
    const rq = sel?.reply_of; if (!rq) return;
    const reason = prompt(`‘${rq.need}’ 요청을 다시 ‘요청함’으로 돌립니다.\n`
      + "받은 자료는 지우지 않고 이름 앞에 [요청과 다름]을 붙입니다.\n\n되돌리는 이유(선택):", "받은 파일이 요청한 자료가 아님");
    if (reason === null) return;
    try { await api.reopenRequest(pid, rq.id, reason); await reload(); }
    catch (e) { setErr(String(e.message || e)); }
  }

  // ── 담당자 진술 ──
  // AI는 '쪼개기'만 한다(없는 사실을 채우지 않는다). 근거가 되는 것은 사람이 고른 것뿐이다.
  async function splitStatement() {
    if (!stmtText.trim()) { alert("진술 내용을 입력하세요."); return; }
    setBusy(true); setErr(""); setStmtNote("");
    try {
      const r = await api.addStatement(pid, { text: stmtText, provider });
      setStmtRid(r.resource.id);
      setStmtClaims((r.claims || []).map((c) => ({ ...c, pick: true })));
      setStmtNote(r.fallback
        ? `AI 쪼개기를 쓰지 못해 줄 단위로 나눴습니다${r.reason ? ` (${r.reason})` : ""}. 아래에서 직접 고치세요.`
        : "");
      await reload();
    } catch (e) { setErr(String(e.message || e)); }
    finally { setBusy(false); }
  }
  async function adoptStatement() {
    const picked = stmtClaims.filter((c) => c.pick && c.claim.trim());
    if (!picked.length) { alert("근거로 삼을 주장을 하나 이상 고르세요."); return; }
    try {
      await api.adoptStatement(pid, stmtRid, {
        claims: picked.map(({ claim, quote, opinion }) => ({ claim, quote, opinion })),
        node_uid: stmtNode || null,
      });
      setStmtText(""); setStmtClaims([]); setStmtRid(null); setStmtNote(""); setStmtOpen(false);
      await reload();
    } catch (e) { setErr(String(e.message || e)); }
  }

  // ── 근거 고리: 분석의 주장 후보 → 한 번에 채택 ──
  // 고르는 것은 사람이다(원칙 1). 인용이 원문에 그대로 있는 후보만 처음부터 골라 둔다.
  function candPicked(i, c) { return pickMap[`${sel.id}:${i}`] ?? (c.quote_state === "일치" && !adoptedClaim(c)); }
  function adoptedClaim(c) { return evidence.some((e) => e.resource_id === sel.id && e.claim === c.claim); }
  async function adoptCandidates() {
    const cands = arr(sel.analysis?.claims);
    const picked = cands.filter((c, i) => candPicked(i, c) && !adoptedClaim(c));
    if (!picked.length) { alert("근거로 삼을 주장을 하나 이상 고르세요."); return; }
    const miss = arr(sel.analysis?.asked_missing);
    let force = false;
    if (miss.length) {
      if (!confirm(`요청한 것 ${miss.length}가지가 이 회신 자료에 없습니다.\n\n${miss.join("\n")}\n\n그래도 골라 둔 주장을 근거로 삼을까요?`)) return;
      force = true;
    }
    try {
      const r = await api.adoptClaims(pid, sel.id, { claims: picked.map(({ claim, quote }) => ({ claim, quote })), node_uid: adoptNode || null, force });
      const where = r.node_uid ? `${numberMap[r.node_uid] || ""} ${(outline.find((n) => n.uid === r.node_uid) || {}).title || ""}`.trim() : "목차 연결 없음";
      setAdoptNote(`근거 ${r.created}건을 만들었습니다 → ${where}${r.linked_from_request ? " (요청의 목차)" : ""}`
        + (r.skipped ? ` · 이미 있는 ${r.skipped}건은 건너뜀` : ""));
      setPickMap({});
      await reload();
    } catch (e) { setErr(String(e.message || e)); }
  }

  async function addEvidenceRow() {
    // 빈 주장으로 만든다. 예전엔 '새 주장'을 실제 값으로 넣어, 고치지 않으면 최종본 부록에 그대로 나갔다(2026-11-24 #6).
    const e = await api.addEvidence(pid, { claim: "", resource_id: null, status: "확인 필요" });
    setEvidence((v) => [...v, e]);
  }
  async function patchEvidence(row, patch) {
    // 근거를 고치는 것과 '자료 변경됨'을 확인하는 것은 다른 행위다 → source_changed 는 건드리지 않는다.
    const next = { ...row, ...patch };
    setEvidence((v) => v.map((x) => (x.id === row.id ? next : x)));
    try { await api.updateEvidence(pid, row.id, next); } catch (e) { setErr(String(e.message || e)); }
  }
  async function ackEvidence(row) {
    try {
      await api.ackEvidence(pid, row.id);
      setEvidence((v) => v.map((x) => (x.id === row.id ? { ...x, source_changed: 0 } : x)));
    } catch (e) { setErr(String(e.message || e)); }
  }
  async function delEvidence(id) { await api.deleteEvidence(pid, id); setEvidence((v) => v.filter((x) => x.id !== id)); }

  if (!pid) return <div className="rr-empty">먼저 상단에서 업무를 선택하세요.</div>;

  return (
    <div className={"rr" + cols.cls} ref={cols.ref} style={cols.style}>
      {cols.handles}
      {err &&<div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}

      {/* 좌: 자료 목록 + 등록 */}
      <section className="col left">
        {/* 짧은 경로: 파일이 없어도 담당자가 아는 사실로 근거를 세운다.
            AI는 쪼개기만 하고, 근거가 되는 것은 사람이 고른 것뿐이다. */}
        <button className={"btn wide stmt-toggle" + (stmtOpen ? " on" : "")} onClick={() => setStmtOpen((v) => !v)}>
          {stmtOpen ? "▼" : "▶"} 담당자 진술로 근거 만들기
        </button>
        {stmtOpen && (
          <div className="stmtbox">
            <p className="hint mb">아는 대로 편하게 적으세요. AI는 <b>주장 단위로 쪼개기만</b> 합니다 —
              없는 사실을 채우지 않습니다. 근거가 되는 것은 아래에서 고른 것뿐입니다.</p>
            <textarea className="wide mb" style={{ minHeight: 100 }}
              placeholder={"예)\n어제 폐교 현장 다녀왔고 지붕 일부가 내려앉았음\n기관장이 이번 주 안에 대책 보고하라고 지시\n인근 주민 10여 가구가 민원 넣은 상태"}
              value={stmtText} onChange={(e) => setStmtText(e.target.value)} />
            <button className="btn primary wide" onClick={splitStatement} disabled={busy}>
              {busy ? "쪼개는 중…" : "주장으로 쪼개기"}
            </button>

            {stmtNote && <div className="hint warn mt2">{stmtNote}</div>}
            {stmtClaims.length > 0 && (
              <div className="mt2">
                <p className="eyebrow">근거로 삼을 주장 고르기</p>
                {stmtClaims.map((c, i) => (
                  <div key={i} className={"claimrow" + (c.pick ? " on" : "")}>
                    <input type="checkbox" checked={c.pick}
                      onChange={() => setStmtClaims((v) => v.map((x, k) => (k === i ? { ...x, pick: !x.pick } : x)))} />
                    <textarea value={c.claim} rows={2}
                      onChange={(e) => setStmtClaims((v) => v.map((x, k) => (k === i ? { ...x, claim: e.target.value } : x)))} />
                    {c.opinion && <span className="tag op" title="사실이 아니라 담당자의 의견·추측으로 보입니다">의견</span>}
                  </div>
                ))}
                <label className="lbl mt2">어느 목차에 붙일까요 (선택)</label>
                <select className="wide mb" value={stmtNode} onChange={(e) => setStmtNode(e.target.value)}>
                  <option value="">연결 안 함</option>
                  {outline.map((n) => <option key={n.uid} value={n.uid}>{numberMap[n.uid]} {n.title}</option>)}
                </select>
                <button className="btn primary wide" onClick={adoptStatement}>
                  선택한 {stmtClaims.filter((c) => c.pick).length}건을 근거로 채택
                </button>
                <p className="hint mt2">채택하면 <b>담당자 진술</b> 근거가 됩니다. 초고·검토·최종본에서
                  문서 근거와 구분해 표시됩니다.</p>
              </div>
            )}
          </div>
        )}

        <p className="eyebrow mt">자료 등록</p>
        <input className="wide mb" placeholder="자료명" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <div className="two mb">
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{RESOURCE_KINDS.map((k) => <option key={k}>{k}</option>)}</select>
          <input placeholder="작성기관" value={form.source_org} onChange={(e) => setForm({ ...form, source_org: e.target.value })} />
        </div>
        <input className="wide mb" placeholder="기준일 (예: 2025)" value={form.base_date} onChange={(e) => setForm({ ...form, base_date: e.target.value })} />
        <label className={"btn primary wide filebtn" + (uploading ? " disabled" : "")}>
          {uploading ? "파일 읽는 중…" : "파일에서 등록 (한글·엑셀·워드·PDF)"}
          <input type="file" accept=".hwpx,.hwp,.xlsx,.xlsm,.xls,.docx,.pdf" disabled={uploading}
            onChange={(e) => { const f = e.target.files[0]; e.target.value = ""; if (f) uploadFile(f); }} />
        </label>
        <div className="hint mb">표는 칸 그대로 읽어 담고 원본 파일도 함께 보관합니다. 위에 적은 자료명·기관·기준일이 같이 붙습니다.</div>
        <textarea className="wide mb" style={{ minHeight: 90 }} placeholder="또는, 자료 본문을 여기에 붙여넣으세요" value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
        <button className="btn wide" onClick={addResource}>붙여넣은 내용으로 자료 추가</button>

        <button className="btn wide mt2" onClick={() => { setImportOpen((v) => !v); if (!importOpen) searchLib(); }}>
          {importOpen ? "▼ 공통자료실에서 가져오기" : "▶ 공통자료실에서 가져오기"}
        </button>
        {importOpen && (
          <div className="importbox">
            <div className="two mb">
              <input placeholder="검색어(자료명·기관)" value={libQuery} onChange={(e) => setLibQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchLib()} />
              <button className="btn sm" onClick={searchLib}>검색</button>
            </div>
            {libResults.length === 0 && <div className="hint">검색 결과가 없습니다. (공통자료실에 등록·확정된 자료가 검색됩니다)</div>}
            {libResults.map((r) => (
              <div key={r.id} className="libresult">
                <div className="lrtop"><b>{r.name}</b><span className={"astate s-" + (r.analysis?.state || "분석 전").replace(/\s/g, "")}>{r.analysis?.state === "사용자 확정" ? "확정됨" : (r.analysis?.state || "분석 전")}</span></div>
                <div className="rmeta">{r.dept_name}{r.source_org ? " · " + r.source_org : ""}{r.base_date ? " · " + r.base_date : ""}</div>
                <button className="btn sm primary" onClick={() => importRef(r.id)}>가져오기(참조)</button>
              </div>
            ))}
          </div>
        )}

        <p className="eyebrow mt">자료 목록 ({resources.length})</p>
        {resources.length === 0 && <div className="hint">아직 등록된 자료가 없습니다.</div>}
        {resources.map((r) => (
          <div key={r.id} className={"rcard" + (r.id === selId ? " sel" : "")} onClick={() => setSelId(r.id)}>
            <div className="rtop"><b>{r.name}</b><span className={"astate s-" + (r.analysis?.state || "분석 전").replace(/\s/g, "")}>{STATE_LABEL[r.analysis?.state] || "분석 전"}</span></div>
            <div className="rmeta">
              <span className={"srcbadge " + (r.source === "library" ? "lib" : r.source === "project" ? "proj" : "own")}>{r.source === "library" ? `공통 · ${r.dept_name || "부서"}`
                 : r.source === "project" ? `빌림 · ${r.owner_name || "다른 업무"}` : "이 업무"}</span>
              {r.file && <span className="filebadge" title={r.file.filename}>파일</span>}
              {r.kind}{r.source_org ? " · " + r.source_org : ""}{r.base_date ? " · " + r.base_date : ""}
            </div>
          </div>
        ))}
      </section>

      {/* 중: 선택 자료 (편집 가능) + AI 분석 */}
      <section className="col center">
        {!sel ? <div className="rr-empty">왼쪽에서 자료를 선택하세요.</div> : (
          <>
            <div className="chead"><p className="eyebrow m0">{selProj ? "다른 업무의 자료 (참조)" : selLib ? "공통자료실 자료 (참조)" : "자료 수정"}</p>
              {selRef
                ? <button className="btn ghost sm" onClick={unlinkRef}>참조 해제</button>
                : <span className="headbtns">
                    <button className="btn ghost sm" onClick={() => setPromoteOpen((v) => !v)}>공통자료실로 승격</button>
                    <button className="btn ghost stamp sm" onClick={() => removeResource(sel.id)}>자료 삭제</button>
                  </span>}</div>
            {!selRef && promoteOpen && (
              <div className="promotebox">
                <div className="two mb">
                  <select value={promoteDept || ""} onChange={(e) => setPromoteDept(+e.target.value)}>
                    {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </select>
                  <button className="btn primary sm" onClick={doPromote}>이 폴더로 승격</button>
                </div>
                <div className="hint">원본이 공통자료실로 옮겨가고 이 업무는 참조로 바뀝니다. 분석·확정 상태도 함께 이동합니다.</div>
              </div>
            )}

            {sel.file && (
              <div className="filenote mb">
                원본 파일: <a href={api.resourceFileUrl(pid, sel.id)}>{sel.file.filename}</a>
                <span className="hint"> · {sel.file.file_kind}{sel.file.pages ? ` · ${sel.file.pages}쪽` : ""} · {Math.max(1, Math.round(sel.file.size / 1024)).toLocaleString()}KB</span>
                <div className="hint">AI 분석은 이 파일에서 읽은 내용을 봅니다. 담당자가 옮겨 적으실 필요는 없습니다.</div>
                {sel.file.read_note && <div className="warn">{sel.file.read_note}</div>}
              </div>
            )}

            {selRef ? (
              <div className="libview">
                <div className="libnote">{selProj
                  ? <>이 자료는 <b>‘{sel.owner_name}’ 업무</b>의 자료를 참조한 것입니다(복사가 아닙니다). 수정·분석·확정은 그 업무에서 하며, 여기서는 근거로 사용만 합니다.</>
                  : <>이 자료는 <b>공통자료실({sel.dept_name})</b>의 자료를 참조한 것입니다. 수정·분석·확정은 ‘공통자료실’ 탭에서 하며, 여기서는 근거로 사용만 합니다.</>}</div>
                <div className="rmeta mb">{sel.kind}{sel.source_org ? " · " + sel.source_org : ""}{sel.base_date ? " · " + sel.base_date : ""}</div>
                <div className="rtext">{sel.text || <span className="hint">본문이 없습니다.</span>}</div>
              </div>
            ) : (
            <>
            <input className="wide mb" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} placeholder="자료명" />
            <div className="two mb">
              <select value={edit.kind} onChange={(e) => setEdit({ ...edit, kind: e.target.value })}>{RESOURCE_KINDS.map((k) => <option key={k}>{k}</option>)}</select>
              <input value={edit.source_org} onChange={(e) => setEdit({ ...edit, source_org: e.target.value })} placeholder="작성기관" />
            </div>
            <input className="wide mb" value={edit.base_date} onChange={(e) => setEdit({ ...edit, base_date: e.target.value })} placeholder="기준일" />
            {/* 파일에서 온 자료의 본문은 '원본이 말하는 그대로'다. 편집 칸으로 두면
                (가) 엑셀 수천 자가 화면을 다 차지하고 (나) 실수로 한 글자만 건드려도
                확정이 풀리고 이 자료를 쓰는 근거마다 변경신호가 뜬다. 접어서 읽기만 한다. */}
            {sel.file ? (
              <div className="rotext mb">
                <button className="btn ghost sm" onClick={() => setShowText((v) => !v)}>
                  {showText ? "▼" : "▶"} 파일에서 읽은 내용 ({(sel.text || "").length.toLocaleString()}자)
                </button>
                {showText && <pre className="robody">{sel.text}</pre>}
              </div>
            ) : (
              <textarea className="wide rtextedit" value={edit.text} onChange={(e) => setEdit({ ...edit, text: e.target.value })} placeholder="자료 본문" />
            )}
            <label className="lbl mt">담당자 메모</label>
            <textarea className="wide memo" value={edit.note} onChange={(e) => setEdit({ ...edit, note: e.target.value })}
              placeholder="이 자료를 어떻게 볼 것인지 적어 두세요. (예: ○○과에서 받음, 2024년치는 잠정 / 표 3의 연도별 수치만 필요)" />
            <div className="hint mb">메모는 담당자의 말이라 AI 분석에 넘기지 않고, 근거표·최종본에도 나가지 않습니다. 고쳐도 확정은 풀리지 않습니다.</div>
            <div className="editbar">
              <button className="btn primary" disabled={!dirty} onClick={saveEdit}>{dirty ? "수정 저장" : "저장됨"}</button>
              {dirty && sel.analysis?.state === "사용자 확정" && <span className="warn">저장하면 확정이 해제되고 재분석이 필요합니다.</span>}
            </div>
            </>
            )}

            <div className="analyzebar">
              {selRef ? (
                sel.analysis?.state === "사용자 확정"
                  ? <span className="confirmed">✔ {selProj ? `‘${sel.owner_name}’ 업무에서` : "공통자료실에서"} 확정됨 — 근거로 사용 가능</span>
                  : <span className="warn">{selProj ? `‘${sel.owner_name}’ 업무에서` : "공통자료실에서"} 아직 확정되지 않았습니다. 그곳에서 분석·확정하세요.</span>
              ) : (<>
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>{PROVIDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              <button className="btn primary" disabled={busy} onClick={runAnalyze}>{busy ? "분석 중…" : (sel.analysis?.state === "재분석 필요" ? "다시 분석" : "AI 분석")}</button>
              {(sel.analysis?.state === "분석 완료" || sel.analysis?.state === "재분석 필요") && <button className="btn" onClick={confirmA}>분석 확정</button>}
              {sel.reply_of?.status === "회신옴" && arr(sel.analysis?.asked_missing).length > 0 &&
                <button className="btn ghost stamp" onClick={reopenRequest}>재요청으로 되돌리기</button>}
              {sel.analysis?.state === "사용자 확정" && <span className="confirmed">✔ 사용자 확정됨 — 근거로 사용 가능</span>}
              {sel.analysis?.state === "재분석 필요" && <span className="warn">자료가 수정되어 재분석이 필요합니다.</span>}
              </>)}
            </div>

            {arr(sel.analysis?.asked_missing).length > 0 && (
              <div className="warnbox">
                <b>이 회신에는 요청한 것이 없습니다({arr(sel.analysis.asked_missing).length}가지).</b>
                {sel.reply_of && <> 요청: ‘{sel.reply_of.need}’</>}
                <ul style={{ margin: "6px 0 6px 18px" }}>{arr(sel.analysis.asked_missing).map((x, i) => <li key={i}>{x}</li>)}</ul>
                다른 파일이 왔다면 <b>재요청으로 되돌리기</b>를 누르세요. 그대로 확정하면 최종본 부록에 요청 이름으로 보입니다.
              </div>
            )}
            {sel.analysis?.summary && (
              <div className={"apanel" + (sel.analysis.state === "재분석 필요" ? " stale" : "")}>
                {sel.analysis.state === "재분석 필요" && <div className="staleflag">아래는 수정 전 분석입니다. ‘다시 분석’으로 갱신하세요.</div>}
                <div className="asec"><h5>핵심 요약</h5><p>{sel.analysis.summary}</p></div>
                {arr(sel.analysis.key_points).length > 0 && <div className="asec"><h5>주요 내용·수치</h5><ul>{arr(sel.analysis.key_points).map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
                {arr(sel.analysis.usable_for).length > 0 && <div className="asec"><h5>활용 가능</h5><ul>{arr(sel.analysis.usable_for).map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
                {arr(sel.analysis.cautions).length > 0 && <div className="asec caution"><h5>주의사항</h5><ul>{arr(sel.analysis.cautions).map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
                {sel.analysis.model && <div className="amodel">분석 모델: {sel.analysis.model}</div>}
              </div>
            )}
            {!selRef && arr(sel.analysis?.claims).length > 0 && sel.analysis.state !== "재분석 필요" && (
              <div className="candbox">
                <div className="candhead"><b>근거로 삼을 주장 후보</b> <span className="hint">AI 제안 · 고른 것만 근거가 됩니다</span></div>
                {arr(sel.analysis.claims).map((c, i) => {
                  const done = adoptedClaim(c);
                  return (
                    <label key={i} className={"cand" + (done ? " done" : "") + (c.quote_state === "불일치" ? " bad" : "")}>
                      <input type="checkbox" disabled={done} checked={done || candPicked(i, c)}
                        onChange={(e) => setPickMap((m) => ({ ...m, [`${sel.id}:${i}`]: e.target.checked }))} />
                      <span className="candbody">
                        <span className="candclaim">{c.claim}{done && <em className="hint"> — 채택함</em>}</span>
                        {c.answers && <span className="candans">요청: {c.answers}</span>}
                        <span className="candquote">“{c.quote || "(인용 없음)"}”
                          <span className={"qst q-" + c.quote_state}>{c.quote_state === "일치" ? "원문에 있음" : c.quote_state === "불일치" ? "원문에서 그대로 찾지 못함" : "인용 없음"}</span></span>
                      </span>
                    </label>
                  );
                })}
                <div className="candbar">
                  <select value={adoptNode} onChange={(e) => setAdoptNode(e.target.value)}>
                    <option value="">{sel.reply_of ? "요청의 목차로(자동)" : "목차 연결 안 함"}</option>
                    {outline.map((n) => <option key={n.uid} value={n.uid}>{numberMap[n.uid]} {n.title}</option>)}
                  </select>
                  <button className="btn primary" onClick={adoptCandidates}>고른 것 근거로 채택</button>
                </div>
                <div className="hint">채택하면 이 자료가 확정되고, 주장과 원문 인용이 근거표에 들어갑니다. 원문에서 그대로 찾지 못한 인용은 ‘확인 필요’로 들어갑니다.</div>
                {adoptNote && <div className="sugnote">{adoptNote}</div>}
              </div>
            )}
          </>
        )}
      </section>

      {/* 우: 근거표 */}
      <section className="col right">
        <div className="chead"><p className="eyebrow m0">근거표</p><button className="btn sm" onClick={addEvidenceRow}>+ 근거 추가</button></div>
        <p className="hint mb">주장에 어떤 자료가 근거로 붙는지 연결합니다. 확정된 자료만 신뢰할 수 있는 근거입니다.</p>
        {evidence.length === 0 && <div className="hint">아직 근거가 없습니다.</div>}
        {evidence.map((row, i) => (
          <div className={"ev" + (row.source_changed ? " changed" : "")} key={row.id}>
            <div className="evtop"><span className="evno">{row.ev_no || `E-${String(i + 1).padStart(3, "0")}`}</span>
              {row.source_changed
                ? <span className="chgflag">근거 자료 변경됨 — 원문 확인 필요
                    <button className="ackbtn" title="자료 원문을 다시 보고 이 근거가 아직 유효한지 확인했다면 누르세요" onClick={() => ackEvidence(row)}>확인함</button>
                  </span>
                : null}</div>
            <textarea className="evclaim" value={row.claim} onChange={(e) => patchEvidence(row, { claim: e.target.value })} placeholder="주장·판단을 한 줄로 — 예: 65세 이상 인구가 3년간 늘었다 (최종본 부록에 그대로 나갑니다)" />
            <div className="evrow">
              <select value={row.resource_id || ""} onChange={(e) => patchEvidence(row, { resource_id: e.target.value ? +e.target.value : null })}>
                <option value="">근거 없음</option>
                {resources.map((r) => <option key={r.id} value={r.id}>{r.name}{r.analysis?.state === "사용자 확정" ? " ✔" : ""}</option>)}
              </select>
              <input className="evloc" value={row.locator} onChange={(e) => patchEvidence(row, { locator: e.target.value })} placeholder="위치(쪽/표)" />
            </div>
            {(row.resource_id || row.quote) && (
              <div className="evquote">
                <textarea value={row.quote || ""} onChange={(e) => patchEvidence(row, { quote: e.target.value, quote_state: "" })}
                  placeholder="원문 인용 — 자료 본문에서 글자 그대로 옮긴 구간(초고와 근거 점검이 이것을 씁니다)" />
                {row.quote_state === "불일치" && <span className="qst q-불일치">자료 본문에서 그대로 찾지 못함</span>}
                {row.quote_state === "일치" && <span className="qst q-일치">원문에 있음</span>}
              </div>
            )}
            <div className="evrow">
              <select value={row.node_uid || ""} onChange={(e) => patchEvidence(row, { node_uid: e.target.value || null })}>
                <option value="">목차 연결 안 함</option>
                {outline.map((n) => <option key={n.uid} value={n.uid}>{numberMap[n.uid]} {n.title}</option>)}
              </select>
              <select value={row.status} onChange={(e) => patchEvidence(row, { status: e.target.value })}>{EVIDENCE_STATUS.map((s) => <option key={s}>{s}</option>)}</select>
              <button className="btn ghost stamp sm" onClick={() => delEvidence(row.id)}>삭제</button>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}

function arr(v) { return Array.isArray(v) ? v : []; }
