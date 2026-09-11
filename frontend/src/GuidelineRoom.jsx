import React, { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import * as M from "./outlineModel.js";

// 공모 가이드라인에서 목차·집필카드·필요 자료를 세우는 화면.
//
// 왜 전면 패널인가:
//   가이드라인은 업무를 시작할 때 한 번 하는 일이다. 탭을 새로 만들면 매일 보는
//   자리에 한 번 쓰는 것이 상주한다. 그래서 목차 화면의 '세 번째 입구'로 들어와
//   덮는 판으로 열고, 끝나면 목차 화면으로 돌아간다.
//
// 왜 단계가 넷인가(원칙 1: AI는 제안하고 사람이 확정한다):
//   ① 올리기 → ② 범위 고르기 → ③ 분석(제안) → ④ 채택.
//   ③에서 나온 것은 전부 제안일 뿐이고, ④에서 사람이 체크한 것만 들어간다.

const DOC_KINDS = ["공고", "수립 가이드라인", "서식"];
const SRC_LABEL = { 표: "빈 표", 각주: "각주", 지시문: "작성 안내" };

export default function GuidelineRoom({ pid, projName, outlineCount, onPlant, onClose }) {
  const [list, setList] = useState([]);
  const [gid, setGid] = useState(null);
  const [kind, setKind] = useState("공고");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  const [blocks, setBlocks] = useState(null);      // 범위 고르기용
  const [range, setRange] = useState({ start: 0, end: 0 });
  const [ana, setAna] = useState(null);            // 분석 결과(제안)
  const [diff, setDiff] = useState(null);          // 정정 공고 비교 결과
  const [step, setStep] = useState("files");       // files | range | result

  // 채택 체크 상태
  const [takeOutline, setTakeOutline] = useState(true);
  const [takeNeeds, setTakeNeeds] = useState({});
  const [takeDue, setTakeDue] = useState("");

  async function reload() {
    if (!pid) return;
    try { setList(await api.listGuidelines(pid)); } catch (e) { setErr(String(e.message || e)); }
  }
  useEffect(() => { reload(); /* eslint-disable-next-line */ }, [pid]);

  async function upload(file) {
    if (!file) return;
    setErr(""); setBusy("파일을 읽는 중…");
    try {
      const g = await api.uploadGuideline(pid, file, kind);
      await reload();
      setGid(g.id);
      setRange({ start: g.range_start, end: g.range_end });
      await openRange(g.id, { start: g.range_start, end: g.range_end });
    } catch (e) { setErr(String(e.message || e)); }
    setBusy("");
  }

  // 정정 공고 비교. 저장된 분석끼리 견주므로 다시 읽지 않고, AI 도 부르지 않는다.
  async function compare() {
    setErr(""); setBusy("이전 분석과 견주는 중…");
    try {
      const d = await api.guidelineCompare(gid);
      setDiff(d);
      if (!d.available) alert(d.reason);
    } catch (e) { setErr(String(e.message || e)); }
    setBusy("");
  }

  // 서식을 양식 보관함으로. 원본은 가이드라인 쪽에도 그대로 남는다(정정 공고 대비).
  async function toForm(g) {
    setErr("");
    try {
      const f = await api.guidelineToForm(g.id);
      alert(`‘${f.name}’을(를) 양식 보관함에 넣었습니다.\n`
        + (f.supported ? "최종본 탭에서 이 양식에 채워 내보낼 수 있습니다."
                       : `다만 이 양식은 채우지 못합니다 — ${f.reason}`));
    } catch (e) { setErr(String(e.message || e)); }
  }

  async function openRange(id, r) {
    setErr(""); setBusy("문서를 훑는 중…");
    try {
      const b = await api.guidelineBlocks(id, 0, 1000);
      setBlocks(b);
      setRange(r || b.range);
      setGid(id); setStep("range"); setAna(null);
      // 이미 분석해 둔 파일이면 그 결과를 그대로 보여준다.
      // 다시 부르면 AI 비용이 또 든다 — 사람이 원할 때만 다시 분석한다.
      const prev = list.find((x) => x.id === id);
      if (prev && prev.analyzed_at) {
        const a = await api.guidelineAnalysis(id);
        if (a && a.analyzed) {
          setAna(a); setStep("result");
          const t = {}; (a.needs || []).forEach((n) => { t[n.ref] = true; });
          setTakeNeeds(t); setTakeOutline(true);
          const due = (a.basic && a.basic.마감일후보) || [];
          setTakeDue(due.length ? due[due.length - 1] : "");
        }
      }
    } catch (e) { setErr(String(e.message || e)); }
    setBusy("");
  }

  async function analyze(useAi) {
    setErr(""); setBusy(useAi ? "AI가 정리하는 중… (문서가 길면 시간이 걸립니다)" : "규칙으로 정리하는 중…");
    try {
      const a = await api.analyzeGuideline(gid, { start: range.start, end: range.end, use_ai: useAi });
      setAna(a); setStep("result");
      const t = {}; (a.needs || []).forEach((n) => { t[n.ref] = true; });
      setTakeNeeds(t);
      setTakeOutline(true);
      const due = (a.basic && a.basic.마감일후보) || [];
      setTakeDue(due.length ? due[due.length - 1] : "");
    } catch (e) { setErr(String(e.message || e)); }
    setBusy("");
  }

  // ── 채택 ─────────────────────────────────────────────
  // 목차는 기존 '목차 틀 심기'와 **같은 경로**로 보낸다(App.jsx 의 onPlant).
  // 그래야 파괴 미리보기·확인 문구·doc_type 맞춤이 그대로 걸린다.
  async function adopt() {
    if (!ana) return;
    setErr(""); setBusy("반영하는 중…");
    try {
      let uidByIndex = null;
      if (takeOutline) {
        uidByIndex = await onPlant(ana.tree, takeDue);   // null 이면 사용자가 취소한 것
        if (!uidByIndex) { setBusy(""); return; }
      }
      const picked = (ana.needs || []).filter((n) => takeNeeds[n.ref]);
      let made = 0;
      if (picked.length) {
        const items = picked.map((n) => ({
          need: n.need, why: n.why, dept_id: n.dept_id ?? null,
          node_uid: uidByIndex ? (uidByIndex[n.node_index] || null) : null,
          ref: n.ref, source: n.source, src_page: n.src_page || 0,
        }));
        const r = await api.adoptGuidelineNeeds(pid, gid, items);
        made = r.created;
      }
      setBusy("");
      alert(
        (takeOutline ? `목차 ${M.countNodes(ana.tree)}개 항목과 집필카드를 넣었습니다.\n` : "") +
        (picked.length ? `필요 자료 ${made}건을 ‘자료요청’ 탭에 담았습니다.` +
          (made < picked.length ? ` (이미 담긴 ${picked.length - made}건은 건너뜀)` : "") : "")
      );
      onClose();
    } catch (e) { setErr(String(e.message || e)); setBusy(""); }
  }

  const needsByNode = useMemo(() => {
    const m = new Map();
    (ana?.needs || []).forEach((n) => {
      if (!m.has(n.node_index)) m.set(n.node_index, []);
      m.get(n.node_index).push(n);
    });
    return m;
  }, [ana]);

  const pickedCount = Object.values(takeNeeds).filter(Boolean).length;

  return (
    <div className="glroom">
      <div className="glhead">
        <div>
          <p className="eyebrow m0">공모 가이드라인에서 시작</p>
          <h2 className="gltitle">{projName || "(업무 없음)"}</h2>
        </div>
        <button className="btn ghost" onClick={onClose}>닫기</button>
      </div>

      {err && <div className="glerr">{err}</div>}
      {busy && <div className="glbusy">{busy}</div>}

      <div className="glsteps">
        {["파일 올리기", "읽을 범위 고르기", "확인하고 반영"].map((s, i) => (
          <span key={s} className={"glstep" + (["files", "range", "result"][i] === step ? " on" : "")}>
            <b>{i + 1}</b>{s}
          </span>
        ))}
      </div>

      {/* ── ① 파일 ───────────────────────────────────── */}
      <section className="glsec">
        <div className="glsec-head">
          <h3>① 가이드라인 파일</h3>
          <span className="hint">공모 한 건에 <b>공고·가이드라인·서식</b>이 함께 옵니다. 여러 개 올려도 됩니다.</span>
        </div>
        <div className="rowbtns">
          <select value={kind} onChange={(e) => setKind(e.target.value)} title="이 파일이 어떤 문서인지">
            {DOC_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <label className="btn primary filebtn">
            파일 고르기 (.pdf / .hwpx / .hwp)
            <input type="file" accept=".pdf,.hwpx,.hwp" hidden
                   onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
          </label>
        </div>
        {list.length === 0
          ? <p className="hint mt2">아직 올린 파일이 없습니다.</p>
          : <ul className="gllist">
              {list.map((g) => (
                <li key={g.id} className={g.id === gid ? "on" : ""}>
                  <div className="glmeta">
                    <b>{g.name}</b>
                    <span className="glchip">{g.doc_kind}</span>
                    <span className="glchip ghost">{g.file_kind}{g.pages ? ` · ${g.pages}쪽` : ""}</span>
                    {g.analyzed_at && <span className="glchip ok">분석함</span>}
                  </div>
                  {g.read_note && <p className="glnote">{g.read_note}</p>}
                  <div className="rowbtns">
                    <button className="btn" onClick={() => openRange(g.id)}>이 파일로 시작</button>
                    {/* 공모에는 제출 서식이 함께 온다. 원본이 이미 여기 있으므로
                        최종본 탭에서 같은 파일을 다시 올리지 않게 버튼 하나로 넘긴다. */}
                    <button className="btn" title="최종본을 이 서식에 채워 내보낼 수 있게 합니다"
                      onClick={() => toForm(g)}>양식 보관함으로</button>
                    <button className="btn ghost stamp" onClick={async () => {
                      if (!confirm(`‘${g.name}’을(를) 지울까요? 이미 심은 목차·자료요청은 남습니다.`)) return;
                      await api.deleteGuideline(g.id); if (gid === g.id) { setGid(null); setStep("files"); }
                      reload();
                    }}>삭제</button>
                  </div>
                </li>
              ))}
            </ul>}
      </section>

      {/* ── ② 범위 ───────────────────────────────────── */}
      {step !== "files" && blocks && (
        <section className="glsec">
          <div className="glsec-head">
            <h3>② 어디부터 어디까지가 목차·작성방법인가</h3>
            <span className="hint">
              자동으로 짚어 둔 곳이 <b>기본값</b>입니다. 눈으로 보고 고쳐 주세요 —
              엉뚱한 데를 읽고도 그럴듯하게 나오는 것이 가장 위험합니다.
            </span>
          </div>
          {blocks.note && <p className="glnote">{blocks.note}</p>}
          <div className="glrange">
            <label>시작 <input type="number" value={range.start} min={0} max={blocks.total - 1}
                              onChange={(e) => setRange({ ...range, start: +e.target.value })} /></label>
            <label>끝 <input type="number" value={range.end} min={0} max={blocks.total - 1}
                            onChange={(e) => setRange({ ...range, end: +e.target.value })} /></label>
            <span className="hint">전체 {blocks.total}줄{blocks.pages ? ` / ${blocks.pages}쪽` : ""}</span>
          </div>
          <div className="glblocks">
            {blocks.blocks.map((b) => {
              const inRange = b.i >= range.start && b.i <= range.end;
              return (
                <div key={b.i} className={"glblk" + (inRange ? " in" : "")}>
                  <button className="glbi" title="여기를 시작으로"
                          onClick={() => setRange({ ...range, start: b.i })}>{b.i}</button>
                  {blocks.pages ? <span className="glpg">p{b.page}</span> : null}
                  <span className={"gltx" + (b.kind === "table" ? " tbl" : "")}>{b.text}</span>
                  <button className="glbe" title="여기를 끝으로"
                          onClick={() => setRange({ ...range, end: b.i })}>끝</button>
                </div>
              );
            })}
          </div>
          <div className="rowbtns mt2">
            <button className="btn primary" disabled={!!busy} onClick={() => analyze(true)}>
              {ana ? "이 범위로 다시 분석 (AI)" : "이 범위를 분석 (AI)"}
            </button>
            <button className="btn" disabled={!!busy} onClick={() => analyze(false)}>
              AI 없이 규칙만으로
            </button>
          </div>
        </section>
      )}

      {/* ── ③ 결과 ───────────────────────────────────── */}
      {step === "result" && ana && (
        <section className="glsec">
          <div className="glsec-head">
            <h3>③ 확인하고 반영</h3>
            <span className="hint">
              전부 <b>제안</b>입니다. 체크한 것만 들어갑니다.
              {ana.fallback && <b className="warn"> · AI 없이 정리했습니다: {ana.reason}</b>}
              {!ana.fallback && ana.model && <> · {ana.model}</>}
            </span>
          </div>

          {/* 정정 공고 비교 — 바뀌는 것은 대개 몇 줄인데, 44쪽을 다시 읽을 수는 없다. */}
          {list.filter((g) => g.analyzed_at && g.id !== gid).length > 0 && (
            <div className="glcard">
              <div className="glsec-head">
                <h4>이전 분석과 견주기</h4>
                <button className="btn sm" disabled={!!busy} onClick={compare}>무엇이 달라졌나</button>
              </div>
              {!diff && <p className="hint m0">정정 공고가 왔다면, 새로 올려 분석한 뒤 이 버튼을 누르세요.
                마감일·배점·목차·필요 자료에서 <b>달라진 것만</b> 짚어 드립니다.</p>}
              {diff && diff.available && (diff.changed === 0
                ? <p className="hint m0">‘{diff.base.name}’과 견주어 <b>달라진 것이 없습니다.</b></p>
                : <>
                    <p className="hint">‘{diff.base.name}’ → ‘{diff.target.name}’ · <b>{diff.changed}가지</b>가 달라졌습니다.</p>
                    <ul className="difflist">
                      {diff.changes.map((c, i) => (
                        <li key={i} className={"d-r" + c.rank}>
                          <span className="dkind">{c.kind}</span>
                          <span className="dval">
                            {c.before && <s>{c.before}</s>}
                            {c.before && c.after ? " → " : ""}
                            {c.after && <b>{c.after}</b>}
                          </span>
                          <span className="dwhat">{c.what}</span>
                        </li>
                      ))}
                    </ul>
                    <p className="hint">여기서 자동으로 고치지는 않습니다 — 이미 심어 둔 목차·자료요청은
                      그대로 두고, 무엇을 손볼지는 담당자가 정합니다.</p>
                  </>)}
            </div>
          )}

          {/* 배점: 짝이 안 맞는 쪽이 더 중요하다 */}
          {ana.scoring?.length > 0 && (
            <div className="glcard">
              <h4>심사 배점 {ana.scoring.length}항목</h4>
              {ana.scoring_match?.missing_in_outline?.length > 0 && (
                <div className="glwarn">
                  <b>대응하는 목차가 없는 심사항목이 있습니다.</b> 빠뜨리면 감점·반려 사유가 됩니다.
                  <ul>{ana.scoring_match.missing_in_outline.map((x, i) => (
                    <li key={i}><b>{x.points_text}</b> {x.label} — {x.detail.slice(0, 90)}</li>))}</ul>
                </div>
              )}
              <table className="gltable">
                <thead><tr><th>배점</th><th>심사항목</th><th>대응 목차</th></tr></thead>
                <tbody>
                  {ana.scoring_match.pairs.map((p, i) => (
                    <tr key={i}><td className="pts">{p.points_text}</td><td>{p.label}</td>
                      <td className="dim">{p.node_title} <em>({p.confidence})</em></td></tr>
                  ))}
                </tbody>
              </table>
              <p className="hint">짝지어진 배점은 그 항목의 집필카드 <b>작성 목적</b>에
                한 줄로 실립니다(‘[심사배점] 이 항목은 …에 대응합니다’). 초고를 만들 때 그대로 전달됩니다.
                유사도로 맞춘 것이라 <b>확신이 낮으면 그렇다고 함께 적습니다</b> — 원문에서 확인하세요.</p>
            </div>
          )}

          {/* 목차 + 항목별 자료 */}
          <div className="glcard">
            <label className="glcheck big">
              <input type="checkbox" checked={takeOutline} onChange={(e) => setTakeOutline(e.target.checked)} />
              <b>목차 {M.countNodes(ana.tree)}개 항목과 집필카드</b>를 넣는다
            </label>
            {takeOutline && outlineCount > 0 && (
              <p className="glwarn sm">이 업무에는 이미 목차 {outlineCount}개가 있습니다.
                넣으면 <b>지금 목차를 지우고</b> 새로 채웁니다 — 다음 화면에서 사라지는 것을 세어 보여드립니다.</p>
            )}
            <Tree tree={ana.tree} needsByNode={needsByNode}
                  takeNeeds={takeNeeds} setTakeNeeds={setTakeNeeds} />
          </div>

          {/* 마감일 */}
          {(ana.basic?.마감일후보 || []).length > 0 && (
            <div className="glcard">
              <h4>접수 마감일</h4>
              <div className="rowbtns">
                <select value={takeDue} onChange={(e) => setTakeDue(e.target.value)}>
                  <option value="">업무 마감일을 바꾸지 않음</option>
                  {ana.basic.마감일후보.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
              <p className="hint">공고에서 찾은 날짜입니다. 접수 기간은 ‘시작 ~ 마감’이라 보통 <b>늦은 쪽</b>이 마감입니다.</p>
            </div>
          )}

          <div className="rowbtns mt2">
            <button className="btn primary wide" disabled={!!busy || (!takeOutline && !pickedCount)}
                    onClick={adopt}>
              {takeOutline ? `목차 ${M.countNodes(ana.tree)}개` : ""}
              {takeOutline && pickedCount ? " + " : ""}
              {pickedCount ? `자료 ${pickedCount}건` : ""} 반영하기
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

// 목차 트리 + 각 항목에 딸린 필요 자료. 자료마다 **어디서 나온 것인지**를 붙인다 —
// "AI가 지어낸 것 아닌가"를 담당자가 원문에서 확인할 수 있어야 한다(원칙 2).
function Tree({ tree, needsByNode, takeNeeds, setTakeNeeds, idx = { n: 0 }, level = 1 }) {
  return (
    <ul className={"gltree l" + level}>
      {tree.map((node) => {
        const i = idx.n++;
        const needs = needsByNode.get(i) || [];
        return (
          <li key={i}>
            <div className="glnode">
              <span className="gltitle">{node.title}</span>
              {node.card?.length && <span className="glchip ghost">{node.card.length}</span>}
            </div>
            {node.card?.question && <p className="glq">핵심 질문 · {node.card.question}</p>}
            {node.card?.content && <p className="glc">{node.card.content.slice(0, 220)}</p>}
            {needs.length > 0 && (
              <ul className="glneeds">
                {needs.map((n) => (
                  <li key={n.ref}>
                    <label className="glcheck">
                      <input type="checkbox" checked={!!takeNeeds[n.ref]}
                             onChange={(e) => setTakeNeeds((t) => ({ ...t, [n.ref]: e.target.checked }))} />
                      <span className="glneed">{n.need}</span>
                    </label>
                    <div className="glsrc">
                      <span className="glchip src">{SRC_LABEL[n.source] || n.source}
                        {n.src_page ? ` · ${n.src_page}쪽` : ""}</span>
                      {n.dept
                        ? <span className="glchip dept" title={n.dept_why}>{n.dept}</span>
                        : <span className="glchip ghost">부서 미정</span>}
                      {n.src_text && <span className="glquote" title={n.src_text}>“{n.src_text.slice(0, 60)}”</span>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {node.children?.length > 0 && (
              <Tree tree={node.children} needsByNode={needsByNode}
                    takeNeeds={takeNeeds} setTakeNeeds={setTakeNeeds} idx={idx} level={level + 1} />
            )}
          </li>
        );
      })}
    </ul>
  );
}
