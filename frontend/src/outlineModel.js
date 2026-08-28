// 목차 트리 · 집필카드 모델 (프레임워크 무관, 순수 함수).
// 핵심: 노드 id 는 한 번 부여되면 바뀌지 않는다 → 카드 연결 보존.

export function genUid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return "n-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
}
export function makeNode(title) { return { id: genUid(), title, children: [] }; }

export function buildNodes(spec) {
  return spec.map(([title, kids]) => {
    const n = makeNode(title);
    n.children = buildNodes((kids || []).map((k) => (Array.isArray(k) ? k : [k, []])));
    return n;
  });
}

export function locate(outline, id, arr = outline, parent = null) {
  for (let i = 0; i < arr.length; i++) {
    if (arr[i].id === id) return { node: arr[i], siblings: arr, index: i, parent };
    const f = locate(outline, id, arr[i].children, arr[i]);
    if (f) return f;
  }
  return null;
}
export function collectIds(n, acc = []) { acc.push(n.id); n.children.forEach((c) => collectIds(c, acc)); return acc; }
export function countNodes(arr) { return arr.reduce((s, n) => s + 1 + countNodes(n.children), 0); }
export function numberMap(outline) {
  const map = {};
  const walk = (arr, p) => arr.forEach((n, i) => { const num = p + (i + 1); map[n.id] = num; walk(n.children, num + "."); });
  walk(outline, ""); return map;
}

// 편집 연산: 전달된 outline 배열을 제자리에서 바꾸고, 그 배열을 반환한다.
export function addSibling(outline, selId) {
  const n = makeNode("새 항목");
  if (!selId) outline.push(n);
  else { const l = locate(outline, selId); l.siblings.splice(l.index + 1, 0, n); }
  return { outline, newId: n.id };
}
export function addChild(outline, selId) {
  if (!selId) return addSibling(outline, selId);
  const l = locate(outline, selId); const n = makeNode("새 하위 항목");
  l.node.children.push(n); return { outline, newId: n.id };
}
export function indent(outline, selId) {
  const l = locate(outline, selId); if (!l || l.index === 0) return { outline };
  l.siblings[l.index - 1].children.push(l.node); l.siblings.splice(l.index, 1); return { outline };
}
export function outdent(outline, selId) {
  const l = locate(outline, selId); if (!l || !l.parent) return { outline };
  const p = locate(outline, l.parent.id); l.siblings.splice(l.index, 1);
  p.siblings.splice(p.index + 1, 0, l.node); return { outline };
}
export function move(outline, selId, dir) {
  const l = locate(outline, selId); if (!l) return { outline };
  const j = l.index + dir; if (j < 0 || j >= l.siblings.length) return { outline };
  [l.siblings[l.index], l.siblings[j]] = [l.siblings[j], l.siblings[l.index]]; return { outline };
}
export function removeNode(outline, selId) {
  const l = locate(outline, selId); if (!l) return { outline, removedIds: [] };
  const removedIds = collectIds(l.node); l.siblings.splice(l.index, 1); return { outline, removedIds };
}

// 트리 ↔ 평면(서버 저장용)
export function flatten(outline) {
  const out = []; let sort = 0;
  const walk = (arr, parent) => arr.forEach((n) => { out.push({ uid: n.id, parent_uid: parent, sort: sort++, title: n.title }); walk(n.children, n.id); });
  walk(outline, null); return out;
}
export function rebuild(nodes) {
  const byId = {}; nodes.forEach((n) => (byId[n.uid] = { id: n.uid, title: n.title, children: [] }));
  const roots = [];
  nodes.forEach((n) => { const nd = byId[n.uid]; if (n.parent_uid && byId[n.parent_uid]) byId[n.parent_uid].children.push(nd); else roots.push(nd); });
  return roots;
}
