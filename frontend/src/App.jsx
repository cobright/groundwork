import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, STATUSES } from "./api.js";
import * as M from "./outlineModel.js";
import ResourceRoom from "./ResourceRoom.jsx";
import DraftRoom from "./DraftRoom.jsx";
import ReviewRoom from "./ReviewRoom.jsx";
import FinalRoom from "./FinalRoom.jsx";
import LibraryRoom from "./LibraryRoom.jsx";
import RequestRoom from "./RequestRoom.jsx";
import SurveyRoom from "./SurveyRoom.jsx";
import Dashboard from "./Dashboard.jsx";
import ReportModal from "./ReportModal.jsx";
import InboxRoom from "./InboxRoom.jsx";
import GuidelineRoom from "./GuidelineRoom.jsx";
import SettingsModal from "./SettingsModal.jsx";
import { useColumns } from "./Columns.jsx";

const clone = (o) => structuredClone(o);
// 집필카드 칸: [키, 라벨, 입력형태, 안내문]
// 안내문은 "무엇을 적는 칸인가"를 예시로 보여준다. 이 카드가 그대로 초고 프롬프트의
// 재료가 되므로, 빈칸으로 두면 초고도 그만큼 막연해진다.
// 계열(family)은 표시용 분류가 아니다 — 초고 문체·분량과 '진행 중인 업무에 덮어쓸 수
// 있는가'(crossFamily)를 가른다. 그래서 유형 목록 위에 먼저 편다.
const FAMILIES = [
  { name: "계획서", sub: "여러 쪽",
    note: <>목차를 사람이 짜고 <b>자료를 모아</b> 씁니다. 초고는 문단으로 나옵니다.</> },
  { name: "보고전", sub: "한 쪽",
    note: <>틀을 넣으면 항목마다 <b>무엇을 몇 줄로 써야 하는지</b>가 집필카드에 미리 채워집니다.
      초고는 개조식으로 짧게 나옵니다.</> },
];

const CARD_FIELDS = [
  ["purpose", "작성 목적", "input",
   "이 항목을 왜 쓰는가 — 예: 심사위원에게 사업의 시급성을 납득시킨다"],
  ["question", "핵심 질문", "input",
   "이 항목이 답해야 할 질문 하나 — 예: 왜 지금 이 사업이어야 하는가?"],
  ["message", "핵심 메시지", "textarea",
   "이것만 기억된다면 무엇이어야 하는가 — 한 문장으로 예: 폐교 방치가 안전·인구 문제를 함께 키우고 있다"],
  ["content", "반드시 포함할 내용", "textarea",
   "빠지면 안 되는 것 — 예: 폐교 3개소 위치와 면적, 안전등급 D 판정(2024), 관련 법령"],
];

