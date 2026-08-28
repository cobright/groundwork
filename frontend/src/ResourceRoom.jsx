import React, { useEffect, useState } from "react";
import { api, RESOURCE_KINDS, EVIDENCE_STATUS } from "./api.js";

const PROVIDERS = [["", "기본(.env)"], ["openai", "OpenAI"], ["claude", "Claude"], ["gemini", "Gemini"]];
const STATE_LABEL = { "분석 전": "분석 전", "분석 완료": "분석 완료(미확정)", "재분석 필요": "재분석 필요", "사용자 확정": "확정됨" };
const EMPTY = { name: "", kind: "외부자료", source_org: "", base_date: "", text: "" };

export default function ResourceRoom({ pid }) {
  const [resources, setResources] = useState([]);
  const [evidence, setEvidence] = useState([]);
  const [outline, setOutline] = useState([]);
  const [selId, setSelId] = useState(null);
  const [provider, setProvider] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ ...EMPTY });   // 신규 등록 폼
  const [edit, setEdit] = useState({ ...EMPTY });    // 선택 자료 수정 폼
  const [importOpen, setImportOpen] = useState(false);
  const [libQuery, setLibQuery] = useState("");
  const [libResults, setLibResults] = useState([]);
  const [depts, setDepts] = useState([]);
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [promoteDept, setPromoteDept] = useState(null);

  useEffect(() => { if (pid) reload(); }, [pid]);
  useEffect(() => { api.listDepartments().then((d) => { setDepts(d); if (d.length) setPromoteDept(d[0].id); }).catch(() => {}); }, []);
  const sel = resources.find((r) => r.id === selId) || null;
  const selLib = sel && sel.source === "library";
  useEffect(() => {
    if (sel) setEdit({ name: sel.name, kind: sel.kind, source_org: sel.source_org, base_date: sel.base_date, text: sel.text });
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
  const dirty = sel && (edit.name !== sel.name || edit.kind !== sel.kind || edit.source_org !== sel.source_org || edit.base_date !== sel.base_date || edit.text !== sel.text);

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
  async function confirmA() { await api.confirmAnalysis(pid, sel.id); await reload(); }

  async function addEvidenceRow() {
    const e = await api.addEvidence(pid, { claim: "새 주장", resource_id: null, status: "확인 필요" });
    setEvidence((v) => [...v, e]);
  }
  async function patchEvidence(row, patch) {
    const next = { ...row, ...patch, source_changed: 0 };
    setEvidence((v) => v.map((x) => (x.id === row.id ? next : x)));
    try { await api.updateEvidence(pid, row.id, next); } catch (e) { setErr(String(e.message || e)); }
  }
  async function delEvidence(id) { await api.deleteEvidence(pid, id); setEvidence((v) => v.filter((x) => x.id !== id)); }

  if (!pid) return <div className="rr-empty">먼저 상단에서 업무를 선택하세요.</div>;

  return (
    <div className="rr">
      {err && <div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}

      {/* 좌: 자료 목록 + 등록 */}
      <section className="col left">
        <p className="eyebrow">자료 등록</p>
        <input className="wide mb" placeholder="자료명" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <div className="two mb">
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{RESOURCE_KINDS.map((k) => <option key={k}>{k}</option>)}</select>
          <input placeholder="작성기관" value={form.source_org} onChange={(e) => setForm({ ...form, source_org: e.target.value })} />
        </div>
        <input className="wide mb" placeholder="기준일 (예: 2025)" value={form.base_date} onChange={(e) => setForm({ ...form, base_date: e.target.value })} />
        <textarea className="wide mb" style={{ minHeight: 90 }} placeholder="자료 본문을 붙여넣으세요 (초기 버전은 텍스트 중심)" value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
        <button className="btn primary wide" onClick={addResource}>자료 추가</button>

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
              <span className={"srcbadge " + (r.source === "library" ? "lib" : "own")}>{r.source === "library" ? `공통 · ${r.dept_name || "부서"}` : "이 업무"}</span>
              {r.kind}{r.source_org ? " · " + r.source_org : ""}{r.base_date ? " · " + r.base_date : ""}
            </div>
          </div>
        ))}
      </section>

      {/* 중: 선택 자료 (편집 가능) + AI 분석 */}
      <section className="col center">
        {!sel ? <div className="rr-empty">왼쪽에서 자료를 선택하세요.</div> : (
          <>
            <div className="chead"><p className="eyebrow m0">{selLib ? "공통자료실 자료 (참조)" : "자료 수정"}</p>
              {selLib
                ? <button className="btn ghost sm" onClick={unlinkRef}>참조 해제</button>
                : <span className="headbtns">
                    <button className="btn ghost sm" onClick={() => setPromoteOpen((v) => !v)}>공통자료실로 승격</button>
                    <button className="btn ghost stamp sm" onClick={() => removeResource(sel.id)}>자료 삭제</button>
                  </span>}</div>
            {!selLib && promoteOpen && (
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

            {selLib ? (
              <div className="libview">
                <div className="libnote">이 자료는 <b>공통자료실({sel.dept_name})</b>의 자료를 참조한 것입니다. 수정·분석·확정은 ‘공통자료실’ 탭에서 하며, 여기서는 근거로 사용만 합니다.</div>
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
            <textarea className="wide rtextedit" value={edit.text} onChange={(e) => setEdit({ ...edit, text: e.target.value })} placeholder="자료 본문" />
            <div className="editbar">
              <button className="btn primary" disabled={!dirty} onClick={saveEdit}>{dirty ? "수정 저장" : "저장됨"}</button>
              {dirty && sel.analysis?.state === "사용자 확정" && <span className="warn">저장하면 확정이 해제되고 재분석이 필요합니다.</span>}
            </div>
            </>
            )}

            <div className="analyzebar">
              {selLib ? (
                sel.analysis?.state === "사용자 확정"
                  ? <span className="confirmed">✔ 공통자료실에서 확정됨 — 근거로 사용 가능</span>
                  : <span className="warn">공통자료실에서 아직 확정되지 않았습니다. ‘공통자료실’ 탭에서 분석·확정하세요.</span>
              ) : (<>
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>{PROVIDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              <button className="btn primary" disabled={busy} onClick={runAnalyze}>{busy ? "분석 중…" : (sel.analysis?.state === "재분석 필요" ? "다시 분석" : "AI 분석")}</button>
              {(sel.analysis?.state === "분석 완료" || sel.analysis?.state === "재분석 필요") && <button className="btn" onClick={confirmA}>분석 확정</button>}
              {sel.analysis?.state === "사용자 확정" && <span className="confirmed">✔ 사용자 확정됨 — 근거로 사용 가능</span>}
              {sel.analysis?.state === "재분석 필요" && <span className="warn">자료가 수정되어 재분석이 필요합니다.</span>}
              </>)}
            </div>

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
            <div className="evtop"><span className="evno">E-{String(i + 1).padStart(3, "0")}</span>
              {row.source_changed ? <span className="chgflag">근거 자료 변경됨 — 확인 필요</span> : null}</div>
            <textarea className="evclaim" value={row.claim} onChange={(e) => patchEvidence(row, { claim: e.target.value })} placeholder="주장·판단" />
            <div className="evrow">
              <select value={row.resource_id || ""} onChange={(e) => patchEvidence(row, { resource_id: e.target.value ? +e.target.value : null })}>
                <option value="">근거 없음</option>
                {resources.map((r) => <option key={r.id} value={r.id}>{r.name}{r.analysis?.state === "사용자 확정" ? " ✔" : ""}</option>)}
              </select>
              <input className="evloc" value={row.locator} onChange={(e) => patchEvidence(row, { locator: e.target.value })} placeholder="위치(쪽/표)" />
            </div>
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
function flatNumbers(nodes) {
  const children = {}; nodes.forEach((n) => { const p = n.parent_uid || "_root"; (children[p] = children[p] || []).push(n); });
  Object.values(children).forEach((a) => a.sort((x, y) => x.sort - y.sort));
  const map = {};
  const walk = (pid, prefix) => (children[pid] || []).forEach((n, i) => { const num = prefix + (i + 1); map[n.uid] = num; walk(n.uid, num + "."); });
  walk("_root", ""); return map;
}
