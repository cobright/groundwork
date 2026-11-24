import React, { useEffect, useState } from "react";
import { PROVIDERS, api, REVIEW_STATUS, SEVERITY_ORDER } from "./api.js";
import { flatNumbers } from "./outlineModel.js";
import { useColumns } from "./Columns.jsx";

const KINDS = ["사실확인", "기술검토", "구조검토", "비평"];
const PERSPECTIVES = ["기관장", "예산부서", "사업부서", "평가위원", "의회·이사회"];
const SEV_CLASS = { "중대": "sev-대", "중요": "sev-요", "일반": "sev-반", "참고": "sev-참" };
const KIND_CLASS = { "사실확인": "k-fact", "기술검토": "k-tech", "구조검토": "k-struct", "비평": "k-crit" };

export default function ReviewRoom({ pid }) {
  const cols = useColumns("review", { left: 300, right: 340 }, { left: "검토 범위·목차", right: "검토의견" });
  const [nodes, setNodes] = useState([]);
  const [numbers, setNumbers] = useState({});
  const [uid, setUid] = useState(null);
  const [body, setBody] = useState("");
  const [opinions, setOpinions] = useState([]);
  const [scope, setScope] = useState("node");     // node | whole
  const [provider, setProvider] = useState("");
  const [perspective, setPerspective] = useState("기관장");
  const [running, setRunning] = useState("");      // 실행 중인 검토 종류
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");           // 실행 결과 안내(예: 문서가 길어 일부만 검토)
  const [kindFilter, setKindFilter] = useState("전체");

  useEffect(() => { if (pid) loadAll(); }, [pid]);
  async function loadAll() {
    try {
      const [ol, rv] = await Promise.all([api.getOutline(pid), api.listReview(pid)]);
      const ns = ol.nodes || []; setNodes(ns); setNumbers(flatNumbers(ns)); setOpinions(rv);
      if (ns.length && !ns.find((n) => n.uid === uid)) selectNode(ns[0].uid);
    } catch (e) { setErr(String(e.message || e)); }
  }
  async function selectNode(u) {
    setUid(u); setErr("");
    try { const d = await api.getDraft(pid, u); setBody(d.draft.body || ""); } catch (e) { setErr(String(e.message || e)); }
  }
  async function run(kind) {
    setRunning(kind); setErr(""); setNote("");
    try {
      if (scope === "whole") {
        const r = await api.runReviewWhole(pid, kind, provider, perspective);
        if (r.truncated) setNote("문서가 길어 앞부분만 검토했습니다. 뒷부분은 목차별 검토로 확인하세요.");
      } else await api.runReview(pid, uid, kind, provider, perspective);
      setOpinions(await api.listReview(pid));
    } catch (e) { setErr(String(e.message || e)); }
    finally { setRunning(""); }
  }
  async function patch(o, p) {
    setOpinions((v) => v.map((x) => (x.id === o.id ? { ...x, ...p } : x)));
    try { await api.patchOpinion(pid, o.id, p); } catch (e) { setErr(String(e.message || e)); }
  }
  async function remove(id) { await api.deleteOpinion(pid, id); setOpinions((v) => v.filter((x) => x.id !== id)); }
  // 검토의견 → 자료요청. 무엇을 요청할지는 사람이 고쳐 넣을 수 있게 먼저 보여준다.
  async function toRequest(o) {
    const suggested = (o.needs || "").trim() || (o.problem || "").trim();
    const need = prompt("부서에 요청할 자료를 적으세요.\n(‘자료요청’ 탭에 ‘필요’ 상태로 들어갑니다)", suggested);
    if (need === null || !need.trim()) return;
    try {
      const r = await api.opinionToRequest(pid, o.id, { need: need.trim() });
      setOpinions((v) => v.map((x) => (x.id === o.id ? { ...x, request_id: r.request_id, request_status: r.status } : x)));
      setErr("");
      alert(r.already ? "이미 자료요청으로 올라가 있습니다." : "자료요청에 담았습니다. ‘자료요청’ 탭에서 부서와 기한을 정하세요.");
    } catch (e) { setErr(String(e.message || e)); }
  }

  if (!pid) return <div className="rr-empty">먼저 상단에서 업무를 선택하세요.</div>;

  const factOnlyNode = scope === "whole"; // 사실확인은 전체 불가
  // 현재 범위의 의견
  let list = opinions.filter((o) => (scope === "whole" ? o.node_uid == null : o.node_uid === uid));
  if (kindFilter !== "전체") list = list.filter((o) => o.kind === kindFilter);
  list = [...list].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));
  const critical = opinions.filter((o) => o.severity === "중대" && o.status !== "반영" && o.status !== "반영안함").length;
  const unhandled = opinions.filter((o) => o.status === "미처리").length;

  return (
    <div className={"rr rev" + cols.cls} ref={cols.ref} style={cols.style}>
      {cols.handles}
      {err &&<div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}

      {/* 좌: 범위 + 목차 */}
      <section className="col left">
        <p className="eyebrow">검토 범위</p>
        <div className="scopetoggle">
          <button className={scope === "node" ? "on" : ""} onClick={() => setScope("node")}>목차별</button>
          <button className={scope === "whole" ? "on" : ""} onClick={() => setScope("whole")}>문서 전체</button>
        </div>

        <p className="eyebrow mt">목차</p>
        {nodes.length === 0 && <div className="hint">먼저 목차와 초고를 만드세요.</div>}
        {nodes.map((n) => {
          const cnt = opinions.filter((o) => o.node_uid === n.uid && o.status === "미처리").length;
          return (
            <div key={n.uid} className={"dnode" + (scope === "node" && n.uid === uid ? " sel" : "") + (scope === "whole" ? " dim" : "")}
                 onClick={() => scope === "node" && selectNode(n.uid)}>
              <span className="num">{numbers[n.uid]}</span><span className="dtitle">{n.title}</span>
              {cnt > 0 && <span className="ncnt">{cnt}</span>}
            </div>
          );
        })}
        <div className="revsummary">전체 미처리 <b>{unhandled}</b>{critical > 0 && <span className="critical"> · 중대 미해결 {critical}</span>}</div>
      </section>

      {/* 중: 대상 + 검토자 실행 */}
      <section className="col center">
        <div className="chead">
          <p className="eyebrow m0">{scope === "whole" ? "문서 전체 검토" : (uid ? `${numbers[uid]} ${nodes.find((n) => n.uid === uid)?.title || ""}` : "목차 선택")}</p>
        </div>

        <div className="runopts">
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>{PROVIDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <select value={perspective} onChange={(e) => setPerspective(e.target.value)} title="비평 관점">{PERSPECTIVES.map((p) => <option key={p}>{p}</option>)}</select>
          <span className="hint">관점은 ‘비평’에 적용</span>
        </div>
        <div className="kindbtns">
          {KINDS.map((k) => {
            const disabled = running || (k === "사실확인" && factOnlyNode) || (scope === "node" && !uid);
            return <button key={k} className={"btn kbtn " + (KIND_CLASS[k] || "")} disabled={disabled} onClick={() => run(k)}>
              {running === k ? "실행 중…" : k}{k === "비평" ? `(${perspective})` : ""}</button>;
          })}
        </div>
        {factOnlyNode && <div className="hint mb">사실확인은 문장↔근거 대조라 <b>목차별</b>에서만 실행합니다.</div>}
        {note && <div className="reqmsg" onClick={() => setNote("")}>{note}</div>}

        <p className="eyebrow" style={{ marginTop: 6 }}>검토 대상</p>
        {scope === "whole"
          ? <div className="wholelist">{nodes.map((n) => <div key={n.uid} className="wl"><span className="num">{numbers[n.uid]}</span> {n.title}</div>)}
              <div className="hint" style={{ marginTop: 8 }}>본문이 없는 목차는 검토에서 제외됩니다.</div></div>
          : <div className="revbody">{body || <span className="hint">이 목차에는 확정된 본문이 없습니다. ‘초고 작성’에서 본문을 먼저 만드세요.</span>}</div>}
      </section>

      {/* 우: 검토의견 */}
      <section className="col right">
        <div className="chead"><p className="eyebrow m0">검토의견 {scope === "whole" ? "(문서 전체)" : ""}</p>
          <select className="filter" value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
            <option>전체</option>{KINDS.map((k) => <option key={k}>{k}</option>)}
          </select></div>
        {list.length === 0 && <div className="hint">검토의견이 없습니다. 가운데에서 검토를 실행하세요.</div>}
        {list.map((o) => (
          <div className={"op " + (SEV_CLASS[o.severity] || "")} key={o.id}>
            <div className="optop">
              <span className={"sevtag " + (SEV_CLASS[o.severity] || "")}>{o.severity}</span>
              <span className={"opkind " + (KIND_CLASS[o.kind] || "")}>{o.kind}</span>
              <button className="btn ghost stamp sm opdel" onClick={() => remove(o.id)}>삭제</button>
            </div>
            {o.target_text && <div className="optarget">“{o.target_text}”</div>}
            <div className="opproblem">{o.problem}</div>
            {o.suggestion && <div className="opline"><b>제안</b> {o.suggestion}</div>}
            {o.basis && <div className="opline"><b>근거</b> {o.basis}</div>}
            {o.needs && <div className="opline needs"><b>필요조치</b> {o.needs}</div>}
            <div className="opbar">
              <select value={o.status} onChange={(e) => patch(o, { status: e.target.value })}>{REVIEW_STATUS.map((s) => <option key={s}>{s}</option>)}</select>
              {/* 자료가 필요하다는 것을 여기서 알았는데, 지금까지는 자료요청 화면으로 건너가
                  '자동 수집'을 다시 눌러야 했다. 게다가 자동 수집은 필요조치가 적힌 의견만
                  가져오므로 그 칸이 빈 의견은 아예 넘어오지 않았다. */}
              {o.request_id
                ? <span className="reqdone">자료요청함 · {o.request_status}</span>
                : <button className="btn ghost sm" onClick={() => toRequest(o)}>자료요청으로</button>}
              {(o.status === "반영안함" || o.status === "보류") && (o.severity === "중대" || o.severity === "중요") &&
                <input className="opnote" placeholder="미반영 사유(권장)" value={o.user_note || ""} onChange={(e) => patch(o, { user_note: e.target.value })} />}
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
