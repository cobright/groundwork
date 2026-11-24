import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import { useColumns } from "./Columns.jsx";

export default function FinalRoom({ pid }) {
  const cols = useColumns("final", { left: 300, right: 340 }, { left: "점검·내보내기" });
  const [preview, setPreview] = useState(null);
  const [check, setCheck] = useState(null);
  const [includeEvidence, setIncludeEvidence] = useState(true);
  const [err, setErr] = useState("");
  // 한글(HWPX) 양식
  const [forms, setForms] = useState([]);
  const [formId, setFormId] = useState("");
  const [org, setOrg] = useState("");
  const [pageBreak, setPageBreak] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => { if (pid) reload(); }, [pid]);
  useEffect(() => { loadForms(); }, []);
  async function reload() {
    setErr("");
    try { const [pv, fc] = await Promise.all([api.preview(pid), api.finalCheck(pid)]); setPreview(pv); setCheck(fc); }
    catch (e) { setErr(String(e.message || e)); }
  }
  async function loadForms() {
    try {
      const list = await api.listForms();
      setForms(list);
      if (list.length && !list.find((f) => String(f.id) === String(formId))) setFormId(String(list[0].id));
    } catch (e) { setErr(String(e.message || e)); }
  }
  async function onUpload(e) {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true); setErr(""); setMsg("");
    try {
      const f = await api.uploadForm(file, "", "");
      await loadForms(); setFormId(String(f.id));
      setMsg(f.supported
        ? `양식 ‘${f.name}’을(를) 보관했습니다. 장 ${f.chapters}개짜리 구조를 읽었습니다.`
        : `양식 ‘${f.name}’을(를) 보관했지만 아직 채울 수 없는 구조입니다.`);
    } catch (e2) { setErr(String(e2.message || e2)); }
    finally { setBusy(false); }
  }
  async function removeForm(f) {
    if (!confirm(`양식 ‘${f.name}’을(를) 보관함에서 지울까요?`)) return;
    try { await api.deleteForm(f.id); await loadForms(); } catch (e) { setErr(String(e.message || e)); }
  }
  function download() {
    // 브라우저가 직접 다운로드 (같은 오리진의 파일 응답)
    window.location.href = api.exportDocxUrl(pid, includeEvidence);
  }
  function downloadHwpx() {
    if (!formId) return;
    window.location.href = api.exportHwpxUrl(pid, formId, org, pageBreak);
  }

  if (!pid) return <div className="rr-empty">먼저 상단에서 업무를 선택하세요.</div>;
  const chosen = forms.find((f) => String(f.id) === String(formId));

  return (
    <div className={"rr final" + cols.cls} ref={cols.ref} style={cols.style}>
      {cols.handles}
      {err &&<div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}

      {/* 좌: 최종 점검 + 내보내기 */}
      <section className="col left">
        <p className="eyebrow">최종 점검</p>
        {!check ? <div className="hint">점검 중…</div> : (
          <>
            {check.ok
              ? <div className="okbox">막을 만한 점검 항목이 없습니다. 내보낼 준비가 되었습니다.</div>
              : <div className="hint mb">내보내기 전에 아래를 확인하세요. 막지는 않으니, 확인 후 진행하시면 됩니다.</div>}
            {/* '참고'는 준비 완료여도 보여 준다 — 담당자 진술처럼 알고 내보내야 하는 것들 */}
            {check.items.map((it, i) => (
              <div key={i} className={"checkitem " + (it.level === "중대" ? "crit" : it.level === "참고" ? "note" : "warn2")}>
                <div className="citop"><span className="clevel">{it.level}</span> {it.label}</div>
                <ul>{it.detail.map((d, k) => <li key={k}>{d}</li>)}</ul>
              </div>
            ))}
          </>
        )}

        <p className="eyebrow mt">내보내기</p>
        <label className="chk mb"><input type="checkbox" checked={includeEvidence} onChange={(e) => setIncludeEvidence(e.target.checked)} /> 근거표를 부록으로 포함</label>
        <button className="btn primary wide" onClick={download}>Word(.docx)로 내보내기</button>
        <p className="hint" style={{ marginTop: 8 }}>
          문서 유형에 따라 서식이 갈립니다 — <b>계획서</b>는 표지와 번호 붙은 장 제목으로,
          <b> 보고전</b>은 머리글(부서·이름·날짜)이 붙은 <b>한 쪽짜리 개조식</b>으로 나옵니다.
          부서·이름은 위쪽 <b>설정</b>에서 한 번 넣어 두시면 됩니다. 한글에서 열어 다듬어 제출하세요.</p>

        <p className="eyebrow mt">한글 양식에 채워 내보내기</p>
        {msg && <div className="reqmsg" onClick={() => setMsg("")}>{msg}</div>}
        {forms.length === 0 ? (
          <div className="hint mb">보관된 양식이 없습니다. 늘 쓰시는 <b>.hwpx 양식</b>을 한 번 올려두면
            그 구조(표지·목차·장 제목·개조식 서식) 그대로 최종본이 채워집니다.</div>
        ) : (
          <>
            <label className="lbl">사용할 양식</label>
            <select className="wide mb" value={formId} onChange={(e) => setFormId(e.target.value)}>
              {forms.map((f) => <option key={f.id} value={f.id}>{f.supported ? f.name : `${f.name} (지원 안 됨)`}</option>)}
            </select>
            {chosen && !chosen.supported &&
              <div className="formwarn">이 양식은 아직 채울 수 없습니다.<br />{chosen.reason}</div>}
            {chosen && chosen.supported && chosen.reason &&
              <div className="hint mb">{chosen.reason}</div>}
            <div className="formrow mb">
              <input placeholder="기관명 (예: ○○군)" value={org} onChange={(e) => setOrg(e.target.value)} />
              <button className="btn ghost stamp sm" title="이 양식을 보관함에서 지웁니다"
                      onClick={() => removeForm(forms.find((f) => String(f.id) === String(formId)))}>양식 삭제</button>
            </div>
            <label className="chk mb"><input type="checkbox" checked={pageBreak}
              onChange={(e) => setPageBreak(e.target.checked)} /> 장(Ⅰ, Ⅱ…)마다 새 쪽에서 시작</label>
            <button className="btn primary wide" disabled={!chosen || !chosen.supported}
                    onClick={downloadHwpx}>한글(.hwpx)로 내보내기</button>
          </>
        )}
        <label className="btn wide upload-lbl">
          {busy ? "올리는 중…" : "+ 양식 올리기 (.hwpx)"}
          <input type="file" accept=".hwpx" onChange={onUpload} disabled={busy} hidden />
        </label>
        <p className="hint" style={{ marginTop: 8 }}>양식은 <b>구조만</b> 빌려 씁니다. 목차가 양식의 장 수보다
          많으면 장을 늘리고, 적으면 줄입니다. 목차 쪽번호는 실제 쪽수를 알 수 없어 비워 두니
          한글에서 확인 후 채워 주세요.</p>
      </section>

      {/* 중·우: 미리보기 */}
      <section className="col center wide-preview">
        <div className="chead"><p className="eyebrow m0">최종본 미리보기</p>
          <button className="btn sm ghost" onClick={reload}>새로고침</button></div>
        {!preview ? <div className="hint">불러오는 중…</div> : (
          <div className="docpreview">
            <h1 className="doctitle">{preview.name || "제목 없음"}</h1>
            {preview.doc_type && <div className="docsub">{preview.doc_type}</div>}
            {preview.sections.length === 0 && <div className="hint">목차가 없습니다.</div>}
            {preview.sections.map((s) => (
              <div key={s.uid} className="docsec">
                <div className={"dochead lv" + Math.min(s.depth, 4)}>{s.number} {s.title}</div>
                {(s.body || "").trim()
                  ? (s.body || "").split("\n").filter((l) => l.trim()).map((line, i) => {
                      const flag = line.includes("[확인 필요") || line.includes("[추정");
                      return <p key={i} className={"docpara" + (flag ? " flagline" : "")}>{line}</p>;
                    })
                  : <p className="docpara empty">(본문 없음)</p>}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
