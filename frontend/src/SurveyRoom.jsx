import React, { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { flatNumbers } from "./outlineModel.js";
import { useColumns } from "./Columns.jsx";

// 주민 설문 — "설계한 설문지가 곧 분석 틀이다"(docs/design/survey.md).
// 계획서의 주장 → 무엇으로 받치나(통계? 설문?) → 문항 → 분석 계획을 **수집 전에** 정한다.
// 지금 만든 것은 ①~④. ⑤수집은 폼(워크벤치 밖)에서 하고, ⑥정리부터는 구글폼·네이버폼의
// 실물 내보내기 파일을 받은 뒤에 만든다 — 그래서 띠에 보이되 흐리게 둔다(숨기지 않는다, 원칙 5).

const STEPS = [
  ["map", "① 근거 지도"], ["items", "② 문항 설계"], ["check", "③ 점검"], ["form", "④ 폼으로 옮기기"],
  [null, "⑤ 수집"], [null, "⑥ 정리"], [null, "⑦ 분석"], [null, "⑧ 확정"],
];
const BASES = ["미정", "설문", "통계", "진술"];
const BASIS_HINT = {
  "설문": "주민의 원함·불만·선호·의향 — 설문으로만 알 수 있는 것",
  "통계": "인구·시설 수처럼 공식 통계·기관 자료로 증명할 것 — 설문으로 재면 틀린다",
  "진술": "담당자가 아는 사실(운영 방식·예산 등)",
  "미정": "아직 정하지 않음",
};
const QTYPES = ["단일", "복수", "척도", "순위", "숫자", "주관식"];
const CHOICE = new Set(["단일", "복수", "척도", "순위"]);
const METHODS = ["온라인 폼", "현장 대리 입력", "온라인 폼 + 현장 대리 입력", "종이 설문"];
const LEVEL_CLASS = { "중요": "sev-요", "일반": "sev-반", "참고": "sev-참" };
const SCALE5 = ["매우 불만족", "불만족", "보통", "만족", "매우 만족"];

export default function SurveyRoom({ pid }) {
  const cols = useColumns("survey", { left: 300, right: 340 }, { left: "설문·조사 개요", right: "점검" });
  const [list, setList] = useState([]);
  const [sid, setSid] = useState(null);
  const [full, setFull] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [cards, setCards] = useState({});
  const [numbers, setNumbers] = useState({});
  const [step, setStep] = useState("map");
  const [focus, setFocus] = useState(null);         // 점검에서 누른 문항/주장 — 가운데에서 눈에 띄게
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState({});              // 폼 설정 점검표 체크(이 화면에서만 — 폼은 밖에 있다)
  const center = useRef(null);

  useEffect(() => { setSid(null); setFull(null); if (pid) loadAll(); }, [pid]);
  async function loadAll(keep) {
    try {
      const [ls, ol] = await Promise.all([api.listSurveys(pid), api.getOutline(pid)]);
      setList(ls); const ns = ol.nodes || []; setNodes(ns); setCards(ol.cards || {}); setNumbers(flatNumbers(ns));
      const pick = keep && ls.find((s) => s.id === keep) ? keep : (ls[0] && ls[0].id);
      if (pick) await open(pick); else { setSid(null); setFull(null); }
    } catch (e) { setErr(String(e.message || e)); }
  }
  async function open(id) {
    setSid(id); setErr(""); setFocus(null); setDone({});
    try { setFull(await api.getSurvey(id)); } catch (e) { setErr(String(e.message || e)); }
  }
  // 모든 쓰기는 설문 전체를 돌려준다 → 점검이 곧바로 따라온다.
  async function run(p, after) {
    setErr("");
    try { const r = await p; setFull(r); if (after) after(r); return r; }
    catch (e) { setErr(String(e.message || e)); try { setFull(await api.getSurvey(sid)); } catch { /* 그대로 둔다 */ } }
  }
  async function create() {
    setBusy(true);
    try {
      const r = await api.createSurvey(pid, { title: list.length ? `주민 설문 ${list.length + 1}` : "주민 설문" });
      await loadAll(r.survey.id); setStep("map");
    } catch (e) { setErr(String(e.message || e)); } finally { setBusy(false); }
  }
  async function remove() {
    let w = null;
    try { w = await api.surveyDeletePreview(sid); } catch (e) { setErr(String(e.message || e)); return; }
    if (!confirm(`설문 ‘${w.title}’을(를) 지웁니다.\n\n· 근거 지도의 주장 ${w.claims}건이 삭제됩니다\n· 문항 ${w.questions}개가 삭제됩니다\n\n`
      + `자료요청으로 넘긴 항목은 ‘자료요청’ 탭에 그대로 남습니다. 되돌릴 수 없습니다. 계속할까요?`)) return;
    try { await api.deleteSurvey(sid); await loadAll(); } catch (e) { setErr(String(e.message || e)); }
  }
  function saveSurvey(k, v) {
    const cur = full.survey[k];
    if (String(cur ?? "") === String(v ?? "")) return;
    run(api.updateSurvey(sid, { [k]: v })).then(() => api.listSurveys(pid).then(setList).catch(() => {}));
  }
  function goTo(o) {
    if (o.question_id) { setStep("items"); setFocus("q" + o.question_id); }
    else if (o.claim_id) { setStep("map"); setFocus("c" + o.claim_id); }
  }
  // 단계를 바꾸면 맨 위에서 시작한다(점검에서 눌러 온 경우는 아래 효과가 그 자리로 옮긴다).
  useEffect(() => { if (center.current) center.current.scrollTop = 0; }, [step, sid]);
  useEffect(() => {
    if (!focus || !center.current) return;
    const el = center.current.querySelector(`[data-focus="${focus}"]`);
    if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focus, step, full]);

  if (!pid) return <div className="rr-empty">먼저 상단에서 업무를 선택하세요.</div>;

  const sv = full && full.survey;
  const claims = (full && full.claims) || [];
  const qs = (full && full.questions) || [];
  const check = (full && full.check) || [];
  const qnum = Object.fromEntries(qs.map((q, i) => [q.id, i + 1]));
  const heavy = check.filter((o) => o.level === "중요").length;
  const stepState = {
    map: claims.length > 0 && !claims.some((c) => c.basis === "미정"),
    items: qs.length > 0 && !check.some((o) => o.kind === "구조" && o.level === "중요"),
    check: qs.length > 0 && heavy === 0,
    form: !!(sv && sv.exported_at),
  };
  const stepNote = {
    map: `주장 ${claims.length}`, items: `문항 ${qs.length}`,
    check: heavy ? `중요 ${heavy}` : (qs.length ? "중요 없음" : "—"),
    form: sv && sv.exported_at ? "내려받음" : "—",
  };

  return (
    <div className={"rr sv" + cols.cls} ref={cols.ref} style={cols.style}>
      {cols.handles}
      {err && <div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}

      {/* 좌: 설문 고르기 + 단계 띠 + 조사 개요 */}
      <section className="col left">
        <p className="eyebrow">설문</p>
        <div className="sv-pick">
          {list.length > 0 && (
            <select value={sid || ""} onChange={(e) => open(+e.target.value)}>
              {list.map((s) => <option key={s.id} value={s.id}>{s.title} (문항 {s.questions})</option>)}
            </select>)}
          <button className="btn sm" disabled={busy} onClick={create}>새 설문</button>
        </div>
        {!sv && (
          <div className="hint">
            설문은 계획서의 <b>주장을 받치는 근거</b>입니다. 결과를 받은 뒤 “이걸로 무엇을 말할 수 있나”를 찾으면
            늦습니다 — 빠진 문항은 되살릴 수 없습니다. 그래서 <b>주장 → 문항 → 분석 계획</b>을 수집 전에 정합니다.
          </div>)}

        {sv && (<>
          <div className="sv-steps" role="list">
            {STEPS.map(([k, label]) => (
              <button key={label} type="button" role="listitem" disabled={!k}
                className={"sv-step" + (!k ? " later" : "") + (k && stepState[k] ? " done" : "") + (k === step ? " now" : "")}
                title={k ? "" : "응답 파일 정리·분석은 구글폼·네이버폼 실물 내보내기 파일을 받은 뒤 만듭니다"}
                onClick={() => k && setStep(k)}>
                <span className="sc-seal" />
                <span className="sv-step-l">{label}</span>
                {k && <span className="sv-step-n">{stepNote[k]}</span>}
              </button>))}
          </div>

          <p className="eyebrow mt">조사 개요</p>
          <div className="hint">결과를 인용하는 모든 자리에 이 조건이 따라다닙니다 — 숫자를 의심받는 이유는 대개 숫자가 아니라 <b>조건이 안 보여서</b>입니다.</div>
          <div className="cf mt8" key={"ov" + sv.id}>
            <label>조사명</label>
            <input defaultValue={sv.title} onBlur={(e) => saveSurvey("title", e.target.value)} />
          </div>
          <div className="cf" key={"tg" + sv.id}>
            <label>대상</label>
            <input defaultValue={sv.target} placeholder="예: 관내 경로당 회원(65세 이상)" onBlur={(e) => saveSurvey("target", e.target.value)} />
          </div>
          <div className="cf">
            <label>방식</label>
            <select value={sv.method} onChange={(e) => saveSurvey("method", e.target.value)}>
              {METHODS.map((m) => <option key={m}>{m}</option>)}
            </select>
          </div>
          <div className="cf sv-two" key={"pd" + sv.id}>
            <div><label>시작</label><input type="date" defaultValue={sv.period_from} onBlur={(e) => saveSurvey("period_from", e.target.value)} /></div>
            <div><label>끝</label><input type="date" defaultValue={sv.period_to} onBlur={(e) => saveSurvey("period_to", e.target.value)} /></div>
          </div>
          <div className="cf sv-two" key={"pp" + sv.id + ":" + sv.population + ":" + sv.margin}>
            <div><label>대상 인구(명)</label>
              <input type="number" min="0" defaultValue={sv.population || ""} placeholder="확정 근거의 숫자"
                onBlur={(e) => saveSurvey("population", Math.max(0, parseInt(e.target.value || "0", 10) || 0))} /></div>
            <div><label>오차범위(±%p)</label>
              <input type="number" step="0.5" min="0.5" max="20" defaultValue={sv.margin}
                onBlur={(e) => { const v = parseFloat(e.target.value); if (v > 0) saveSurvey("margin", v); }} /></div>
          </div>
          <div className="sv-target">
            목표 응답 <b>{(full.target_n || 0).toLocaleString()}명</b>
            <span>95% 신뢰수준 · ±{sv.margin}%p{sv.population ? ` · 대상 ${sv.population.toLocaleString()}명` : " · 대상 인구를 적으면 줄어듭니다"}</span>
          </div>
          <div className="sv-del"><button className="btn ghost stamp sm" onClick={remove}>이 설문 지우기</button></div>
        </>)}
      </section>

      {/* 중: 단계별 작업 */}
      <section className="col center" ref={center}>
        {!sv ? <div className="empty">아직 설문이 없습니다. 왼쪽의 <b>새 설문</b>으로 시작하세요.</div>
          : step === "map" ? <MapStep {...{ sid, nodes, numbers, cards, claims, qs, qnum, run, focus, setStep, setFocus, setMsg }} />
          : step === "items" || step === "check" ? <ItemsStep {...{ sid, claims, qs, qnum, run, focus, setFocus }} />
          : <FormStep {...{ sid, full, done, setDone, setMsg, reload: () => open(sid) }} />}
        {msg && <div className="reqmsg sv-msg" onClick={() => setMsg("")}>{msg}</div>}
      </section>

      {/* 우: ③ 점검 — 검토자처럼 의견만 낸다(문항을 고치지 않는다) */}
      <section className="col right">
        <div className="chead"><p className="eyebrow m0">③ 점검</p>
          {sv && <span className="count">중요 {heavy} · 전체 {check.length}</span>}</div>
        {sv && <div className="sv-chkhint">규칙으로 짚은 <b>의견</b>입니다. 고칠지는 담당자가 정합니다. 누르면 그 자리로 갑니다.</div>}
        {sv && check.length === 0 && <div className="hint">짚을 것이 없습니다.</div>}
        {check.map((o, i) => (
          <div key={i} className={"op sv-op " + (LEVEL_CLASS[o.level] || "") + (o.question_id || o.claim_id ? " link" : "")}
            onClick={() => goTo(o)}>
            <div className="optop">
              <span className={"sevtag " + (LEVEL_CLASS[o.level] || "")}>{o.level}</span>
              <span className="opkind">{o.kind}</span>
            </div>
            <div className="opproblem" dangerouslySetInnerHTML={{ __html: bold(o.text) }} />
          </div>))}
      </section>
    </div>
  );
}

// 점검 문구의 **굵게**만 살린다(나머지는 글자 그대로).
function bold(t) {
  const esc = String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return esc.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
}

// ────────────── ① 근거 지도 ──────────────
function MapStep({ sid, nodes, numbers, cards, claims, qs, run, focus, setStep, setFocus, setMsg }) {
  const byNode = {};
  claims.forEach((c) => { (byNode[c.node_uid || ""] = byNode[c.node_uid || ""] || []).push(c); });
  const orphan = byNode[""] || [];
  const qcount = (cid) => qs.filter((q) => q.claim_id === cid).length;

  async function addFor(uid) {
    // 집필카드의 핵심 메시지가 있으면 첫 주장으로 제안한다(고쳐 쓰는 것은 사람).
    const first = !(byNode[uid] || []).length && cards[uid] && (cards[uid].message || "").trim();
    await run(api.addClaim(sid, { node_uid: uid, claim: first || "", basis: "미정" }));
  }
  async function addQuestionFor(c) {
    await run(api.addQuestion(sid, { claim_id: c.id, text: "", qtype: "단일", options: [] }),
      (r) => { setStep("items"); setFocus("q" + r.new_id); });
  }
  async function toRequest(c) {
    const need = prompt("부서에 요청할 통계 자료를 적으세요.\n(‘자료요청’ 탭에 ‘필요’ 상태로 들어갑니다)", `통계 자료: ${c.claim}`);
    if (need === null || !need.trim()) return;
    try {
      const r = await api.claimToRequest(sid, c.id, need.trim());
      setMsg(r.already ? "이미 자료요청으로 올라가 있습니다." : "자료요청에 담았습니다. ‘자료요청’ 탭에서 부서와 기한을 정하세요.");
      await run(api.getSurvey(sid));
    } catch (e) { setMsg(String(e.message || e)); }
  }
  function delClaim(c) {
    const n = qcount(c.id);
    if (!confirm(`이 주장을 지웁니다.${n ? `\n\n· 이 주장에 붙은 문항 ${n}개는 남고, 연결만 끊깁니다` : ""}\n\n계속할까요?`)) return;
    run(api.deleteClaim(sid, c.id));
  }

  function row(c) {
    const n = qcount(c.id);
    return (
      <div key={c.id} className={"sv-claim" + (focus === "c" + c.id ? " focus" : "")} data-focus={"c" + c.id}>
        <textarea className="sv-claim-t" rows={1} defaultValue={c.claim} placeholder="이 항목이 내세우는 주장 — 예: 주민이 건강관리 프로그램을 가장 원한다"
          onBlur={(e) => e.target.value.trim() !== c.claim && run(api.updateClaim(sid, c.id, { claim: e.target.value }))} />
        <div className="sv-claim-bar">
          <div className="sv-seg" role="radiogroup" aria-label="무엇으로 받치나">
            {BASES.map((b) => (
              <button key={b} type="button" role="radio" aria-checked={c.basis === b} title={BASIS_HINT[b]}
                className={"b-" + b + (c.basis === b ? " on" : "")}
                onClick={() => c.basis !== b && run(api.updateClaim(sid, c.id, { basis: b }))}>{b}</button>))}
          </div>
          {c.basis === "설문" && <button className="btn ghost sm" onClick={() => addQuestionFor(c)}>문항 {n ? `${n}개 · ` : ""}더하기</button>}
          {c.basis === "통계" && (c.request_id
            ? <span className="reqdone">자료요청함 · {c.request_status}</span>
            : <button className="btn ghost sm" onClick={() => toRequest(c)}>자료요청으로</button>)}
          {c.basis !== "설문" && n > 0 && <span className="sv-warn">문항 {n}개가 붙어 있음</span>}
          {!c.node_uid && (
            <select className="sv-relink" value="" onChange={(e) => e.target.value && run(api.updateClaim(sid, c.id, { node_uid: e.target.value }))}>
              <option value="">목차에 다시 잇기…</option>
              {nodes.map((x) => <option key={x.uid} value={x.uid}>{numbers[x.uid]} {x.title}</option>)}
            </select>)}
          <button className="mini sv-x" title="주장 지우기" onClick={() => delClaim(c)}>✕</button>
        </div>
      </div>
    );
  }

  return (
    <div className="sv-map">
      <div className="chead"><p className="eyebrow m0">① 근거 지도 — 이 항목의 주장을 무엇으로 받치나</p></div>
      <div className="sv-lead">
        <b>통계로 증명할 수 있는 것은 설문으로 묻지 않습니다</b>(군의 연령 분포를 설문으로 재면 틀리고 문항만 길어집니다).
        설문은 <b>주민의 원함·불만·선호·의향</b>처럼 설문으로만 알 수 있는 것에 씁니다.
        통계로 받칠 주장은 자료요청으로, 설문으로 받칠 주장은 문항으로 이어집니다.
      </div>
      {nodes.length === 0 && <div className="empty">목차가 없습니다. ‘목차 편집’에서 목차를 먼저 세우면 항목마다 주장을 적을 수 있습니다.</div>}
      {nodes.map((n) => (
        <div key={n.uid} className="sv-node">
          <div className="sv-node-h">
            <span className="num">{numbers[n.uid]}</span><span className="sv-node-t">{n.title}</span>
            <button className="btn ghost sm" onClick={() => addFor(n.uid)}>+ 주장</button>
          </div>
          {(byNode[n.uid] || []).map(row)}
        </div>))}
      {orphan.length > 0 && (
        <div className="sv-node orphan">
          <div className="sv-node-h"><span className="sv-node-t">목차 연결이 끊긴 주장</span>
            <span className="hint">목차를 갈아끼우면 연결만 끊깁니다. 다시 이을 항목을 고르세요.</span></div>
          {orphan.map(row)}
        </div>)}
    </div>
  );
}

// ────────────── ② 문항 설계 ──────────────
function ItemsStep({ sid, claims, qs, qnum, run, focus, setFocus }) {
  function add(after) {
    run(api.addQuestion(sid, { text: "", qtype: "단일", options: [], after_id: after || null }),
      (r) => setFocus("q" + r.new_id));
  }
  function move(i, d) {
    const ids = qs.map((q) => q.id); const j = i + d;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    run(api.orderQuestions(sid, ids));
  }
  function del(q) {
    const refs = qs.filter((x) => x.id !== q.id && ((x.cross_with || []).includes(q.id) || Object.values(x.branch || {}).includes(q.id)));
    if (!confirm(`${qnum[q.id]}번 문항을 지웁니다.`
      + (refs.length ? `\n\n· ${refs.map((x) => qnum[x.id] + "번").join(", ")} 문항의 분석 계획·분기가 이 문항을 가리킵니다 — 점검에 표시되니 다시 고르세요` : "")
      + "\n\n계속할까요?")) return;
    run(api.deleteQuestion(sid, q.id));
  }
  return (
    <div className="sv-items">
      <div className="chead"><p className="eyebrow m0">② 문항 설계 — 문항마다 받치는 주장과 분석 계획</p>
        <button className="btn sm" onClick={() => add(qs.length ? qs[qs.length - 1].id : null)}>+ 문항</button></div>
      <div className="sv-lead">
        <b>분석은 설문 전에 정합니다.</b> 문항마다 “무엇과 견줄지”(예: 이용 의향 × 연령대)를 미리 고르면
        결과가 들어오는 순간 집계가 정해지고, 결과를 본 뒤 유리한 것만 골라 쓰는 일도 막힙니다.
        연령대·지역(읍면 등) 같은 <b>응답자 특성 문항</b>의 보기는 주민등록 통계 구분과 똑같이 만드세요.
      </div>
      {qs.length === 0 && <div className="empty">문항이 없습니다. <b>+ 문항</b>을 누르거나, 근거 지도에서 ‘설문’으로 정한 주장의 <b>문항 더하기</b>로 시작하세요.</div>}
      {qs.map((q, i) => <Question key={q.id} {...{ sid, q, i, qs, qnum, claims, run, focus, add, move, del }} />)}
    </div>
  );
}

function Question({ sid, q, i, qs, qnum, claims, run, focus, add, move, del }) {
  const save = (patch) => run(api.updateQuestion(sid, q.id, patch));
  const choice = CHOICE.has(q.qtype);
  const opts = (q.options || []).filter((o) => o.trim());
  const others = qs.filter((x) => x.id !== q.id);
  const crossable = [...others.filter((x) => x.profile), ...others.filter((x) => !x.profile)];
  function toggleCross(id) {
    const cur = q.cross_with || [];
    save({ cross_with: cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id] });
  }
  function setBranch(opt, v) {
    const b = { ...(q.branch || {}) };
    if (!v) delete b[opt]; else b[opt] = v === "end" ? "end" : +v;
    save({ branch: b });
  }
  function setType(t) {
    const patch = { qtype: t };
    if (t === "척도" && !opts.length) patch.options = SCALE5;     // 빈 척도에는 흔한 5단계를 깔아 준다(고쳐 쓴다)
    if (t !== "단일" && Object.keys(q.branch || {}).length) patch.branch = {};
    save(patch);
  }
  const dead = (q.cross_with || []).filter((x) => !qnum[x]);
  return (
    <div className={"sv-q" + (focus === "q" + q.id ? " focus" : "") + (q.profile ? " profile" : "")} data-focus={"q" + q.id}>
      <div className="sv-q-h">
        <span className="sv-q-no">{i + 1}</span>
        <textarea className="sv-q-t" rows={1} defaultValue={q.text} placeholder="문항 글 — 한 문항에는 한 가지만 묻습니다"
          onBlur={(e) => e.target.value.trim() !== q.text && save({ text: e.target.value })} />
        <div className="sv-q-move">
          <button className="mini" title="위로" disabled={i === 0} onClick={() => move(i, -1)}>▲</button>
          <button className="mini" title="아래로" disabled={i === qs.length - 1} onClick={() => move(i, 1)}>▼</button>
          <button className="mini" title="문항 지우기" onClick={() => del(q)}>✕</button>
        </div>
      </div>
      <div className="sv-q-row">
        <label>유형
          <select value={q.qtype} onChange={(e) => setType(e.target.value)}>{QTYPES.map((t) => <option key={t}>{t}</option>)}</select></label>
        {q.qtype === "순위" && <label>몇 순위까지
          <input type="number" min="1" max="10" defaultValue={q.rank_k} key={"rk" + q.rank_k}
            onBlur={(e) => { const v = parseInt(e.target.value, 10); if (v && v !== q.rank_k) save({ rank_k: v }); }} /></label>}
        <label className="chk"><input type="checkbox" checked={q.required} onChange={(e) => save({ required: e.target.checked })} /> 필수</label>
        {(q.qtype === "단일" || q.qtype === "복수") &&
          <label className="chk"><input type="checkbox" checked={q.other_allowed} onChange={(e) => save({ other_allowed: e.target.checked })} /> 기타(직접 입력)</label>}
        <label className="chk" title="연령대·지역처럼 응답자를 나누는 문항 — 분석의 '× 연령대'에 쓰이고, 실제 인구와 견주는 데 쓰입니다">
          <input type="checkbox" checked={q.profile} onChange={(e) => save({ profile: e.target.checked })} /> 응답자 특성</label>
      </div>
      {choice && (
        <div className="sv-q-opts">
          <label>보기 <span className="hint">한 줄에 하나</span></label>
          <textarea rows={Math.max(3, opts.length + 1)} defaultValue={(q.options || []).join("\n")} key={"op" + (q.options || []).join("|")}
            onBlur={(e) => {
              const v = e.target.value.split("\n").map((s) => s.trim()).filter(Boolean);
              if (v.join("\n") !== opts.join("\n")) save({ options: v });
            }} />
        </div>)}
      {!q.profile && (
        <div className="sv-q-row">
          <label className="grow">받치는 주장
            <select value={q.claim_id || ""} onChange={(e) => save({ claim_id: e.target.value ? +e.target.value : null })}>
              <option value="">(없음 — 계획서에 쓰지 않을 문항이면 빼는 편이 낫습니다)</option>
              {claims.map((c) => <option key={c.id} value={c.id}>
                {(c.node_number ? c.node_number + " · " : "") + (c.claim || "(빈 주장)").slice(0, 50)} [{c.basis}]</option>)}
            </select></label>
        </div>)}
      {!q.profile && (
        <div className="sv-q-cross">
          <span className="sv-q-lbl">분석 계획 — 빈도 ×</span>
          {crossable.length === 0 && <span className="hint">견줄 다른 문항이 없습니다.</span>}
          {crossable.map((x) => (
            <button key={x.id} type="button" className={"sv-chip" + ((q.cross_with || []).includes(x.id) ? " on" : "") + (x.profile ? " pf" : "")}
              onClick={() => toggleCross(x.id)} title={x.text}>
              {qnum[x.id]}번 {(x.text || "(빈 문항)").slice(0, 14)}</button>))}
          {dead.length > 0 && <span className="sv-warn">지워진 문항 {dead.length}개를 가리킴
            <button className="mini" onClick={() => save({ cross_with: (q.cross_with || []).filter((x) => qnum[x]) })}>빼기</button></span>}
        </div>)}
      {q.qtype === "단일" && opts.length > 0 && (
        <details className="sv-branch" open={Object.keys(q.branch || {}).length > 0}>
          <summary>분기 — 응답에 따라 건너뛰기{Object.keys(q.branch || {}).length ? ` (${Object.keys(q.branch).length})` : ""}</summary>
          {opts.map((o) => {
            const v = (q.branch || {})[o];
            return (
              <div key={o} className="sv-branch-r">
                <span>{o}</span>→
                <select value={v === undefined ? "" : String(v)} onChange={(e) => setBranch(o, e.target.value)}>
                  <option value="">다음 문항</option>
                  {qs.slice(i + 1).map((x) => <option key={x.id} value={x.id}>{qnum[x.id]}번 {(x.text || "").slice(0, 24)}</option>)}
                  <option value="end">양식 제출(끝)</option>
                  {v !== undefined && v !== "end" && !qs.slice(i + 1).some((x) => x.id === v) &&
                    <option value={String(v)}>{qnum[v] ? `${qnum[v]}번(앞 문항)` : "지워진 문항"}</option>}
                </select>
              </div>);
          })}
        </details>)}
      <div className="sv-q-foot"><button className="btn ghost sm" onClick={() => add(q.id)}>+ 아래에 문항</button></div>
    </div>
  );
}