// 서버는 시각을 UTC 로 적는다(db.now). 화면에는 이 PC 의 시각으로 보여준다.
function when(ts) {
  if (!ts) return "";
  const d = new Date(String(ts).replace(" ", "T") + "Z");
  if (isNaN(d)) return ts;
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function App() {
  const [projects, setProjects] = useState([]);
  const [pid, setPid] = useState(null);
  const [projName, setProjName] = useState("");
  const [projDue, setProjDue] = useState("");
  const [templates, setTemplates] = useState([]);   // 백엔드에서 받는 목차 틀(계획서/보고전)
  const [blocks, setBlocks] = useState([]);
  const [docType, setDocType] = useState("");
  const [outline, setOutline] = useState([]);
  const cols = useColumns("outline", { left: 280, right: 320 }, { left: "목차 생성", right: "집필카드" });
  const [cards, setCards] = useState({});
  const [selId, setSelId] = useState(null);
  const [flag, setFlag] = useState("");
  const [view, setView] = useState("dashboard");
  const [reportOpen, setReportOpen] = useState(false);
  const [glOpen, setGlOpen] = useState(false);   // 공모 가이드라인 패널
  const [snaps, setSnaps] = useState([]);        // 되돌아갈 수 있는 자리(목차 스냅샷)
  const [setOpen, setSetOpen] = useState(false); // 설정(내 정보·AI 연결·백업)
  const [carryProgress, setCarryProgress] = useState(true);  // 보고전에 진행상황을 근거로 넣을지
  const saveTimer = useRef(null);      // 목차 저장 전용
  const nameTimer = useRef(null);      // 업무명 저장 전용(목차 저장을 취소하지 않도록 분리)
  const cardTimers = useRef({});

  useEffect(() => { (async () => {
    try {
      const t = await api.getTemplates();
      setTemplates(t.templates || []); setBlocks(t.blocks || []);
      if (t.templates && t.templates.length) setDocType(t.templates[0].name);
      const list = await api.listProjects(); setProjects(list); if (list.length) await loadProject(list[0].id);
    }
    catch (e) { setFlag("서버 연결 안 됨"); console.error(e); }
  })(); }, []);

  async function refreshList() { const list = await api.listProjects(); setProjects(list); return list; }

  // 보관·삭제로 목록이 바뀌었을 때: 열려 있던 업무가 사라졌으면 남은 첫 업무로 옮겨 탄다.
  async function afterProjectListChanged() {
    const list = await refreshList();
    if (pid && list.some((p) => p.id === pid)) return;
    if (list.length) { await loadProject(list[0].id); }
    else { setPid(null); setProjName(""); setProjDue(""); setOutline([]); setCards({}); setSelId(null); setFlag(""); }
  }
  async function loadProject(id) {
    const d = await api.getOutline(id); setPid(id); setOutline(M.rebuild(d.nodes)); setCards(d.cards || {}); setSelId(null);
    const list = await refreshList(); const p = list.find((x) => x.id === id); setProjName(p ? p.name : ""); setProjDue(p ? (p.due_date || "") : ""); setFlag("저장됨");
    loadSnaps(id);
  }
  // 되돌리기: 목차를 통째로 갈아끼우기 직전 상태가 서버에 자동으로 적힌다.
  async function loadSnaps(id) {
    try { setSnaps(await api.listSnapshots(id || pid)); } catch (e) { console.error(e); }
  }
  async function restoreSnap(sn) {
    const ask = `${when(sn.taken_at)} 상태로 되돌립니다.\n\n${sn.summary}\n\n`
      + "지금의 목차·집필카드·본문은 그 시점 것으로 바뀝니다.\n"
      + "(되돌리기 직전 상태도 함께 적어 두므로 다시 앞으로 올 수 있습니다.)";
    if (!confirm(ask)) return;
    try {
      const r = await api.restoreSnapshot(pid, sn.id);
      await loadProject(pid);
      setFlag("저장됨");
      alert(`되돌렸습니다.\n목차 ${r.nodes} · 집필카드 ${r.cards} · 본문 ${r.drafts}`
        + (r.opinions_restored ? `\n검토의견 ${r.opinions_restored}건을 되살렸습니다.` : "")
        + (r.relinked ? `\n근거·자료요청 ${r.relinked}건의 목차 연결을 다시 이었습니다.` : ""));
    } catch (e) { alert(String(e.message || e)); }
  }
  async function saveSnap() {
    try { await api.takeSnapshot(pid); await loadSnaps(pid); setFlag("저장됨"); }
    catch (e) { alert(String(e.message || e)); }
  }
  async function newProject() {
    const name = prompt("새 업무명", "새 업무"); if (name === null) return;
    const p = await api.createProject({ name: name.trim() || "새 업무", doc_type: docType }); await refreshList(); await loadProject(p.id); setView("outline");
  }
  async function ensureProject() {
    if (pid) return pid;
    const p = await api.createProject({ name: projName.trim() || "새 업무", doc_type: docType });
    setPid(p.id); await refreshList(); return p.id;
  }

  // 저장(디바운스)
  function saveOutlineSoon(next) {
    setFlag("저장 중…"); clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      try { const id = await ensureProject(); await api.putOutline(id, M.flatten(next)); setFlag("저장됨"); loadSnaps(id); }
      catch (e) { setFlag("저장 실패"); console.error(e); }
    }, 400);
  }
  function saveCardSoon(uid, card) {
    setFlag("저장 중…"); clearTimeout(cardTimers.current[uid]);
    cardTimers.current[uid] = setTimeout(async () => {
      try { const id = await ensureProject(); await api.putCard(id, uid, card); setFlag("저장됨"); }
      catch (e) { setFlag("저장 실패"); console.error(e); }
    }, 400);
  }
  function commit(next, newSel) { setOutline(next); if (newSel !== undefined) setSelId(newSel); saveOutlineSoon(next); }

  // 편집 연산
  const op = {
    addSib: () => { const n = clone(outline); const { newId } = M.addSibling(n, selId); commit(n, newId); },
    addChild: () => { const n = clone(outline); const { newId } = M.addChild(n, selId); commit(n, newId); },
    indent: () => { const n = clone(outline); M.indent(n, selId); commit(n); },
    outdent: () => { const n = clone(outline); M.outdent(n, selId); commit(n); },
    up: () => { const n = clone(outline); M.move(n, selId, -1); commit(n); },
    down: () => { const n = clone(outline); M.move(n, selId, 1); commit(n); },
    del: () => {
      const l = M.locate(outline, selId); if (!l) return;
      const ids = M.collectIds(l.node); const wc = ids.filter((id) => cards[id]).length;
      // 서버는 사라진 항목의 집필카드와 '본문'을 함께 지운다(근거·자료요청은 남고 연결만 끊긴다).
      const msg = `‘${l.node.title}’ 및 하위 항목을 삭제합니다.\n`
        + (wc > 0 ? `연결된 집필카드 ${wc}개와 ` : "")
        + `작성된 본문이 함께 삭제됩니다.\n(지우기 직전 상태는 왼쪽 아래 ‘되돌리기’에 남습니다)\n계속할까요?`;
      if (!confirm(msg)) return;
      const n = clone(outline); const { removedIds } = M.removeNode(n, selId);
      const c2 = { ...cards }; removedIds.forEach((id) => delete c2[id]); setCards(c2);
      commit(n, null);
    },
  };
  function rename(id, title) { const n = clone(outline); M.locate(n, id).node.title = title; setOutline(n); saveOutlineSoon(n); }
  // 틀에 딸려온 집필카드를 한꺼번에 저장한다(보고전 틀은 카드가 알맹이다).
  async function saveCardsNow(id, map) {
    for (const [uid, card] of Object.entries(map)) {
      try { await api.putCard(id, uid, card); } catch (e) { console.error(e); }
    }
  }
  // 목차를 통째로 갈아끼우기 전, 사라지는 것을 전부 세어 확인받는다.
  // 목차 틀 심기와 가이드라인 채택이 **같은 문구**를 쓰도록 함수로 뺐다 —
  // 한쪽만 고쳐 확인 문구가 어긋나면 v0.19 의 목차 유실 사고가 되풀이된다.
  async function confirmReplace(what) {
    if (!pid || !outline.length) return true;
    let w = null;
    try { w = await api.replacePreview(pid); } catch (e) { console.error(e); }
    const lost = [];
    if (w) {
      if (w.nodes) lost.push(`· 목차 ${w.nodes}개가 삭제됩니다`);
      if (w.cards) lost.push(`· 집필카드 ${w.cards}개가 삭제됩니다`);
      if (w.bodies) lost.push(`· 작성된 본문 ${w.bodies}개가 삭제됩니다`);
      if (w.opinions) lost.push(`· 검토의견 ${w.opinions}건이 삭제됩니다`);
      if (w.evidence_links) lost.push(`· 근거 ${w.evidence_links}건의 목차 연결이 끊깁니다 (근거 자체는 남습니다)`);
      if (w.request_links) lost.push(`· 자료요청 ${w.request_links}건의 목차 연결이 끊깁니다`);
      if (w.survey_links) lost.push(`· 설문 근거 지도의 주장 ${w.survey_links}건의 목차 연결이 끊깁니다 (주장·문항은 남습니다)`);
    }
    return confirm(`‘${projName}’의 목차를 지우고 ${what} 새로 시작합니다.\n\n`
      + (lost.length ? lost.join("\n") + "\n\n" : "")
      + `바꾸기 직전 상태는 왼쪽 아래 ‘되돌리기’에 적어 둡니다.\n계속할까요?`);
  }

  // 가이드라인 분석 결과(목차 틀과 같은 모양)를 목차로 심는다.
  // 돌려주는 것: 항목 순번 → uid 배열. 필요 자료를 목차에 매다는 데 쓴다.
  // null 을 돌려주면 사용자가 확인 창에서 취소한 것이다.
  async function plantFromGuideline(tree, due) {
    const newCards = {};
    const nodes = M.buildFromTemplate(tree, newCards);
    if (!(await confirmReplace("공모 가이드라인에서 읽은 목차로"))) return null;
    const order = [];
    (function walk(arr) { arr.forEach((n) => { order.push(n.id); walk(n.children); }); })(nodes);
    setOutline(nodes); setCards(newCards); setSelId(null);
    setFlag("저장 중…"); clearTimeout(saveTimer.current);
    const id = await ensureProject();
    await api.putOutline(id, M.flatten(nodes));
    await saveCardsNow(id, newCards);
    const patch = {};
    if (due) patch.due_date = due;
    // 문서 유형이 비어 있을 때만 채운다. 이미 정해 둔 유형을 말없이 바꾸지 않는다
    // (doc_type 은 표시용 라벨이 아니라 초고 문체를 가르는 값이다).
    const curType = (projects.find((x) => x.id === id) || {}).doc_type || "";
    if (!curType) patch.doc_type = "공모사업 계획서";
    if (Object.keys(patch).length) await api.updateProject(id, patch);
    if (due) setProjDue(due);
    if (patch.doc_type) setDocType(patch.doc_type);
    await refreshList();
    setFlag("저장됨");
    loadSnaps(id);
    return order;
  }

  async function generate(mode) {
    const tpl = templates.find((t) => t.name === docType);
    if (!tpl) return;
    const newCards = {};
    const nodes = M.buildFromTemplate(tpl.nodes, newCards);
    let next;
    if (mode === "replace") {
      // 사라지는 것을 전부 세어 보여준다. 카드·본문만 말하고 근거·검토를 빼놓았다가
      // 계획서 업무가 통째로 날아간 사고가 있었다(v0.19). 문구는 confirmReplace 한 곳에서 만든다.
      if (!(await confirmReplace(`‘${docType}’ 틀로`))) return;
      next = nodes; setCards(newCards); setSelId(null);
    } else {
      next = [...clone(outline), ...nodes]; setCards({ ...cards, ...newCards });
    }
    setOutline(next);
    // 목차 틀을 넣으면 이 업무의 문서 유형도 그것이 된다.
    // doc_type 은 표시용 라벨이 아니라 초고 문체를 가르는 값이므로 함께 맞춰야 한다.
    setFlag("저장 중…"); clearTimeout(saveTimer.current);   // 디바운스 저장이 뒤늦게 덮어쓰지 않도록
    try {
      const id = await ensureProject();
      await api.putOutline(id, M.flatten(next));
      await saveCardsNow(id, newCards);
      await api.updateProject(id, { doc_type: docType });
      await refreshList();
      setFlag("저장됨");
    } catch (e) { setFlag("저장 실패"); console.error(e); }
  }
  // 보고전 뽑기: 진행 중인 업무는 손대지 않고 새 업무를 만든다.
  // 보고전은 계획서의 '한 부분'이 아니라 다른 문서다 — 같은 업무의 목차를 갈아끼우면
  // 계획서가 통째로 날아간다(v0.19에 실제로 그 사고가 있었다).
  async function spinoff() {
    if (!pid) return;
    setFlag("만드는 중…");
    try {
      const p = await api.spinoff(pid, { doc_type: docType, carry_progress: carryProgress });
      await refreshList();
      await loadProject(p.id);
      setFlag("저장됨");
      alert(`‘${p.name}’ 업무를 만들었습니다.\n\n`
        + `· 목차 ${p.created_nodes}개가 ‘${docType}’ 틀로 준비됐습니다\n`
        + (p.carried_evidence
            ? `· ‘${p.source_name}’의 확정 근거 ${p.carried_evidence}건을 함께 가져왔습니다\n`
            : `· 가져올 확정 근거가 없어 근거는 비어 있습니다\n`)
        + (p.carried_progress ? `· 진행상황 ${p.carried_progress}건을 [진술] 근거로 담았습니다\n` : "")
        + `\n‘${p.source_name}’은 그대로 있습니다.`);
    } catch (e) { setFlag("실패"); alert(String(e.message || e)); }
  }
  function combine(block, chosen) { const add = M.buildFromTemplate(block.sections.filter((_, i) => chosen.includes(i)), {}); commit([...clone(outline), ...add]); }
  function setCardField(uid, key, value) {
    const c = { ...(cards[uid] || { purpose: "", question: "", message: "", content: "", length: "1쪽", status: "작성 전" }), [key]: value };
    setCards({ ...cards, [uid]: c }); saveCardSoon(uid, c);
  }

  const numbers = useMemo(() => M.numberMap(outline), [outline]);
  const total = useMemo(() => M.countNodes(outline), [outline]);
  const curFamily = useMemo(
    () => (templates.find((t) => t.name === docType) || {}).family || "계획서",
    [templates, docType]);
  const famTemplates = useMemo(() => templates.filter((t) => t.family === curFamily), [templates, curFamily]);
  // 계열 탭은 별도 상태를 두지 않는다 — 고른 유형이 곧 계열이다(둘이 어긋날 자리를 만들지 않는다).
  function pickFamily(fam) {
    if (fam === curFamily) return;
    const first = templates.find((t) => t.family === fam);
    if (first) setDocType(first.name);
  }
  // 지금 업무가 어느 계열인지(저장된 doc_type 기준)와, 고른 틀이 그와 다른지.
  const projType = (projects.find((p) => p.id === pid) || {}).doc_type || "";
  const projFamily = useMemo(() => {
    const t = templates.find((x) => x.name === projType);
    return t ? t.family : (projType.startsWith("보고전") ? "보고전" : "계획서");
  }, [templates, projType]);
  // 계열이 다른 틀을 진행 중인 업무에 덮어쓰면 그 업무가 통째로 날아간다 → 새 업무로 뽑는다.
  const crossFamily = !!pid && outline.length > 0 && !!projType && projFamily !== curFamily;
  const sel = selId ? M.locate(outline, selId) : null;
  const selLoc = sel; const canIndent = sel && sel.index > 0; const canOutdent = sel && sel.parent; const canUp = sel && sel.index > 0; const canDown = sel && sel.index < sel.siblings.length - 1;

  return (
    <div className="app">
      {/* 헤더는 두 줄이다. 섞어 놓으면 어수선해진다.
          윗줄 = 지금 다루는 '업무'가 무엇인가 / 아랫줄 = 어느 '화면'으로 가는가 */}
      <header>
        <div className="hrow work">
          <div className="brand"><span className="logo">기</span><b>행정기획</b> 워크벤치</div>
          <div className="projbar">
            <select value={pid || ""} onChange={(e) => loadProject(+e.target.value)}>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name || "(무제)"}</option>)}
              {!projects.length && <option value="">업무 없음</option>}
            </select>
            <input value={projName} placeholder="업무명" onChange={(e) => {
              const v = e.target.value;
              setProjName(v);
              if (!pid) return;
              setFlag("저장 중…");
              clearTimeout(nameTimer.current);
              nameTimer.current = setTimeout(async () => {
                try { await api.updateProject(pid, { name: v }); await refreshList(); setFlag("저장됨"); }
                catch (err) { setFlag("저장 실패"); console.error(err); }
              }, 500);
            }} />
            <input type="date" className="duein" title="마감일" value={projDue} onChange={async (e) => {
              setProjDue(e.target.value);
              if (pid) { await api.updateProject(pid, { due_date: e.target.value }); refreshList(); }
            }} />
            <span className={"flag" + (flag === "저장됨" ? "" : " on")}>{flag}</span>
          </div>
          <button className="btn" onClick={newProject}>+ 새 업무</button>
          {pid && <button className="btn report-btn" onClick={() => setReportOpen(true)} title="현재 업무의 진행상황을 파일로 내보냅니다">진행상황 보고</button>}
        </div>

        <div className="hrow nav">
          <button className={"btn dashbtn" + (view === "dashboard" ? " on" : "")} onClick={() => setView("dashboard")}>대시보드</button>
          <button className={"btn dashbtn" + (view === "inbox" ? " on" : "")} onClick={() => setView("inbox")}>받은 보고</button>
          <span className="hsep" aria-hidden="true"></span>
          <nav className={"tabs" + (view === "dashboard" || view === "inbox" ? " away" : "")}>
            <button className={"tab" + (view === "outline" ? " on" : "")} onClick={() => setView("outline")}>목차 편집</button>
            <button className={"tab" + (view === "resources" ? " on" : "")} onClick={() => setView("resources")}>자료·근거</button>
            <button className={"tab" + (view === "library" ? " on" : "")} onClick={() => setView("library")}>공통자료실</button>
            <button className={"tab" + (view === "draft" ? " on" : "")} onClick={() => setView("draft")}>초고 작성</button>
            <button className={"tab" + (view === "review" ? " on" : "")} onClick={() => setView("review")}>검토</button>
            <button className={"tab" + (view === "requests" ? " on" : "")} onClick={() => setView("requests")}>자료요청</button>
            <button className={"tab" + (view === "survey" ? " on" : "")} onClick={() => setView("survey")}>설문</button>
            <button className={"tab" + (view === "final" ? " on" : "")} onClick={() => setView("final")}>최종본</button>
          </nav>
          <button className="help setbtn" onClick={() => setSetOpen(true)}
                  title="내 정보 · AI 연결 · 자동 백업">설정</button>
          <a className="help" href="/사용설명서.html" target="_blank" rel="noopener"
             title="사용설명서를 새 창에서 엽니다">사용설명서</a>
        </div>
      </header>

      {setOpen && <SettingsModal onClose={() => setSetOpen(false)} />}

      {glOpen && (
        <div className="gloverlay" role="dialog" aria-label="공모 가이드라인">
          <GuidelineRoom pid={pid} projName={projName} outlineCount={M.countNodes(outline)}
                         onPlant={plantFromGuideline}
                         onClose={() => { setGlOpen(false); setView("outline"); }} />
        </div>
      )}

      {view === "dashboard" ? <Dashboard onOpen={async (id, v) => { await loadProject(id); setView(v || "resources"); }} onChanged={afterProjectListChanged} /> : view === "inbox" ? <InboxRoom /> : view === "resources" ? <ResourceRoom pid={pid} /> : view === "library" ? <LibraryRoom /> : view === "draft" ? <DraftRoom pid={pid} /> : view === "review" ? <ReviewRoom pid={pid} /> : view === "requests" ? <RequestRoom pid={pid} /> : view === "survey" ? <SurveyRoom pid={pid} /> : view === "final" ? <FinalRoom pid={pid} /> : (
      <main ref={cols.ref} className={cols.cls.trim() || undefined} style={cols.style}>
        {cols.handles}
        <section className="col left">
          <p className="eyebrow">문서 유형별 목차 생성</p>
          {/* 계열 먼저, 유형은 그 아래에 전부 편다. 드롭다운은 여덟 개를 다 숨기면서
              정작 갈림(계열)까지 함께 숨겼다 — 되돌릴 수 없는 버튼 바로 위에서는 곤란하다. */}
          <div className="famtabs" role="tablist" aria-label="문서 계열">
            {FAMILIES.map((f) => (
              <button key={f.name} role="tab" aria-selected={curFamily === f.name}
                      className={"famtab" + (curFamily === f.name ? " on" : "")}
                      onClick={() => pickFamily(f.name)}>
                {f.name}<em>{f.sub}</em>
              </button>
            ))}
          </div>
          <div className="tpllist" role="radiogroup" aria-label="작성할 문서 유형">
            {famTemplates.map((t) => {
              const on = t.name === docType;
              return (
                <button key={t.name} role="radio" aria-checked={on}
                        className={"tplcard" + (on ? " on" : "")}
                        onClick={() => setDocType(t.name)}>
                  <span className="tpl-top">
                    <span className="tpl-name">{t.name}</span>
                    <span className="tpl-n">{M.countNodes(t.nodes)}개 항목</span>
                  </span>
                  {/* 고른 틀이 무엇을 넣는지 누르기 전에 보여준다 */}
                  {on && <span className="tpl-peek">{t.nodes.map((n) => n.title).join(" · ")}</span>}
                </button>
              );
            })}
          </div>
          {!crossFamily && <p className="hint">{(FAMILIES.find((f) => f.name === curFamily) || {}).note}</p>}

          {crossFamily ? (
            /* 계열이 다르다 → 지금 업무를 갈아엎지 않고 새 업무로 뽑는다 */
            <div className="spinoffbox">
              <p className="hint mb">
                <b>‘{projName}’</b>은(는) {projType}입니다. 고르신 <b>{docType}</b>은(는) 다른 문서라
                <b> 별도 업무로 만듭니다.</b> 지금 업무의 목차·집필카드·본문·근거는 그대로 둡니다.
              </p>
              {/* 상황 보고의 재료는 대부분 '지금 어디까지 왔는가'다. 그것은 프로그램이 이미
                  세고 있으므로 담당자가 옮겨 적지 않게 근거로 함께 담는다.
                  다만 문서로 확인된 자료가 아니므로 [진술] 표시를 끝까지 달고 간다. */}
              <label className="chk mb">
                <input type="checkbox" checked={carryProgress} onChange={(e) => setCarryProgress(e.target.checked)} />
                <span>진행상황(단계·진행률·마감·미해결 건수)을 <b>[진술] 근거</b>로 함께 담기</span>
              </label>
              <button className="btn primary wide" onClick={spinoff}>‘{docType}’ 새 업무로 뽑기</button>
              <p className="hint mt2">확정된 근거는 새 업무로 함께 넘어갑니다(같은 자료를 가리키므로 원본은 하나입니다).
                진행상황은 프로그램이 센 사실이라 지어낸 것이 없지만, 문서 근거는 아니므로 [진술]로 표시됩니다.</p>
              <details className="danger-more">
                <summary>그래도 이 업무의 목차를 바꾸겠습니다</summary>
                <p className="hint">지금 업무의 목차·집필카드·본문·검토의견이 삭제되고 근거의 목차 연결이 끊깁니다.</p>
                <div className="rowbtns">
                  <button className="btn" onClick={() => generate("replace")}>새로 채우기</button>
                  <button className="btn" onClick={() => generate("append")}>이어붙이기</button>
                </div>
              </details>
            </div>
          ) : (
            <div className="rowbtns">
              <button className="btn primary" onClick={() => generate("replace")}>새로 채우기</button>
              <button className="btn" onClick={() => generate("append")}>이어붙이기</button>
            </div>
          )}
          {/* 되돌리기 — 바로 위 '새로 채우기' 옆에 둔다.
              v0.19에 진행 중이던 계획서의 목차 19개·집필카드 19개를 실제로 잃었다.
              확인 문구를 고쳐 재발은 막았지만 돌아갈 자리가 없었다. 여기가 그 자리다. */}
          {pid && (
            <div className="undobox">
              <div className="undohead">
                <p className="eyebrow m0">되돌리기</p>
                <button className="btn ghost sm" onClick={saveSnap} title="지금 상태를 적어 둡니다">지금 상태 저장</button>
              </div>
              {snaps.length === 0
                ? <p className="hint m0">목차를 통째로 바꾸면 <b>바꾸기 직전 상태</b>가 여기에 자동으로 남습니다.</p>
                : <ul className="snaplist">
                    {snaps.map((sn) => (
                      <li key={sn.id}>
                        <div className="snapmeta"><b>{when(sn.taken_at)}</b><span>{sn.reason}</span></div>
                        <div className="snapsum">{sn.summary}</div>
                        <button className="btn sm" onClick={() => restoreSnap(sn)}>이 시점으로</button>
                      </li>
                    ))}
                  </ul>}
            </div>
          )}

          {/* 세 번째 입구 — 틀을 고르는 대신 공모 가이드라인에서 읽어 온다.
              공모사업은 목차가 이미 공고에 적혀 있다. 우리가 짐작할 일이 아니다. */}
          <div className="glentry">
            <p className="eyebrow m0">공모 가이드라인이 있다면</p>
            <p className="hint">공고·가이드라인 파일(.pdf/.hwpx/.hwp)에서 <b>목차·집필카드·필요한 자료</b>를
              읽어 옵니다. 심사 배점표도 함께 짚어 줍니다.</p>
            <button className="btn wide" disabled={!pid} title={pid ? "" : "먼저 업무를 만들어 주세요"}
                    onClick={() => setGlOpen(true)}>가이드라인에서 만들기</button>
          </div>

          {curFamily !== "보고전" && blocks.length > 0 && <>
            <p className="eyebrow mt">목차안 조합</p>
            <BlockPicker blocks={blocks} onCombine={(bi, chosen) => combine(blocks[bi], chosen)} />
          </>}
        </section>

        {/* 머리(제목·도구 막대)는 고정, 몸(목차)만 스크롤한다. 예전엔 칸 전체가 스크롤 통이라
            항목을 고른 뒤 버튼을 찾으러 위로 올라갔다 내려와야 했다. */}
        <section className="col center pane">
          <div className="pane-head">
            <div className="chead"><p className="eyebrow m0">작업 목차</p><span className="count">{total}개 항목</span></div>
            <div className="toolbar">
              <button className="btn" onClick={op.addSib}>항목 추가</button>
              <button className="btn" disabled={!selId} onClick={op.addChild}>하위 추가</button>
              <span className="tbsep" aria-hidden="true"></span>
              <button className="btn" disabled={!canIndent} onClick={op.indent}>들여쓰기 →</button>
              <button className="btn" disabled={!canOutdent} onClick={op.outdent}>← 내어쓰기</button>
              <button className="btn" disabled={!canUp} onClick={op.up}>위로</button>
              <button className="btn" disabled={!canDown} onClick={op.down}>아래로</button>
              <button className="btn ghost stamp" disabled={!selId} onClick={op.del}>삭제</button>
            </div>
          </div>
          <div className="pane-body">
            {outline.length === 0
              ? <div className="empty">아직 목차가 없습니다. 왼쪽에서 유형을 골라 <b>새로 채우기</b>를 누르거나 구조안을 <b>조합</b>하세요.</div>
              : <ul className="tree">{outline.map((n, i) => <TreeNode key={n.id} node={n} number={String(i + 1)} level={1} selId={selId} cards={cards} onSelect={setSelId} onRename={rename} onEnter={op.addSib} />)}</ul>}
          </div>
        </section>

        <section className="col right">
          <p className="eyebrow">집필카드</p>
          {!selId ? <div className="cnone">목차 항목을 선택하면 집필카드가 표시됩니다.</div> : (
            <>
              <div className="cmeta"><b>{numbers[selId] || ""}</b> {selLoc?.node.title}</div>
              <p className="cguide">여기 적은 것이 <b>그대로 초고의 재료</b>가 됩니다.
                비워 두어도 되지만, 채울수록 초고가 정확해집니다.</p>
              {CARD_FIELDS.map(([key, label, type, hint]) => (
                <div className="cf" key={key}><label>{label}</label>
                  {type === "input"
                    ? <input value={cards[selId]?.[key] || ""} placeholder={hint}
                             onChange={(e) => setCardField(selId, key, e.target.value)} />
                    : <textarea value={cards[selId]?.[key] || ""} placeholder={hint}
                                onChange={(e) => setCardField(selId, key, e.target.value)} />}
                </div>
              ))}
              <div className="two-cf">
                <div className="cf"><label>예상 분량</label>
                  {/* 카드의 '분량' 칸. obj.length 는 배열 길이로 읽히기 쉬워 대괄호로 명시한다. */}
                  <input value={cards[selId]?.["length"] || ""}
                         placeholder={curFamily === "보고전" ? "3~5줄" : "1쪽"}
                         onChange={(e) => setCardField(selId, "length", e.target.value)} />
                </div>
                <div className="cf"><label>작성 상태</label>
                  <select value={cards[selId]?.status || "작성 전"}
                          onChange={(e) => setCardField(selId, "status", e.target.value)}>
                    {STATUSES.map((s) => <option key={s}>{s}</option>)}
                  </select>
                </div>
              </div>
            </>
          )}
          <div className="pnote"><b>연결 보존</b> — 항목을 옮기거나 이름을 바꿔도 집필카드는 그대로 따라갑니다. 카드를 바뀌지 않는 고유번호로 묶어 저장하기 때문입니다.</div>
        </section>
      </main>
      )}
      {reportOpen && pid && <ReportModal pid={pid} onClose={() => setReportOpen(false)} />}
    </div>
  );
}

