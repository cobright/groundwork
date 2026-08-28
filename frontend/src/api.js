// FastAPI 백엔드 호출 헬퍼. vite proxy 로 /api → :8000 전달됨.
async function req(path, opts = {}) {
  const r = await fetch("/api" + path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) {
    const b = await r.json().catch(() => ({}));
    let msg = "요청 실패";
    const d = b && b.detail;
    if (typeof d === "string") msg = d;
    else if (Array.isArray(d)) msg = d.map((e) => (e && e.msg) ? e.msg : JSON.stringify(e)).join("; ");
    else if (d && typeof d === "object") msg = d.msg || JSON.stringify(d);
    throw new Error(msg);
  }
  return r.json();
}
export const api = {
  listProjects: () => req("/projects"),
  createProject: (p) => req("/projects", { method: "POST", body: JSON.stringify(p) }),
  updateProject: (id, p) => req(`/projects/${id}`, { method: "PUT", body: JSON.stringify(p) }),
  getOutline: (id) => req(`/projects/${id}/outline`),
  putOutline: (id, nodes) => req(`/projects/${id}/outline`, { method: "PUT", body: JSON.stringify({ nodes }) }),
  putCard: (id, uid, card) => req(`/projects/${id}/cards/${uid}`, { method: "PUT", body: JSON.stringify(card) }),
  // 초고
  getDraft: (id, uid) => req(`/projects/${id}/nodes/${uid}/draft`),
  generateDraft: (id, uid, strictness, provider) => req(`/projects/${id}/nodes/${uid}/draft/generate`, { method: "POST", body: JSON.stringify({ strictness, provider: provider || null }) }),
  saveDraftBody: (id, uid, body) => req(`/projects/${id}/nodes/${uid}/draft`, { method: "PUT", body: JSON.stringify({ body }) }),
  // 검토
  runReview: (id, uid, kind, provider, perspective) => req(`/projects/${id}/nodes/${uid}/review/run`, { method: "POST", body: JSON.stringify({ kind, provider: provider || null, perspective: perspective || "군수" }) }),
  runReviewWhole: (id, kind, provider, perspective) => req(`/projects/${id}/review/run`, { method: "POST", body: JSON.stringify({ kind, provider: provider || null, perspective: perspective || "군수" }) }),
  reviewPerspectives: (id) => req(`/projects/${id}/review/perspectives`),
  listReview: (id) => req(`/projects/${id}/review`),
  patchOpinion: (id, oid, patch) => req(`/projects/${id}/review/${oid}`, { method: "PUT", body: JSON.stringify(patch) }),
  deleteOpinion: (id, oid) => req(`/projects/${id}/review/${oid}`, { method: "DELETE" }),

  // 자료실
  listResources: (id) => req(`/projects/${id}/resources`),
  addResource: (id, r) => req(`/projects/${id}/resources`, { method: "POST", body: JSON.stringify(r) }),
  updateResource: (id, rid, r) => req(`/projects/${id}/resources/${rid}`, { method: "PUT", body: JSON.stringify(r) }),
  deleteResource: (id, rid) => req(`/projects/${id}/resources/${rid}`, { method: "DELETE" }),
  analyzeResource: (id, rid, provider) => req(`/projects/${id}/resources/${rid}/analyze`, { method: "POST", body: JSON.stringify({ provider: provider || null }) }),
  confirmAnalysis: (id, rid) => req(`/projects/${id}/resources/${rid}/confirm`, { method: "POST", body: "{}" }),
  // 근거표
  listEvidence: (id) => req(`/projects/${id}/evidence`),
  addEvidence: (id, e) => req(`/projects/${id}/evidence`, { method: "POST", body: JSON.stringify(e) }),
  updateEvidence: (id, eid, e) => req(`/projects/${id}/evidence/${eid}`, { method: "PUT", body: JSON.stringify(e) }),
  deleteEvidence: (id, eid) => req(`/projects/${id}/evidence/${eid}`, { method: "DELETE" }),
  // 최종본
  finalCheck: (id) => req(`/projects/${id}/final-check`),
  preview: (id) => req(`/projects/${id}/preview`),
  exportDocxUrl: (id, includeEvidence) => `/api/projects/${id}/export.docx?include_evidence=${includeEvidence ? "true" : "false"}`,

  // 공통자료실 — 부서 폴더
  listDepartments: () => req(`/library/departments`),
  createDepartment: (name) => req(`/library/departments`, { method: "POST", body: JSON.stringify({ name }) }),
  renameDepartment: (did, name) => req(`/library/departments/${did}`, { method: "PUT", body: JSON.stringify({ name }) }),
  deleteDepartment: (did) => req(`/library/departments/${did}`, { method: "DELETE" }),
  // 공통자료실 — 자료
  listLibResources: (deptId, q) => req(`/library/resources?${deptId ? `dept_id=${deptId}&` : ""}${q ? `q=${encodeURIComponent(q)}` : ""}`),
  addLibResource: (r) => req(`/library/resources`, { method: "POST", body: JSON.stringify(r) }),
  updateLibResource: (rid, r) => req(`/library/resources/${rid}`, { method: "PUT", body: JSON.stringify(r) }),
  deleteLibResource: (rid, force) => req(`/library/resources/${rid}${force ? "?force=true" : ""}`, { method: "DELETE" }),
  analyzeLibResource: (rid, provider) => req(`/library/resources/${rid}/analyze`, { method: "POST", body: JSON.stringify({ provider: provider || null }) }),
  confirmLibResource: (rid) => req(`/library/resources/${rid}/confirm`, { method: "POST", body: "{}" }),
  // 업무 ↔ 공통자료 참조
  addResourceRef: (pid, resourceId) => req(`/projects/${pid}/resource-refs`, { method: "POST", body: JSON.stringify({ resource_id: resourceId }) }),
  removeResourceRef: (pid, rid) => req(`/projects/${pid}/resource-refs/${rid}`, { method: "DELETE" }),
  promoteResource: (pid, rid, deptId) => req(`/projects/${pid}/resources/${rid}/promote`, { method: "POST", body: JSON.stringify({ dept_id: deptId }) }),

  // 부서 자료요청
  listRequests: (pid) => req(`/projects/${pid}/requests`),
  collectRequests: (pid) => req(`/projects/${pid}/requests/collect`, { method: "POST", body: "{}" }),
  addRequest: (pid, body) => req(`/projects/${pid}/requests`, { method: "POST", body: JSON.stringify(body) }),
  updateRequest: (pid, rid, patch) => req(`/projects/${pid}/requests/${rid}`, { method: "PUT", body: JSON.stringify(patch) }),
  deleteRequest: (pid, rid) => req(`/projects/${pid}/requests/${rid}`, { method: "DELETE" }),
  requestsXlsxUrl: (pid) => `/api/projects/${pid}/requests/export.xlsx`,
  registerRequestResource: (pid, rid) => req(`/projects/${pid}/requests/${rid}/register-resource`, { method: "POST", body: "{}" }),
};

