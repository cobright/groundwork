import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

// 세 칸 화면(목차 편집·자료·근거·공통자료실·초고 작성·검토·최종본)의 칸 폭 조절.
//
// 왜 필요했나: 칸 폭이 CSS 에 박혀 있었다(280·가변·320 / 300·가변·340). 넓은 모니터에서도
//   초고 본문은 가운데에 갇히고, 근거표·검토의견처럼 긴 목록은 좁은 옆 칸에서 줄이 접혔다.
//
// 어떻게 동작하나:
//   · 칸 경계를 끌면 폭이 바뀐다. 화면마다 따로, 이 PC 의 브라우저에 기억한다(사람마다 모니터가 다르다).
//   · 경계를 두 번 누르면 처음 폭. 키보드: 경계에 초점 → ←/→ 로 조금씩, Enter 로 처음 폭.
//   · 경계에 마우스를 올리면 나오는 ◂/▸ 로 옆 칸을 접는다. 접힌 칸은 이름이 적힌 띠로 남는다.
//     **접은 상태는 기억하지 않는다** — 다음에 이 화면에 왔을 때 칸이 사라져 있으면 없어진 줄 안다.
//     숨겨 둔 것은 '통제되고 있다는 느낌'의 반대다(CLAUDE.md 원칙 5).
//   · 가운데 칸은 CENTER_MIN 아래로 줄지 않는다. 창을 줄여도 styles.css 의 minmax 가 같은 선을 지킨다.
//
// 칸을 새로 만들지 않는다: 각 화면의 <section className="col left|center|right"> 는 그대로 두고,
// 감싸는 요소에 ref·style·cls 를 붙이고 손잡이(handles)만 끼운다. 손잡이는 절대 위치라
// 그리드 칸 배치(오류 줄 .rr-err 의 1/-1, 최종본 미리보기의 2/-1)를 건드리지 않는다.
// 폭은 CSS 변수로만 건넨다 — 인라인 grid-template-columns 는 좁은 화면(세로 쌓기) 규칙을 이겨 버린다.

const LIMITS = { left: [200, 560], right: [240, 640] };   // styles.css 의 minmax 최소값과 같아야 한다
const CENTER_MIN = 360;                                   // styles.css 의 minmax(360px,1fr) 와 같아야 한다
const STEP = 16;
const KEY = "wb.cols.";

function readSaved(screen) {
  try { return JSON.parse(localStorage.getItem(KEY + screen) || "{}") || {}; } catch { return {}; }
}
function writeSaved(screen, w, defaults) {
  const diff = {};
  for (const s of ["left", "right"]) if (w[s] !== defaults[s]) diff[s] = w[s];
  try {
    if (Object.keys(diff).length) localStorage.setItem(KEY + screen, JSON.stringify(diff));
    else localStorage.removeItem(KEY + screen);     // 처음 폭이면 기억할 것이 없다
  } catch { /* 저장을 못 해도 지금 화면에서는 그대로 동작한다 */ }
}
const within = (v, [lo, hi]) => Math.max(lo, Math.min(hi, v));

