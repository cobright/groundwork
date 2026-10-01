import React, { useEffect, useState } from "react";
import { api, reportApi } from "./api.js";

// 설정 — 담당자가 파일을 열지 않고 끝낼 수 있어야 하는 것들만 모은다.
//  ① 내 정보(보고전 머리글·진행상황 보고에 쓰인다)
//  ② AI 연결 — 등급(빠름·기본·정밀)마다 회사와 모델, 그리고 회사별 키
//  ③ 자동 백업(돌아갈 자리가 있다는 것을 보여 준다)

// 주소를 쓰는 공급자의 현재 주소를 입력칸으로 옮긴다. 키는 돌려받지 못하지만 주소는 받는다
// (가릴 것이 없고, 눈으로 확인해야 하는 값이다).
function basesFrom(c) {
  const b = {};
  (c.keys || []).filter((k) => k.needs_base).forEach((k) => { b[k.name] = k.base || ""; });
  return b;
}

// 서버가 준 등급 설정을 입력 상태로 옮긴다(회사 "" = 기본과 같게 / 모델 "" = 추천값).
function rowsFrom(c) {
  const r = {};
  (c.tiers || []).forEach((t) => { r[t.tier] = { provider: t.set_provider || "", model: t.set_model || "" }; });
  return r;
}