export const REQUEST_STATUS = ["필요", "요청함", "회신옴", "반영", "보류"];

export async function fetchDashboard() { return req("/dashboard"); }

// 설정 · 진행상황 보고
export const reportApi = {
  getSettings: () => req("/settings"),
  putSettings: (author_name) => req("/settings", { method: "PUT", body: JSON.stringify({ author_name }) }),
  reportPreview: (pid) => req(`/projects/${pid}/report/preview`),
  reportExportUrl: (pid) => `/api/projects/${pid}/report/export`,
  // 받은 보고(팀장/과장)
  getInboxFolder: () => req("/inbox/settings"),
  setInboxFolder: (folder) => req("/inbox/settings", { method: "PUT", body: JSON.stringify({ folder }) }),
  pickFolder: () => req("/inbox/pick-folder", { method: "POST", body: "{}" }),
  readInbox: () => req("/inbox"),
};

export const RESOURCE_KINDS = ["기준자료", "내부자료", "부서자료", "외부자료", "웹자료", "메모"];
export const EVIDENCE_STATUS = ["확인", "확인 필요", "조건부", "충돌", "추정", "의견", "사용 보류"];
export const STRICTNESS = [["엄격", "엄격 — 확정 근거 안에서만"], ["유연", "유연 — 연결문장 허용, 추측은 표시"], ["자료목록", "자료목록만 — 필요한 자료 제시"]];
export const REVIEW_STATUS = ["미처리", "확인중", "반영", "일부반영", "반영안함", "보류"];
export const SEVERITY_ORDER = { "중대": 0, "중요": 1, "일반": 2, "참고": 3 };

