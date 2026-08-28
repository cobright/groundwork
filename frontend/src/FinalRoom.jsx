import React, { useEffect, useState } from "react";
import { api } from "./api.js";

export default function FinalRoom({ pid }) {
  const [preview, setPreview] = useState(null);
  const [check, setCheck] = useState(null);
  const [includeEvidence, setIncludeEvidence] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => { if (pid) reload(); }, [pid]);
  async function reload() {
    setErr("");
    try { const [pv, fc] = await Promise.all([api.preview(pid), api.finalCheck(pid)]); setPreview(pv); setCheck(fc); }
    catch (e) { setErr(String(e.message || e)); }
  }
  function download() {
    // 브라우저가 직접 다운로드 (같은 오리진의 파일 응답)
    window.location.href = api.exportDocxUrl(pid, includeEvidence);
  }

  if (!pid) return <div className="rr-empty">먼저 상단에서 업무를 선택하세요.</div>;

  return (
    <div className="rr final">
      {err && <div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}

      {/* 좌: 최종 점검 + 내보내기 */}
      <section className="col left">
        <p className="eyebrow">최종 점검</p>
        {!check ? <div className="hint">점검 중…</div> : check.ok ? (
          <div className="okbox">점검 항목이 없습니다. 내보낼 준비가 되었습니다.</div>
        ) : (
          <>
            <div className="hint mb">내보내기 전에 아래를 확인하세요. 막지는 않으니, 확인 후 진행하시면 됩니다.</div>
            {check.items.map((it, i) => (
              <div key={i} className={"checkitem " + (it.level === "중대" ? "crit" : "warn2")}>
                <div className="citop"><span className="clevel">{it.level}</span> {it.label}</div>
                <ul>{it.detail.map((d, k) => <li key={k}>{d}</li>)}</ul>
              </div>
            ))}
          </>
        )}

        <p className="eyebrow mt">내보내기</p>
        <label className="chk mb"><input type="checkbox" checked={includeEvidence} onChange={(e) => setIncludeEvidence(e.target.checked)} /> 근거표를 부록으로 포함</label>
        <button className="btn primary wide" onClick={download}>Word(.docx)로 내보내기</button>
        <p className="hint" style={{ marginTop: 8 }}>내려받은 .docx 는 한글(HWP)에서 열어 최종 서식을 다듬어 제출하시면 됩니다.</p>
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
