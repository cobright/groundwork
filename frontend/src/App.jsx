import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, TEMPLATES, BLOCKS, STATUSES } from "./api.js";
import * as M from "./outlineModel.js";
import ResourceRoom from "./ResourceRoom.jsx";
import DraftRoom from "./DraftRoom.jsx";
import ReviewRoom from "./ReviewRoom.jsx";
import FinalRoom from "./FinalRoom.jsx";
import LibraryRoom from "./LibraryRoom.jsx";
import RequestRoom from "./RequestRoom.jsx";
import Dashboard from "./Dashboard.jsx";
import ReportModal from "./ReportModal.jsx";
import InboxRoom from "./InboxRoom.jsx";

const clone = (o) => structuredClone(o);
const CARD_FIELDS = [["purpose", "작성 목적", "input"], ["question", "핵심 질문", "input"], ["message", "핵심 메시지", "textarea"], ["content", "반드시 포함할 내용", "textarea"]];

export default function App() {
  const [projects, setProjects] = useState([]);
  const [pid, setPid] = useState(null);
  const [projName, setProjName] = useState("");
  const [projDue, setProjDue] = useState("");
  const [docType, setDocType] = useState(Object.keys(TEMPLATES)[0]);
  const [outline, setOutline] = useState([]);
  const [cards, setCards] = useState({});
  const [selId, setSelId] = useState(null);
  const [flag, setFlag] = useState("");
  const [view, setView] = useState("dashboard");
  const [reportOpen, setReportOpen] = useState(false);
  const saveTimer = useRef(null);
  const cardTimers = useRef({});

  useEffect(() => { (async () => {
    try { const list = await api.listProjects(); setProjects(list); if (list.length) await loadProject(list[0].id); }
    catch (e) { setFlag("서버 연결 안 됨"); console.error(e); }
  })(); }, []);

  async function refreshList() { const list = await api.listProjects(); setProjects(list); return list; }
  async function loadProject(id) {
    const d = await api.getOutline(id); setPid(id); setOutline(M.rebuild(d.nodes)); setCards(d.cards || {}); setSelId(null);
    const list = await refreshList(); const p = list.find((x) => x.id === id); setProjName(p ? p.name : ""); setProjDue(p ? (p.due_date || "") : ""); setFlag("저장됨");
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
      try { const id = await ensureProject(); await api.putOutline(id, M.flatten(next)); setFlag("저장됨"); }
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
      const msg = wc > 0 ? `‘${l.node.title}’ 및 하위 항목을 삭제합니다. 연결된 집필카드 ${wc}개도 삭제됩니다. 계속할까요?` : `‘${l.node.title}’ 및 하위 항목을 삭제할까요?`;
      if (!confirm(msg)) return;
      const n = clone(outline); const { removedIds } = M.removeNode(n, selId);
      const c2 = { ...cards }; removedIds.forEach((id) => delete c2[id]); setCards(c2);
      commit(n, null);
    },
  };
  function rename(id, title) { const n = clone(outline); M.locate(n, id).node.title = title; setOutline(n); saveOutlineSoon(n); }
  function generate(mode) {
    const nodes = M.buildNodes(TEMPLATES[docType]);
    if (mode === "replace") {
      const orphan = Object.keys(cards).length;
      if (outline.length && !confirm(orphan > 0 ? `현재 목차를 지우고 새로 시작합니다. 집필카드 ${orphan}개가 사라집니다. 계속할까요?` : "현재 목차를 지우고 새로 시작할까요?")) return;
      setCards({}); setSelId(null); commit(nodes, null);
    } else { const n = [...clone(outline), ...nodes]; commit(n); }
  }
  function combine(block, chosen) { const add = M.buildNodes(block.sections.filter((_, i) => chosen.includes(i))); commit([...clone(outline), ...add]); }
  function setCardField(uid, key, value) {
    const c = { ...(cards[uid] || { purpose: "", question: "", message: "", content: "", length: "1쪽", status: "작성 전" }), [key]: value };
    setCards({ ...cards, [uid]: c }); saveCardSoon(uid, c);
  }

  const numbers = useMemo(() => M.numberMap(outline), [outline]);
  const total = useMemo(() => M.countNodes(outline), [outline]);
  const sel = selId ? M.locate(outline, selId) : null;
  const selLoc = sel; const canIndent = sel && sel.index > 0; const canOutdent = sel && sel.parent; const canUp = sel && sel.index > 0; const canDown = sel && sel.index < sel.siblings.length - 1;

  return (
    <div className="app">
      <header>
        <div className="brand"><span className="logo">기</span><b>행정기획</b> 워크벤치</div>
        <button className={"btn dashbtn" + (view === "dashboard" ? " on" : "")} onClick={() => setView("dashboard")}>대시보드</button>
        <button className={"btn dashbtn" + (view === "inbox" ? " on" : "")} onClick={() => setView("inbox")}>받은 보고</button>
        <div className="projbar">
          <select value={pid || ""} onChange={(e) => loadProject(+e.target.value)}>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name || "(무제)"}</option>)}
            {!projects.length && <option value="">업무 없음</option>}
          </select>
          <input value={projName} placeholder="업무명" onChange={(e) => {
            setProjName(e.target.value);
            clearTimeout(saveTimer.current);
            saveTimer.current = setTimeout(async () => { if (pid) { await api.updateProject(pid, { name: e.target.value }); refreshList(); } }, 500);
          }} />
          <input type="date" className="duein" title="마감일" value={projDue} onChange={async (e) => {
            setProjDue(e.target.value);
            if (pid) { await api.updateProject(pid, { due_date: e.target.value }); refreshList(); }
          }} />
          <span className={"flag" + (flag === "저장됨" ? "" : " on")}>{flag}</span>
        </div>
        <nav className="tabs">
          <button className={"tab" + (view === "outline" ? " on" : "")} onClick={() => setView("outline")}>목차 편집</button>
          <button className={"tab" + (view === "resources" ? " on" : "")} onClick={() => setView("resources")}>자료·근거</button>
          <button className={"tab" + (view === "library" ? " on" : "")} onClick={() => setView("library")}>공통자료실</button>
          <button className={"tab" + (view === "draft" ? " on" : "")} onClick={() => setView("draft")}>초고 작성</button>
          <button className={"tab" + (view === "review" ? " on" : "")} onClick={() => setView("review")}>검토</button>
          <button className={"tab" + (view === "requests" ? " on" : "")} onClick={() => setView("requests")}>자료요청</button>
          <button className={"tab" + (view === "final" ? " on" : "")} onClick={() => setView("final")}>최종본</button>
        </nav>
        <button className="btn" onClick={newProject}>+ 새 업무</button>
        {pid && <button className="btn report-btn" onClick={() => setReportOpen(true)} title="현재 업무의 진행상황을 파일로 내보냅니다">진행상황 보고</button>}
      </header>

      {view === "dashboard" ? <Dashboard onOpen={async (id) => { await loadProject(id); setView("resources"); }} /> : view === "inbox" ? <InboxRoom /> : view === "resources" ? <ResourceRoom pid={pid} /> : view === "library" ? <LibraryRoom /> : view === "draft" ? <DraftRoom pid={pid} /> : view === "review" ? <ReviewRoom pid={pid} /> : view === "requests" ? <RequestRoom pid={pid} /> : view === "final" ? <FinalRoom pid={pid} /> : (
      <main>
        <section className="col left">
          <p className="eyebrow">문서 유형별 목차 생성</p>
          <label className="lbl">작성할 문서 유형</label>
          <select className="wide" value={docType} onChange={(e) => setDocType(e.target.value)}>
            {Object.keys(TEMPLATES).map((t) => <option key={t}>{t}</option>)}
          </select>
          <div className="rowbtns">
            <button className="btn primary" onClick={() => generate("replace")}>새로 채우기</button>
            <button className="btn" onClick={() => generate("append")}>이어붙이기</button>
          </div>
          <p className="eyebrow mt">목차안 조합</p>
          {BLOCKS.map((b, bi) => <BlockCard key={bi} block={b} onCombine={(chosen) => combine(b, chosen)} />)}
        </section>

        <section className="col center">
          <div className="chead"><p className="eyebrow m0">작업 목차</p><span className="count">{total}개 항목</span></div>
          <div className="toolbar">
            <button className="btn" onClick={op.addSib}>항목 추가</button>
            <button className="btn" disabled={!selId} onClick={op.addChild}>하위 추가</button>
            <button className="btn" disabled={!canIndent} onClick={op.indent}>들여쓰기 →</button>
            <button className="btn" disabled={!canOutdent} onClick={op.outdent}>← 내어쓰기</button>
            <button className="btn" disabled={!canUp} onClick={op.up}>위로</button>
            <button className="btn" disabled={!canDown} onClick={op.down}>아래로</button>
            <button className="btn ghost stamp" disabled={!selId} onClick={op.del}>삭제</button>
          </div>
          {outline.length === 0
            ? <div className="empty">아직 목차가 없습니다. 왼쪽에서 유형을 골라 <b>새로 채우기</b>를 누르거나 구조안을 <b>조합</b>하세요.</div>
            : <ul className="tree">{outline.map((n, i) => <TreeNode key={n.id} node={n} number={String(i + 1)} level={1} selId={selId} cards={cards} onSelect={setSelId} onRename={rename} onEnter={op.addSib} />)}</ul>}
        </section>

        <section className="col right">
          <p className="eyebrow">집필카드</p>
          {!selId ? <div className="cnone">목차 항목을 선택하면 집필카드가 표시됩니다.</div> : (
            <>
              <div className="cmeta"><b>{numbers[selId] || ""}</b> {selLoc?.node.title}</div>
              {CARD_FIELDS.map(([key, label, type]) => (
                <div className="cf" key={key}><label>{label}</label>
                  {type === "input"
                    ? <input value={cards[selId]?.[key] || ""} onChange={(e) => setCardField(selId, key, e.target.value)} />
                    : <textarea value={cards[selId]?.[key] || ""} onChange={(e) => setCardField(selId, key, e.target.value)} />}
                </div>
              ))}
              <div className="cf"><label>예상 분량 · 작성 상태</label>
                <div className="rowbtns">
                  <input value={cards[selId]?.length || ""} placeholder="1쪽" onChange={(e) => setCardField(selId, "length", e.target.value)} />
                  <select value={cards[selId]?.status || "작성 전"} onChange={(e) => setCardField(selId, "status", e.target.value)}>
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

function BlockCard({ block, onCombine }) {
  const [checked, setChecked] = useState({});
  const toggle = (i) => setChecked((c) => ({ ...c, [i]: !c[i] }));
  return (
    <div className="block">
      <h4>{block.name}</h4><p>{block.desc}</p>
      {block.sections.map(([title], i) => (
        <label key={i} className="chk"><input type="checkbox" checked={!!checked[i]} onChange={() => toggle(i)} /> {title}</label>
      ))}
      <button className="combine" onClick={() => {
        const chosen = Object.keys(checked).filter((k) => checked[k]).map(Number);
        if (!chosen.length) { alert("추가할 항목을 하나 이상 선택하세요."); return; }
        onCombine(chosen); setChecked({});
      }}>선택 항목을 목차에 조합</button>
    </div>
  );
}