export function useColumns(screen, defaults, labels = {}) {
  const [box, setBox] = useState(null);     // 감싸는 요소 — 화면이 늦게 그려져도 잡히도록 콜백 ref 로 받는다
  const [w, setW] = useState(() => {
    const saved = readSaved(screen);
    const out = { ...defaults };
    for (const s of ["left", "right"]) if (Number.isFinite(saved[s])) out[s] = within(saved[s], LIMITS[s]);
    return out;
  });
  const [fold, setFold] = useState({ left: false, right: false });
  const [geo, setGeo] = useState({ left: null, right: null });
  const [dragging, setDragging] = useState("");
  const live = useRef({ w, fold, geo });
  live.current = { w, fold, geo };

  // 화면을 떠났다 오면 접힌 칸을 펼친다(접기는 기억하지 않는다 — 위 설명).
  useEffect(() => { if (!box) setFold({ left: false, right: false }); }, [box]);

  // 손잡이 자리는 칸의 실제 경계에서 잰다 — 창이 좁아 칸이 CSS 최소값까지 눌렸을 때도 경계에 붙어 있게.
  const measure = useCallback(() => {
    if (!box) return;
    const b = box.getBoundingClientRect();
    const edge = (side) => {
      const el = box.querySelector(`:scope > .col.${side}`);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: Math.round((side === "left" ? r.right : r.left) - b.left), top: Math.round(r.top - b.top) };
    };
    const next = { left: edge("left"), right: edge("right") };
    setGeo((g) => (JSON.stringify(g) === JSON.stringify(next) ? g : next));
  }, [box]);

  useLayoutEffect(() => { measure(); }, [measure, w, fold]);
  useEffect(() => {
    if (!box || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => measure());
    ro.observe(box);
    box.querySelectorAll(":scope > .col").forEach((el) => ro.observe(el));
    return () => ro.disconnect();
  }, [box, measure]);

  // 가운데 칸이 CENTER_MIN 보다 좁아지지 않는 선에서만 넓힌다.
  function fit(side, v) {
    const { w: cw, fold: cf, geo: cg } = live.current;
    const other = side === "left" ? "right" : "left";
    const otherW = cg[other] && !cf[other] ? cw[other] : 0;
    const room = box ? box.clientWidth - otherW - CENTER_MIN : LIMITS[side][1];
    return Math.round(within(Math.min(v, room), LIMITS[side]));
  }
  function commit(next) { setW(next); writeSaved(screen, next, defaults); }
  function reset(side) { commit({ ...live.current.w, [side]: defaults[side] }); }
  function toggle(side) { setFold((f) => ({ ...f, [side]: !f[side] })); }

  function onPointerDown(side, e) {
    if (e.button !== 0 || live.current.fold[side] || e.target.closest("button")) return;
    e.preventDefault();
    const el = e.currentTarget;
    const x0 = e.clientX;
    const w0 = live.current.w[side];
    try { el.setPointerCapture(e.pointerId); } catch { /* 없어도 끌기는 된다 */ }
    setDragging(side);
    document.body.classList.add("col-dragging");
    const move = (ev) => {
      const dx = ev.clientX - x0;
      const v = fit(side, side === "left" ? w0 + dx : w0 - dx);
      setW((cur) => (cur[side] === v ? cur : { ...cur, [side]: v }));
    };
    const up = () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
      document.body.classList.remove("col-dragging");
      setDragging("");
      writeSaved(screen, live.current.w, defaults);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
  }

  function onKeyDown(side, e) {
    if (e.target !== e.currentTarget) return;        // 안쪽 접기 단추의 Enter 는 단추의 일이다
    const cw = live.current.w;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const d = (e.key === "ArrowRight" ? STEP : -STEP) * (side === "left" ? 1 : -1);
      commit({ ...cw, [side]: fit(side, cw[side] + d) });
    } else if (e.key === "Enter") {
      e.preventDefault();
      reset(side);
    }
  }

  function grip(side) {
    const g = geo[side];
    if (!g) return null;
    const name = labels[side] || (side === "left" ? "왼쪽 칸" : "오른쪽 칸");
    if (fold[side]) {
      return (
        <button key={side} type="button" className={"colrail " + side} style={{ top: g.top }}
          onClick={() => toggle(side)} title={`${name} 펼치기`} aria-label={`${name} 펼치기`}>
          <span aria-hidden="true">{side === "left" ? "▸" : "◂"}</span>
          <span className="colrail-lbl">{name}</span>
        </button>
      );
    }
    return (
      <div key={side} className={"colgrip" + (dragging === side ? " on" : "")} style={{ left: g.x, top: g.top }}
        role="separator" aria-orientation="vertical" tabIndex={0}
        aria-label={`${name} 폭`} aria-valuenow={w[side]} aria-valuemin={LIMITS[side][0]} aria-valuemax={LIMITS[side][1]}
        title={`${name} 폭 — 끌어서 조절 · 두 번 누르면 처음 폭`}
        onPointerDown={(e) => onPointerDown(side, e)}
        onDoubleClick={(e) => { if (!e.target.closest("button")) reset(side); }}
        onKeyDown={(e) => onKeyDown(side, e)}>
        <button type="button" className="colfold" onClick={() => toggle(side)}
          title={`${name} 접기`} aria-label={`${name} 접기`}>{side === "left" ? "◂" : "▸"}</button>
      </div>
    );
  }

  const style = {
    "--col-l": `${fold.left ? 0 : w.left}px`,
    "--col-r": `${fold.right ? 0 : w.right}px`,
    "--col-l-min": `${fold.left ? 0 : LIMITS.left[0]}px`,
    "--col-r-min": `${fold.right ? 0 : LIMITS.right[0]}px`,
  };
  const cls = (fold.left ? " fold-l" : "") + (fold.right ? " fold-r" : "");
  return { ref: setBox, style, cls, handles: <>{grip("left")}{grip("right")}</> };
}