export const TEMPLATES = {
  "공모사업 계획서": [["추진배경",[]],["사업 필요성",["지역 현황과 문제","기존 정책의 한계","사업의 정책적 근거"]],["사업 개요",["목적과 목표","사업 대상과 범위"]],["세부 추진계획",["주요 사업내용","추진체계","추진일정"]],["사업 차별성",[]],["재원 및 운영계획",["소요예산","재원조달","운영 지속성"]],["기대효과",[]],["평가항목 대응",[]]],
  "용역 과업지시서": [["과업의 배경 및 목적",[]],["과업 범위",["기본 과업","선택 과업"]],["과업 수행방법",[]],["과업 기간 및 일정",[]],["과업 결과물",[]],["수행자 자격 및 요건",[]],["대가 산정 및 지급",[]],["관리·감독 및 검수",[]]],
  "군정기획보고서": [["보고 목적",[]],["추진 배경 및 경위",[]],["현황 및 문제점",["현황","문제점"]],["추진 방향",[]],["세부 추진계획",["과제별 계획","추진일정"]],["소요예산 및 재원",[]],["기대효과",[]],["행정사항",[]]],
  "군수 관심사업 추진계획서": [["검토 요청사항",[]],["추진배경",[]],["지역 현황과 사업 필요성",[]],["대상지 현황",["위치·규모","소유 및 권리관계"]],["주요 쟁점",[]],["대안 비교",["대안별 개요","비교 검토"]],["권고안",[]],["추진계획",["단계별 추진","추진체계","재원 및 운영"]],["위험요인과 대응방안",[]],["결정 필요사항",[]]],
  "정책검토 보고서": [["검토 배경",[]],["검토 대상 및 방법",[]],["현황 분석",[]],["쟁점별 검토",["쟁점 1","쟁점 2","쟁점 3"]],["대안 및 비교",[]],["종합 검토의견",[]],["권고사항",[]]],
  "간부회의 보고자료": [["보고 개요",[]],["핵심 현황",[]],["주요 쟁점",[]],["검토 대안",[]],["추진(권고) 방안",[]],["소요예산·일정",[]],["결정 필요사항",[]]],
};

export const BLOCKS = [
  { name: "실행계획 중심", desc: "사업 실행방법을 명확히", sections: [["추진배경",[]],["사업개요",[]],["대상지 현황",[]],["세부 사업계획",[]],["추진체계",[]],["재원계획",[]],["추진일정",[]],["운영계획",[]],["기대효과",[]],["향후 조치사항",[]]] },
  { name: "문제해결 중심", desc: "문제와 사업의 인과관계", sections: [["지역의 현황과 문제",[]],["문제의 원인",[]],["기존 정책의 한계",[]],["사업 추진 필요성",[]],["정책 대안",[]],["권고 사업안",[]],["실행계획",[]],["기대효과",[]],["위험요인과 대응방안",[]]] },
  { name: "의사결정 중심", desc: "간부의 선택·결정을 도움", sections: [["검토 요청사항",[]],["검토배경",[]],["핵심 현황",[]],["주요 쟁점",[]],["대안 비교",[]],["종합 검토의견",[]],["권고안",[]],["권고안 추진계획",[]],["결정 필요사항",[]]] },
];

export const STATUSES = ["작성 전", "자료 부족", "작성 가능", "초고 작성 중", "사용자 확인", "확정"];