// ────────────── ④ 폼으로 옮기기 ──────────────
function FormStep({ sid, full, done, setDone, setMsg, reload }) {
  const rows = full.form || [];
  const sections = [];
  rows.forEach((r) => { if (!sections.length || sections[sections.length - 1].no !== r.section) sections.push({ no: r.section, rows: [] }); sections[sections.length - 1].rows.push(r); });
  function download() {
    window.location.href = api.surveyFormXlsxUrl(sid);
    setMsg("폼 옮기기 표(xlsx)를 내려받았습니다 — 문항표 · 폼 설정 점검표 · 근거 지도 · 조사 개요 네 장입니다.");
    setTimeout(reload, 1200);
  }
  const heavy = (full.check || []).filter((o) => o.level === "중요").length;
  return (
    <div className="sv-form">
      <div className="chead"><p className="eyebrow m0">④ 폼으로 옮기기 — 구글폼·네이버폼에 그대로 옮겨 적는 표</p>
        <button className="btn primary sm" disabled={!rows.length} onClick={download}>xlsx 내려받기</button></div>
      <div className="sv-lead">
        폼을 워크벤치가 직접 만들지 않습니다(계정 인증이 필요하고 기관 내부망에서 막히기 쉽습니다). 이 표를 보며 옮겨 적으세요.
        폼의 분기는 <b>섹션 단위</b>로 움직이므로 섹션을 미리 나눠 두었습니다.
        {heavy > 0 && <> <span className="sv-warn">점검에 ‘중요’ {heavy}건이 남아 있습니다 — 수집을 시작하면 고칠 수 없는 것이 있습니다.</span></>}
      </div>
      {rows.length === 0 && <div className="empty">문항이 없습니다.</div>}
      {sections.map((s) => (
        <div key={s.no} className="sv-sec">
          <div className="sv-sec-h">섹션 {s.no}</div>
          {s.rows.map((r) => (
            <div key={r.id} className="sv-frow">
              <div className="sv-frow-h"><b>{r.no}.</b> {r.text || <span className="hint">(빈 문항)</span>}
                {r.required && <span className="sv-req">필수</span>}</div>
              <div className="sv-ftype">{r.form_type}</div>
              {r.options.length > 0 && <ul className="sv-fopts">{r.options.map((o) => <li key={o}>{o}</li>)}{r.other && <li className="hint">기타(직접 입력) 추가</li>}</ul>}
              {r.moves.length > 0 && <div className="sv-fmove">‘답변을 기준으로 섹션으로 이동’ 켜기: {r.moves.join(" · ")}</div>}
            </div>))}
        </div>))}
      {rows.length > 0 && (<>
        <p className="eyebrow mt">폼 설정 점검표 — 폼을 만든 뒤 정할 것</p>
        {(full.checklist || []).map((c) => (
          <label key={c.item} className={"sv-cl" + (done[c.item] ? " on" : "")}>
            <input type="checkbox" checked={!!done[c.item]} onChange={(e) => setDone({ ...done, [c.item]: e.target.checked })} />
            <span><b>{c.item}</b> — {c.note}</span>
          </label>))}
        <div className="hint mt8">이 체크는 저장하지 않습니다(폼은 워크벤치 밖에 있습니다). 내려받은 xlsx 의 점검표에 같은 목록이 있습니다.</div>
      </>)}
    </div>
  );
}