function TreeNode({ node, number, level, selId, cards, onSelect, onRename, onEnter }) {
  const has = !!cards[node.id];
  return (
    <li className={"lv" + level}>
      <div className={"row" + (node.id === selId ? " sel" : "")} onClick={(e) => { if (e.target.tagName !== "INPUT") onSelect(node.id); }}>
        <span className="num">{number}</span>
        <input className="title" value={node.title} onFocus={() => onSelect(node.id)}
          onChange={(e) => onRename(node.id, e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.target.blur(); onEnter(); } }} />
        <span className={"badge" + (has ? "" : " empty")}>{has ? (cards[node.id].status || "카드") : "카드 없음"}</span>
      </div>
      {node.children.length > 0 && (
        <ul>{node.children.map((c, i) => <TreeNode key={c.id} node={c} number={number + "." + (i + 1)} level={level + 1} selId={selId} cards={cards} onSelect={onSelect} onRename={onRename} onEnter={onEnter} />)}</ul>
      )}
    </li>
  );
}

// 목차안 조합. 세 덩이를 쌓아 두면 아래 것이 화면 밖으로 밀려 비교가 안 됐다 → 탭으로 겹친다.
// 고른 것이 몇 개인지 버튼에 적고, 하나도 없으면 눌리지 않게 한다(경고창을 띄우지 않는다).
function BlockPicker({ blocks, onCombine }) {
  const [bi, setBi] = useState(0);
  const [checked, setChecked] = useState({});   // 키는 "블록번호:항목번호" — 탭을 옮겨도 선택이 섞이지 않는다
  const block = blocks[bi];
  if (!block) return null;
  const key = (i) => bi + ":" + i;
  const chosen = block.sections.map((_, i) => i).filter((i) => checked[key(i)]);
  const allOn = chosen.length === block.sections.length;
  return (
    <div className="blockpick">
      <div className="blocktabs" role="tablist" aria-label="목차안">
        {blocks.map((b, i) => (
          <button key={i} role="tab" aria-selected={i === bi}
                  className={"blocktab" + (i === bi ? " on" : "")}
                  onClick={() => setBi(i)}>{b.name}</button>
        ))}
      </div>
      <div className="blockbody">
        <p className="blockdesc">{block.desc}</p>
        <div className="blockchks">
          {block.sections.map((s, i) => (
            <label key={i} className={"chk" + (checked[key(i)] ? " on" : "")}>
              <input type="checkbox" checked={!!checked[key(i)]}
                     onChange={() => setChecked((c) => ({ ...c, [key(i)]: !c[key(i)] }))} />
              <span>{s.title}</span>
            </label>
          ))}
        </div>
        <div className="rowbtns">
          <button className="btn sm" onClick={() => {
            const next = { ...checked };
            block.sections.forEach((_, i) => { next[key(i)] = !allOn; });
            setChecked(next);
          }}>{allOn ? "전체 해제" : "전체 선택"}</button>
          <button className="btn sm primary" disabled={!chosen.length}
                  onClick={() => { onCombine(bi, chosen); setChecked({}); }}>
            {chosen.length ? `${chosen.length}개 목차에 추가` : "목차에 추가"}
          </button>
        </div>
      </div>
    </div>
  );
}
