import React, { useEffect, useState } from "react";
import { api, RESOURCE_KINDS } from "./api.js";

const PROVIDERS = [["", "기본(.env)"], ["openai", "OpenAI"], ["claude", "Claude"], ["gemini", "Gemini"]];
const STATE_LABEL = { "분석 전": "분석 전", "분석 완료": "분석 완료(미확정)", "재분석 필요": "재분석 필요", "사용자 확정": "확정됨" };
const EMPTY = { name: "", kind: "부서자료", source_org: "", base_date: "", text: "" };
const arr = (v) => (Array.isArray(v) ? v : []);

export default function LibraryRoom() {
  const [depts, setDepts] = useState([]);
  const [deptId, setDeptId] = useState(null);
  const [resources, setResources] = useState([]);
  const [selId, setSelId] = useState(null);
  const [form, setForm] = useState({ ...EMPTY });
  const [edit, setEdit] = useState({ ...EMPTY });
  const [provider, setProvider] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { loadDepts(); }, []);
  useEffect(() => { if (deptId) loadResources(deptId); }, [deptId]);
  const sel = resources.find((r) => r.id === selId) || null;
  useEffect(() => { if (sel) setEdit({ name: sel.name, kind: sel.kind, source_org: sel.source_org, base_date: sel.base_date, text: sel.text }); }, [selId]); // eslint-disable-line

  async function loadDepts() {
    try { const d = await api.listDepartments(); setDepts(d); if (d.length && !d.find((x) => x.id === deptId)) setDeptId(d[0].id); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function loadResources(id) {
    try { const rs = await api.listLibResources(id); setResources(rs); if (rs.length && !rs.find((r) => r.id === selId)) setSelId(rs[0].id); else if (!rs.length) setSelId(null); }
    catch (e) { setErr(String(e.message || e)); }
  }
  const dirty = sel && (edit.name !== sel.name || edit.kind !== sel.kind || edit.source_org !== sel.source_org || edit.base_date !== sel.base_date || edit.text !== sel.text);

  async function addDept() {
    const name = prompt("새 부서 폴더 이름"); if (name === null || !name.trim()) return;
    try { const d = await api.createDepartment(name.trim()); await loadDepts(); setDeptId(d.id); } catch (e) { setErr(String(e.message || e)); }
  }
  async function renameDept(d) {
    const name = prompt("부서 폴더 이름 수정", d.name); if (name === null || !name.trim()) return;
    try { await api.renameDepartment(d.id, name.trim()); await loadDepts(); } catch (e) { setErr(String(e.message || e)); }
  }
  async function delDept(d) {
    if (!confirm(`부서 폴더 '${d.name}'를 삭제할까요?`)) return;
    try { await api.deleteDepartment(d.id); await loadDepts(); } catch (e) { setErr(String(e.message || e)); }
  }
  async function addResource() {
    if (!form.text.trim() && !form.name.trim()) { alert("자료명이나 본문 중 하나는 입력하세요."); return; }
    try { const r = await api.addLibResource({ ...form, dept_id: deptId }); setForm({ ...EMPTY }); await loadResources(deptId); setSelId(r.id); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function saveEdit() {
    if (!sel || !dirty) return;
    try { await api.updateLibResource(sel.id, { ...edit, dept_id: sel.dept_id }); await loadResources(deptId); } catch (e) { setErr(String(e.message || e)); }
  }
  async function removeResource() {
    if (!sel) return;
    if (sel.ref_count > 0 && !confirm(`이 자료를 참조하는 업무가 ${sel.ref_count}건 있습니다. 삭제하면 그 업무 근거에 '원본 삭제됨' 신호가 표시됩니다. 계속할까요?`)) return;
    if (sel.ref_count === 0 && !confirm("이 공통자료를 삭제할까요?")) return;
    try { await api.deleteLibResource(sel.id, sel.ref_count > 0); setSelId(null); await loadResources(deptId); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function runAnalyze() {
    if (!sel) return; setBusy(true); setErr("");
    try { await api.analyzeLibResource(sel.id, provider); await loadResources(deptId); }
    catch (e) { setErr(String(e.message || e)); } finally { setBusy(false); }
  }
  async function confirmA() { await api.confirmLibResource(sel.id); await loadResources(deptId); }

  return (
    <div className="rr">
      {err && <div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}

      {/* 좌: 부서 폴더 */}
      <section className="col left">
        <div className="chead"><p className="eyebrow m0">부서 폴더</p><button className="btn sm" onClick={addDept}>+ 폴더</button></div>
        <p className="hint mb">부서가 생산·관리하는 자료를 여기에 등록하면 여러 업무에서 참조해 씁니다.</p>
        {depts.map((d) => (
          <div key={d.id} className={"dnode" + (d.id === deptId ? " sel" : "")} onClick={() => setDeptId(d.id)}>
            <span className="dtitle">{d.name}</span>
            <span className="ncnt lib">{d.resource_count}</span>
            <span className="deptedit">
              <button className="mini" title="이름 수정" onClick={(e) => { e.stopPropagation(); renameDept(d); }}>✎</button>
              <button className="mini" title="삭제" onClick={(e) => { e.stopPropagation(); delDept(d); }}>✕</button>
            </span>
          </div>
        ))}
      </section>

      {/* 중: 자료 등록 + 목록 */}
      <section className="col center">
        <p className="eyebrow">공통자료 등록{sel ? "" : ""}</p>
        <input className="wide mb" placeholder="자료명" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <div className="two mb">
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{RESOURCE_KINDS.map((k) => <option key={k}>{k}</option>)}</select>
          <input placeholder="작성기관" value={form.source_org} onChange={(e) => setForm({ ...form, source_org: e.target.value })} />
        </div>
        <input className="wide mb" placeholder="기준일 (예: 2025)" value={form.base_date} onChange={(e) => setForm({ ...form, base_date: e.target.value })} />
        <textarea className="wide mb" style={{ minHeight: 80 }} placeholder="자료 본문" value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
        <button className="btn primary wide" disabled={!deptId} onClick={addResource}>이 부서 폴더에 자료 추가</button>

        <p className="eyebrow mt">자료 목록 ({resources.length})</p>
        {resources.length === 0 && <div className="hint">이 폴더에 등록된 자료가 없습니다.</div>}
        {resources.map((r) => (
          <div key={r.id} className={"rcard" + (r.id === selId ? " sel" : "")} onClick={() => setSelId(r.id)}>
            <div className="rtop"><b>{r.name}</b><span className={"astate s-" + (r.analysis?.state || "분석 전").replace(/\s/g, "")}>{STATE_LABEL[r.analysis?.state] || "분석 전"}</span></div>
            <div className="rmeta">{r.kind}{r.source_org ? " · " + r.source_org : ""}{r.base_date ? " · " + r.base_date : ""}{r.ref_count > 0 ? ` · 참조 ${r.ref_count}건` : ""}</div>
          </div>
        ))}
      </section>

      {/* 우: 선택 자료 수정 + 분석 */}
      <section className="col right">
        {!sel ? <div className="cnone">자료를 선택하면 수정·분석할 수 있습니다.</div> : (
          <>
            <div className="chead"><p className="eyebrow m0">자료 수정</p>
              <button className="btn ghost stamp sm" onClick={removeResource}>자료 삭제</button></div>
            <input className="wide mb" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} placeholder="자료명" />
            <div className="two mb">
              <select value={edit.kind} onChange={(e) => setEdit({ ...edit, kind: e.target.value })}>{RESOURCE_KINDS.map((k) => <option key={k}>{k}</option>)}</select>
              <input value={edit.source_org} onChange={(e) => setEdit({ ...edit, source_org: e.target.value })} placeholder="작성기관" />
            </div>
            <input className="wide mb" value={edit.base_date} onChange={(e) => setEdit({ ...edit, base_date: e.target.value })} placeholder="기준일" />
            <textarea className="wide rtextedit" value={edit.text} onChange={(e) => setEdit({ ...edit, text: e.target.value })} placeholder="자료 본문" />
            <div className="editbar">
              <button className="btn primary" disabled={!dirty} onClick={saveEdit}>{dirty ? "수정 저장" : "저장됨"}</button>
              {dirty && sel.ref_count > 0 && <span className="warn">저장 시 이 자료를 참조하는 {sel.ref_count}개 업무에 변경 신호가 갑니다.</span>}
            </div>
            <div className="analyzebar">
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>{PROVIDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              <button className="btn primary" disabled={busy} onClick={runAnalyze}>{busy ? "분석 중…" : (sel.analysis?.state === "재분석 필요" ? "다시 분석" : "AI 분석")}</button>
              {(sel.analysis?.state === "분석 완료" || sel.analysis?.state === "재분석 필요") && <button className="btn" onClick={confirmA}>분석 확정</button>}
              {sel.analysis?.state === "사용자 확정" && <span className="confirmed">✔ 확정됨 — 업무에서 근거로 사용 가능</span>}
            </div>
            {sel.analysis?.summary && (
              <div className={"apanel" + (sel.analysis.state === "재분석 필요" ? " stale" : "")}>
                {sel.analysis.state === "재분석 필요" && <div className="staleflag">수정 전 분석입니다. ‘다시 분석’으로 갱신하세요.</div>}
                <div className="asec"><h5>핵심 요약</h5><p>{sel.analysis.summary}</p></div>
                {arr(sel.analysis.key_points).length > 0 && <div className="asec"><h5>주요 내용·수치</h5><ul>{arr(sel.analysis.key_points).map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
                {arr(sel.analysis.cautions).length > 0 && <div className="asec caution"><h5>주의사항</h5><ul>{arr(sel.analysis.cautions).map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