export default function SettingsModal({ onClose }) {
  const [me, setMe] = useState({ author_name: "", author_dept: "" });
  const [ai, setAi] = useState(null);
  const [rows, setRows] = useState({});      // 등급별 {provider, model} — 저장 전 입력
  const [keys, setKeys] = useState({});      // 새로 입력한 키(빈 칸이면 그대로 둔다)
  const [bases, setBases] = useState({});    // 호환 서버 주소(키와 달리 가려 둘 것이 없어 그대로 보인다)
  const [lists, setLists] = useState({});    // 회사별로 불러온 모델 목록
  const [backups, setBackups] = useState([]);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => { (async () => {
    try {
      const [s, c, b] = await Promise.all([reportApi.getSettings(), api.getAiConfig(), api.listBackups()]);
      setMe({ author_name: s.author_name || "", author_dept: s.author_dept || "" });
      setAi(c); setRows(rowsFrom(c)); setBases(basesFrom(c)); setBackups(b.backups || []);
    } catch (e) { setErr(String(e.message || e)); }
  })(); }, []);

  async function saveMe() {
    setBusy("me"); setErr(""); setMsg("");
    try { const r = await reportApi.putSettings(me); setMe({ author_name: r.author_name, author_dept: r.author_dept }); setMsg("내 정보를 저장했습니다."); }
    catch (e) { setErr(String(e.message || e)); } finally { setBusy(""); }
  }

  function setRow(tier, patch) { setRows((rs) => ({ ...rs, [tier]: { ...rs[tier], ...patch } })); }
  // 회사를 바꾸면 모델 칸을 비운다 — 다른 회사의 모델 이름이 남으면 부를 때 '모델을 찾지 못했습니다'가 된다.
  function pickProvider(tier, provider) { setRow(tier, { provider, model: "" }); }
  function labelOf(name) { return ((ai.providers || []).find((p) => p.name === name) || {}).label || name; }
  function keyOf(name) { return (ai.keys || []).find((k) => k.name === name) || {}; }
  // 이 줄이 실제로 쓸 회사('기본과 같게'면 기본 줄의 회사)
  function effProvider(tier) { return (rows[tier] || {}).provider || (rows.base || {}).provider || ""; }

  async function saveAi() {
    setBusy("ai"); setErr(""); setMsg("");
    const tiers = {};
    ai.tiers.forEach((t) => {
      const cur = rows[t.tier] || {};
      const ent = {};
      if ((cur.provider || "") !== (t.set_provider || "")) ent.provider = cur.provider || "";
      if ((cur.model || "").trim() !== (t.set_model || "")) ent.model = (cur.model || "").trim();
      if (Object.keys(ent).length) tiers[t.tier] = ent;
    });
    const k = {};
    Object.entries(keys).forEach(([name, v]) => { if ((v || "").trim()) k[name] = v.trim(); });   // 빈 칸 = 그대로 둔다
    // 주소는 빈 칸도 뜻이 있다(지우기) — 그래서 '달라졌을 때만' 보낸다.
    const bs = {};
    (ai.keys || []).filter((x) => x.needs_base).forEach((x) => {
      const now = (bases[x.name] || "").trim();
      if (now !== (x.base || "")) bs[x.name] = now;
    });
    try {
      const c = await api.putAiConfig({ tiers, keys: k, bases: bs });
      setAi(c); setRows(rowsFrom(c)); setBases(basesFrom(c)); setKeys({});
      setMsg("저장했습니다. 프로그램을 다시 켜지 않아도 바로 적용됩니다.");
    } catch (e) { setErr(String(e.message || e)); } finally { setBusy(""); }
  }
  async function clearKey(name) {
    if (!confirm("이 회사의 키를 화면 설정에서 지웁니다.\n(.env 에 키가 있으면 그쪽으로 되돌아갑니다)")) return;
    setBusy("ai"); setErr(""); setMsg("");
    try { const c = await api.putAiConfig({ keys: { [name]: "" } }); setAi(c); setMsg("키를 지웠습니다."); }
    catch (e) { setErr(String(e.message || e)); } finally { setBusy(""); }
  }
  async function test(tier) {
    setBusy("test:" + tier); setErr(""); setMsg("");
    const cur = rows[tier] || {};
    try {
      const r = await api.testAi({ tier, provider: cur.provider || "", model: cur.model || "" });
      setMsg(`연결됐습니다. (${r.label} · ${r.model} · ${r.seconds}초 · 응답 “${r.reply}”)`);
    } catch (e) { setErr(String(e.message || e)); } finally { setBusy(""); }
  }
  async function loadList(tier) {
    const prov = effProvider(tier);
    if (!prov) return;
    setBusy("list:" + tier); setErr(""); setMsg("");
    try {
      const r = await api.listAiModels(prov);
      setLists((l) => ({ ...l, [prov]: r.models || [] }));
      setMsg(`${labelOf(prov)} 에서 모델 ${(r.models || []).length}개를 불러왔습니다. 모델 칸을 누르면 고를 수 있습니다.`);
    } catch (e) { setErr(String(e.message || e)); } finally { setBusy(""); }
  }

  return (
    <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal setmodal" role="dialog" aria-label="설정">
        <div className="modal-head">
          <h3>설정</h3>
          <button className="mini" onClick={onClose} title="닫기">✕</button>
        </div>
        <div className="modal-body">
          {err && <div className="rr-err" onClick={() => setErr("")}>{err} <span className="x">✕</span></div>}
          {msg && <div className="reqmsg" onClick={() => setMsg("")}>{msg}</div>}

          <p className="eyebrow m0">내 정보</p>
          <p className="hint">보고전(.docx) 머리글과 진행상황 보고에 들어갑니다.</p>
          <div className="two mb">
            <label className="lbl">부서
              <input value={me.author_dept} placeholder="예: 기획예산실"
                onChange={(e) => setMe({ ...me, author_dept: e.target.value })} />
            </label>
            <label className="lbl">내 이름
              <input value={me.author_name} placeholder="예: 홍길동"
                onChange={(e) => setMe({ ...me, author_name: e.target.value })} />
            </label>
          </div>
          <button className="btn" disabled={busy === "me"} onClick={saveMe}>내 정보 저장</button>

          <p className="eyebrow mt">AI 연결</p>
          {!ai ? <p className="hint">불러오는 중…</p> : (<>
            <p className="hint">
              여기 넣은 값이 <b>바로 적용</b>됩니다(프로그램을 다시 켜지 않아도 됩니다).
              키는 이 PC 의 <span className="mono">workbench.db</span> 에 저장되며 포터블 꾸러미에는 딸려가지 않습니다.
            </p>

            <p className="subhead">등급별 모델</p>
            <p className="hint">일의 무게에 따라 세 등급으로 나눠 씁니다. 등급마다 회사를 달리할 수 있고,
              모델 칸을 비워 두면 <b>추천값</b>을 씁니다.</p>
            {ai.tiers.map((t) => {
              const cur = rows[t.tier] || { provider: "", model: "" };
              const inherit = t.tier !== "base" && !cur.provider;
              const prov = effProvider(t.tier);
              const rec = inherit ? "기본 등급의 모델을 씁니다"
                : (((ai.recommended[prov] || {})[t.tier] || "") || "모델 이름을 적어 주세요 (추천값이 없습니다)");
              const dirty = (cur.provider || "") !== (t.set_provider || "") || (cur.model || "").trim() !== (t.set_model || "");
              return (
                <div key={t.tier} className={"aibox" + (t.tier === "base" ? " on" : "")}>
                  <div className="aihead"><b>{t.label}</b><span className="hint">{t.hint}</span></div>
                  <p className="tiertasks">맡는 일: {t.tasks.join(" · ")}</p>
                  <div className="tiergrid">
                    <label className="lbl">회사
                      <select value={cur.provider} onChange={(e) => pickProvider(t.tier, e.target.value)}>
                        {t.tier !== "base" && <option value="">기본과 같게</option>}
                        {ai.providers.map((p) => <option key={p.name} value={p.name}>{p.label}</option>)}
                      </select>
                    </label>
                    <label className="lbl">모델
                      <input list={"ai-models-" + t.tier} value={inherit ? "" : cur.model} disabled={inherit}
                        placeholder={rec} onChange={(e) => setRow(t.tier, { model: e.target.value })} />
                      <datalist id={"ai-models-" + t.tier}>
                        {(lists[prov] || []).map((m) => <option key={m.id} value={m.id}>{m.label !== m.id ? m.label : null}</option>)}
                      </datalist>
                    </label>
                    <div className="rowbtns">
                      <button className="btn sm" disabled={inherit || !prov || busy === "list:" + t.tier}
                        title="그 회사가 지금 제공하는 모델 목록을 불러옵니다" onClick={() => loadList(t.tier)}>
                        {busy === "list:" + t.tier ? "불러오는 중…" : "목록"}</button>
                      <button className="btn sm" disabled={busy === "test:" + t.tier} onClick={() => test(t.tier)}>
                        {busy === "test:" + t.tier ? "확인 중…" : "시험"}</button>
                    </div>
                  </div>
                  <p className="tiernow">
                    {dirty ? "저장하지 않은 변경이 있습니다."
                      : <>지금 쓰는 것: <b>{labelOf(t.provider)} · {t.model}</b>
                          {" "}({t.inherits ? "기본 등급을 따름" : `회사 ${t.provider_source} · 모델 ${t.model_source}`})</>}
                    {prov && (keyOf(prov).needs_base
                      ? (!keyOf(prov).base && <span className="warn"> — {labelOf(prov)} 주소가 없습니다. 아래에서 넣어 주세요.</span>)
                      : (!keyOf(prov).key_set && <span className="warn"> — {labelOf(prov)} 키가 없습니다. 아래에서 넣어 주세요.</span>))}
                  </p>
                </div>
              );
            })}

            <p className="subhead">API 키</p>
            {ai.keys.map((p) => (
              <div key={p.name} className="aibox">
                <div className="aihead"><b>{p.label}</b>
                  <span className="hint">
                    {p.key_set ? `키 ${p.key_masked} · ${p.key_source}`
                      : (p.key_optional ? "키 없음 (인증이 없는 서버면 그대로 두세요)" : "키가 없습니다")}
                    {p.needs_base && <> · {p.base ? `주소 ${p.base_source}` : "주소가 없습니다"}</>}
                    {p.used_by.length > 0 && <> · 쓰는 등급: {p.used_by.join("·")}</>}</span>
                </div>
                {/* 주소를 쓰는 공급자(호환 서버)는 주소가 먼저다 — 주소 없이는 키도 의미가 없다. */}
                {p.needs_base && (
                  <div className="keyrow">
                    <input className="wide mono" autoComplete="off" placeholder="http://서버주소:포트/v1"
                      value={bases[p.name] || ""} onChange={(e) => setBases({ ...bases, [p.name]: e.target.value })} />
                  </div>
                )}
                <div className="keyrow">
                  <input type="password" autoComplete="off" className="wide"
                    placeholder={p.key_set ? "새 키를 넣을 때만 입력 (비워 두면 그대로)" : `키 붙여넣기 — ${p.where}`}
                    value={keys[p.name] || ""} onChange={(e) => setKeys({ ...keys, [p.name]: e.target.value })} />
                  {p.key_source === "화면" && <button className="btn sm stamp" onClick={() => clearKey(p.name)}>키 지우기</button>}
                </div>
                {p.needs_base && (
                  <p className="hint">행정안전부 AI 공통기반이 지원하는 모델(엑사원·솔라·젬마·라마·GPT-OSS 등)처럼
                    <b> OpenAI 호환 주소</b>를 내주는 서버를 그대로 붙입니다. 모델 이름은 등급 칸의 ‘목록’으로 불러올 수 있습니다.</p>
                )}
              </div>
            ))}
            <button className="btn primary" disabled={busy === "ai"} onClick={saveAi}>AI 설정 저장</button>
            <p className="hint mt2">시험은 실제로 한 번 물어봅니다. 저장하기 전에 고른 회사·모델로도 되고, 키는 저장된 것을 씁니다.
              실패하면 <b>키가 틀린 것인지 망이 막힌 것인지</b>를 그대로 알려 드립니다(방화벽이 막는 경우가 있습니다).</p>

            <p className="subhead">어떤 일에 어떤 등급을 쓰나</p>
            <table className="tasktable"><tbody>
              {ai.tasks.map((x) => <tr key={x.task}><td>{x.label}</td><td>{x.tier_label}</td></tr>)}
            </tbody></table>
            <p className="hint">배정은 프로그램에 정해져 있습니다. 초고·자료 분석 결과에는 실제로 쓴 모델 이름이 함께 찍힙니다.</p>
          </>)}

          <p className="eyebrow mt">자동 백업</p>
          <p className="hint">프로그램을 켤 때 하루 한 번 자료 전체를 복사해 둡니다(최근 7개).
            폴더: <span className="mono">backend/data/backups</span></p>
          {backups.length === 0
            ? <p className="hint">아직 백업이 없습니다. 다음에 프로그램을 켜면 만들어집니다.</p>
            : <ul className="baklist">
                {backups.map((b) => (
                  <li key={b.name}><b>{b.date.slice(0, 4)}-{b.date.slice(4, 6)}-{b.date.slice(6, 8)}</b>
                    <span>{Math.max(1, Math.round(b.size / 1024)).toLocaleString()}KB</span></li>
                ))}
              </ul>}
        </div>
      </div>
    </div>
  );
}
