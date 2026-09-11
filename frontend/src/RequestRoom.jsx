import React, { useEffect, useState } from "react";
import { api, REQUEST_STATUS } from "./api.js";
import { flatNumbers } from "./outlineModel.js";

const STATUS_CLASS = { "필요": "st-need", "요청함": "st-sent", "회신옴": "st-back", "반영": "st-done", "보류": "st-hold" };
const ORIGIN_LABEL = { draft: "초고", review: "검토", user: "직접" };

export default function RequestRoom({ pid }) {
  const [items, setItems] = useState([]);
  const [depts, setDepts] = useState([]);
  const [nodes, setNodes] = useState([]);
  const [numbers, setNumbers] = useState({});
  const [filter, setFilter] = useState("전체");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);   // 회신 파일 읽기(자동 수집과 다른 일)
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [add, setAdd] = useState({ need: "", node_uid: "", dept_id: "" });
  const [recvOpen, setRecvOpen] = useState(null);

  useEffect(() => { if (pid) reload(); }, [pid]);
  useEffect(() => { api.listDepartments().then(setDepts).catch(() => {}); }, []);
  async function reload() {
    try {
      const [rs, ol] = await Promise.all([api.listRequests(pid), api.getOutline(pid)]);
      setItems(rs); const ns = ol.nodes || []; setNodes(ns); setNumbers(flatNumbers(ns));
    } catch (e) { setErr(String(e.message || e)); }
  }
  async function collect() {
    setBusy(true); setErr(""); setMsg("");
    try { const r = await api.collectRequests(pid); await reload(); setMsg(r.collected === 0 ? "새로 수집된 항목이 없습니다(이미 모두 수집됨)." : `${r.collected}건을 새로 수집했습니다.`); }
    catch (e) { setErr(String(e.message || e)); } finally { setBusy(false); }
  }
  async function patch(it, p) {
    setItems((v) => v.map((x) => (x.id === it.id ? { ...x, ...p } : x)));
    try { await api.updateRequest(pid, it.id, p); await reload(); } catch (e) { setErr(String(e.message || e)); }
  }
  async function addItem() {
    if (!add.need.trim()) { alert("필요한 자료 내용을 입력하세요."); return; }
    try {
      await api.addRequest(pid, { need: add.need.trim(), node_uid: add.node_uid || null, dept_id: add.dept_id ? +add.dept_id : null });
      setAdd({ need: "", node_uid: "", dept_id: "" }); await reload();
    } catch (e) { setErr(String(e.message || e)); }
  }
  async function del(id) { if (!confirm("이 요청 항목을 삭제할까요?")) return; try { await api.deleteRequest(pid, id); await reload(); } catch (e) { setErr(String(e.message || e)); } }
  async function registerResource(it) {
    if (!confirm("회신받은 내용을 이 업무의 자료로 등록할까요?\n(요청 내용이 자료명, 회신 메모가 본문이 됩니다. 이후 자료·근거에서 분석·연결하세요.)")) return;
    try { await api.registerRequestResource(pid, it.id); await reload(); setMsg("회신자료를 업무 자료로 등록했습니다. ‘자료·근거’ 탭에서 분석·근거 연결을 이어가세요."); }
    catch (e) { setErr(String(e.message || e)); }
  }
  // 담당자 메모는 '자료'에 붙는다. 여기서 적어도 자료·근거 화면의 그 칸과 같은 칸이다.
  async function saveMemo(it, note) {
    setItems((v) => v.map((x) => (x.id === it.id ? { ...x, received_memo: note } : x)));
    try { await api.setResourceNote(pid, it.received_resource_id, note); }
    catch (e) { setErr(String(e.message || e)); await reload(); }
  }
  // 부서 회신은 대개 파일로 온다. 담당자가 열어 요약해 붙여넣지 않아도 되게 그대로 올린다.
  async function uploadReceived(it, file) {
    setUploading(true); setErr(""); setMsg("");
    try {
      const r = await api.uploadReceivedFile(pid, it.id, file);
      await reload();     // 상자는 열어 둔다 — 회신에 대해 남길 말을 여기서 적는다
      setMsg(`‘${file.name}’ 을(를) 읽어 회신자료로 등록했습니다(${r.file_kind}, 본문 ${(r.chars || 0).toLocaleString()}자).`
        + (r.read_note ? ` ${r.read_note}` : "")
        + " ‘자료·근거’ 탭에서 AI 분석을 누르면, 요청한 내용이 이 자료에 들어 있는지까지 짚어 줍니다.");
    } catch (e) { setErr(String(e.message || e)); } finally { setUploading(false); }
  }

  if (!pid) return <div className="rr-empty">먼저 상단에서 업무를 선택하세요.</div>;

  const filtered = items.filter((it) => filter === "전체" || (filter === "미배정" ? !it.dept_id : it.dept_name === filter));
  const deptNames = [...new Set(items.map((it) => it.dept_name).filter(Boolean))];
  const counts = REQUEST_STATUS.map((s) => [s, items.filter((it) => it.status === s).length]);
  const overdue = items.filter((it) => it.overdue).length;

  return (
    <div className="rr reqroom">
      {err && <div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}

      <div className="reqbar">
        <button className="btn primary" disabled={busy} onClick={collect}>{busy ? "수집 중…" : "자동 수집"}</button>
        <span className="hint">초고의 [확인 필요]와 검토의견의 필요조치를 모읍니다.</span>
        <div className="spacer" />
        <button className="btn" onClick={() => (window.location.href = api.requestsXlsxUrl(pid))}>xlsx 내보내기(부서별)</button>
      </div>
      {msg && <div className="reqmsg" onClick={() => setMsg("")}>{msg}</div>}

      <div className="reqsummary">
        {counts.map(([s, n]) => <span key={s} className={"stcount " + STATUS_CLASS[s]}>{s} {n}</span>)}
        {overdue > 0 && <span className="stcount st-over">마감 초과 {overdue}</span>}
        <div className="spacer" />
        <label className="hint">부서 필터&nbsp;
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option>전체</option><option>미배정</option>
            {deptNames.map((d) => <option key={d}>{d}</option>)}
          </select>
        </label>
      </div>

      <div className="reqadd">
        <input placeholder="필요한 자료(직접 추가)" value={add.need} onChange={(e) => setAdd({ ...add, need: e.target.value })} onKeyDown={(e) => e.key === "Enter" && addItem()} />
        <select value={add.node_uid} onChange={(e) => setAdd({ ...add, node_uid: e.target.value })}>
          <option value="">관련 목차(선택)</option>
          {nodes.map((n) => <option key={n.uid} value={n.uid}>{numbers[n.uid]} {n.title}</option>)}
        </select>
        <select value={add.dept_id} onChange={(e) => setAdd({ ...add, dept_id: e.target.value })}>
          <option value="">대상 부서(선택)</option>
          {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <button className="btn primary" onClick={addItem}>추가</button>
      </div>

      <div className="reqlist">
        {filtered.length === 0 && <div className="hint" style={{ padding: "12px" }}>표시할 항목이 없습니다. ‘자동 수집’을 누르거나 위에서 직접 추가하세요.</div>}
        {filtered.map((it) => (
          <div className={"reqcard" + (it.overdue ? " overdue" : "")} key={it.id}>
            <div className="rc-main">
              <div className="rc-need">{it.need}
                <span className={"obadge o-" + it.origin}>{ORIGIN_LABEL[it.origin]}</span>
                {it.node_number && <span className="rc-node">{it.node_number} {it.node_title}</span>}
              </div>
              <button className="mini" title="삭제" onClick={() => del(it.id)}>✕</button>
            </div>
            <div className="rc-ctrl">
              <label>부서
                <select value={it.dept_id || ""} onChange={(e) => (e.target.value ? patch(it, { dept_id: +e.target.value }) : patch(it, { clear_dept: true }))}>
                  <option value="">미배정</option>
                  {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </label>
              <label>상태
                <select className={STATUS_CLASS[it.status]} value={it.status} onChange={(e) => patch(it, { status: e.target.value })}>
                  {REQUEST_STATUS.map((s) => <option key={s}>{s}</option>)}
                </select>
              </label>
              <label>요청일
                <input type="date" value={it.requested_at || ""} onChange={(e) => patch(it, { requested_at: e.target.value })} />
              </label>
              <label className={it.overdue ? "due-over" : ""}>마감일
                <input type="date" value={it.due_date || ""} onChange={(e) => patch(it, { due_date: e.target.value })} />
              </label>
            </div>
            <div className="rc-foot">
              <input className="rc-note" placeholder="비고" defaultValue={it.note || ""} onBlur={(e) => e.target.value !== (it.note || "") && patch(it, { note: e.target.value })} />
              {it.received_resource_id
                ? <><span className="recvdone">회신자료 등록됨: <b>{it.received_resource_name}</b>
                    {it.received_filename && <> — <a href={api.resourceFileUrl(pid, it.received_resource_id)}>{it.received_filename}</a></>}</span>
                    <button className="btn ghost sm" onClick={() => setRecvOpen(recvOpen === it.id ? null : it.id)}>
                      {recvOpen === it.id ? "메모 닫기" : "담당자 메모"}</button></>
                : <>{it.received_lost && <span className="warn">등록했던 회신자료를 지우셨습니다. 다시 등록할 수 있습니다.</span>}
                    <button className="btn ghost sm" onClick={() => setRecvOpen(recvOpen === it.id ? null : it.id)}>회신 등록</button></>}
            </div>
            {/* 등록 전에는 '회신받은 내용'을 받는 입구, 등록 뒤에는 그 자료의 담당자 메모를 연다.
                메모 칸을 여기 따로 만들지 않는 이유: 같은 뜻의 자리가 둘이 되면 어느 쪽에 적었는지
                알 수 없게 된다(이 앱은 이미 '비고'가 요청 항목에 하나 있다). 칸은 하나, 문만 둘이다. */}
            {recvOpen === it.id && (
              <div className="recvbox">
                {it.received_resource_id ? (<>
                  <div className="recvor">담당자 메모 — ‘자료·근거’ 탭의 그 칸과 <b>같은 칸</b>입니다</div>
                  <textarea placeholder="이 자료를 어떻게 볼 것인지 적어 두세요. (예: 2023년치는 잠정이라고 함 / 나머지는 다음 주 회신 예정)"
                    defaultValue={it.received_memo || ""}
                    onBlur={(e) => e.target.value !== (it.received_memo || "") && saveMemo(it, e.target.value)} />
                  <div className="recvbar">
                    <span className="hint">칸 밖을 누르면 저장됩니다. 메모는 AI 분석에 넘어가지 않고 최종본에도 나가지 않습니다.</span>
                  </div>
                </>) : (<>
                  <div className="recvfile">
                    <div>
                      <b>부서가 보낸 파일을 그대로 올리세요.</b>
                      <span className="hint">한글(.hwpx/.hwp) · 엑셀(.xlsx/.xls) · 워드(.docx) · PDF. 표와 연도별 수치를 칸 그대로 읽어 담고, 원본 파일도 함께 보관합니다.</span>
                    </div>
                    <label className={"btn primary sm filebtn" + (uploading ? " disabled" : "")}>
                      {uploading ? "읽는 중…" : "회신 파일 올리기"}
                      <input type="file" accept=".hwpx,.hwp,.xlsx,.xlsm,.xls,.docx,.pdf" disabled={uploading}
                        onChange={(e) => { const f = e.target.files[0]; e.target.value = ""; if (f) uploadReceived(it, f); }} />
                    </label>
                  </div>
                  <div className="recvor">또는, 짧은 회신이라면 직접 적기</div>
                  <textarea placeholder="회신받은 내용을 붙여넣거나 요약해 적으세요."
                    defaultValue={it.received_note || ""}
                    onBlur={(e) => e.target.value !== (it.received_note || "") && patch(it, { received_note: e.target.value })} />
                  <div className="recvbar">
                    <button className="btn ghost sm" onClick={() => registerResource(it)}>적은 내용을 업무 자료로 등록</button>
                    <span className="hint">등록하면 자료·근거에서 분석·근거 연결로 이어집니다.</span>
                  </div>
                </>)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
