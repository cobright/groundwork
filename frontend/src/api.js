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
  // 목차 틀은 백엔드가 유일한 출처다(문서 유형이 초고 문체까지 가르므로 한곳에 둔다).
  getTemplates: () => req("/templates"),
  listProjects: () => req("/projects"),
  createProject: (p) => req("/projects", { method: "POST", body: JSON.stringify(p) }),
  updateProject: (id, p) => req(`/projects/${id}`, { method: "PUT", body: JSON.stringify(p) }),
  // 보관함(캐비넷) — 삭제는 보관함에 넣은 뒤에만 할 수 있다
  listArchived: () => req("/projects?archived=true"),
  archiveProject: (id, note) => req(`/projects/${id}/archive`, { method: "POST", body: JSON.stringify({ note }) }),
  unarchiveProject: (id) => req(`/projects/${id}/unarchive`, { method: "POST", body: "{}" }),
  deletePreview: (id) => req(`/projects/${id}/delete-preview`),
  deleteProject: (id) => req(`/projects/${id}`, { method: "DELETE" }),
  // 담당자 진술 — 파일 없이 근거를 세우는 짧은 경로(제안 → 사람이 채택)
  addStatement: (id, body) => req(`/projects/${id}/statements`, { method: "POST", body: JSON.stringify(body) }),
  adoptStatement: (id, rid, body) => req(`/projects/${id}/statements/${rid}/adopt`, { method: "POST", body: JSON.stringify(body) }),
  // 보고전 뽑기 — 진행 중인 업무는 손대지 않고 새 업무를 만든다(확정 근거를 함께 넘김)
  spinoff: (id, body) => req(`/projects/${id}/spinoff`, { method: "POST", body: JSON.stringify(body) }),
  replacePreview: (id) => req(`/projects/${id}/outline/replace-preview`),
  // 되돌리기: 목차를 통째로 갈아끼우기 직전 상태가 자동으로 적힌다(사람이 직접 찍을 수도 있다)
  listSnapshots: (id) => req(`/projects/${id}/outline/snapshots`),
  takeSnapshot: (id) => req(`/projects/${id}/outline/snapshots`, { method: "POST", body: "{}" }),
  restoreSnapshot: (id, sid) => req(`/projects/${id}/outline/snapshots/${sid}/restore`, { method: "POST", body: "{}" }),
  deleteSnapshot: (id, sid) => req(`/projects/${id}/outline/snapshots/${sid}`, { method: "DELETE" }),
  listBackups: () => req(`/backups`),
  // AI 설정: 화면에서 넣은 값이 .env 보다 앞선다(저장 즉시 반영 — 재시작 불필요). 등급(빠름·기본·정밀)마다 회사·모델.
  getAiConfig: () => req(`/ai/config`),
  putAiConfig: (body) => req(`/ai/config`, { method: "PUT", body: JSON.stringify(body) }),
  testAi: (body) => req(`/ai/test`, { method: "POST", body: JSON.stringify(body || {}) }),
  // 그 회사가 지금 제공하는 모델 목록(저장하지 않는다 — 이름은 몇 달이면 바뀐다)
  listAiModels: (provider) => req(`/ai/models?provider=${encodeURIComponent(provider)}`),
  getOutline: (id) => req(`/projects/${id}/outline`),
  putOutline: (id, nodes) => req(`/projects/${id}/outline`, { method: "PUT", body: JSON.stringify({ nodes }) }),
  putCard: (id, uid, card) => req(`/projects/${id}/cards/${uid}`, { method: "PUT", body: JSON.stringify(card) }),
  // 초고
  getDraft: (id, uid) => req(`/projects/${id}/nodes/${uid}/draft`),
  generateDraft: (id, uid, strictness, provider) => req(`/projects/${id}/nodes/${uid}/draft/generate`, { method: "POST", body: JSON.stringify({ strictness, provider: provider || null }) }),
  saveDraftBody: (id, uid, body) => req(`/projects/${id}/nodes/${uid}/draft`, { method: "PUT", body: JSON.stringify({ body }) }),
  // 검토
  runReview: (id, uid, kind, provider, perspective) => req(`/projects/${id}/nodes/${uid}/review/run`, { method: "POST", body: JSON.stringify({ kind, provider: provider || null, perspective: perspective || "기관장" }) }),
  runReviewWhole: (id, kind, provider, perspective) => req(`/projects/${id}/review/run`, { method: "POST", body: JSON.stringify({ kind, provider: provider || null, perspective: perspective || "기관장" }) }),
  reviewPerspectives: (id) => req(`/projects/${id}/review/perspectives`),
  listReview: (id) => req(`/projects/${id}/review`),
  patchOpinion: (id, oid, patch) => req(`/projects/${id}/review/${oid}`, { method: "PUT", body: JSON.stringify(patch) }),
  deleteOpinion: (id, oid) => req(`/projects/${id}/review/${oid}`, { method: "DELETE" }),
  // 검토의견을 그 자리에서 자료요청으로. 중복 방지 키는 자동 수집과 같다(두 번 만들어지지 않는다)
  opinionToRequest: (id, oid, body) => req(`/projects/${id}/review/${oid}/to-request`,
    { method: "POST", body: JSON.stringify(body || {}) }),

  // 자료실
  listResources: (id) => req(`/projects/${id}/resources`),
  addResource: (id, r) => req(`/projects/${id}/resources`, { method: "POST", body: JSON.stringify(r) }),
  updateResource: (id, rid, r) => req(`/projects/${id}/resources/${rid}`, { method: "PUT", body: JSON.stringify(r) }),
  deleteResource: (id, rid) => req(`/projects/${id}/resources/${rid}`, { method: "DELETE" }),
  // 파일로 자료 등록 — 한글·엑셀·워드·PDF 를 읽어 본문에 담고 원본은 그대로 보관한다.
  // multipart 대신 원시 바이트(양식·가이드라인과 같은 방식).
  uploadResource: (id, file, opt) => req(
    `/projects/${id}/resources/upload?filename=${encodeURIComponent(file.name)}`
    + `&name=${encodeURIComponent((opt && opt.name) || "")}`
    + `&kind=${encodeURIComponent((opt && opt.kind) || "부서자료")}`
    + `&source_org=${encodeURIComponent((opt && opt.source_org) || "")}`
    + `&base_date=${encodeURIComponent((opt && opt.base_date) || "")}`,
    { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file }),
  resourceFileUrl: (id, rid) => `/api/projects/${id}/resources/${rid}/file`,
  // 담당자 메모만 고치기. 자료요청 화면에서도 같은 칸을 열기 위해 따로 둔다
  // (자료 수정은 본문까지 통째로 받으므로 메모 한 줄에 쓰면 나머지가 지워진다)
  setResourceNote: (id, rid, note) => req(`/projects/${id}/resources/${rid}/note`,
    { method: "PUT", body: JSON.stringify({ note }) }),
  analyzeResource: (id, rid, provider) => req(`/projects/${id}/resources/${rid}/analyze`, { method: "POST", body: JSON.stringify({ provider: provider || null }) }),
  confirmAnalysis: (id, rid, force = false) => req(`/projects/${id}/resources/${rid}/confirm`, { method: "POST", body: JSON.stringify({ force }) }),
  // 근거표
  listEvidence: (id) => req(`/projects/${id}/evidence`),
  addEvidence: (id, e) => req(`/projects/${id}/evidence`, { method: "POST", body: JSON.stringify(e) }),
  updateEvidence: (id, eid, e) => req(`/projects/${id}/evidence/${eid}`, { method: "PUT", body: JSON.stringify(e) }),
  deleteEvidence: (id, eid) => req(`/projects/${id}/evidence/${eid}`, { method: "DELETE" }),
  // '근거 자료 변경됨' 신호는 사람이 원문을 확인했을 때만 내린다(수정으로는 안 꺼짐)
  ackEvidence: (id, eid) => req(`/projects/${id}/evidence/${eid}/acknowledge`, { method: "POST", body: "{}" }),
  // 최종본
  finalCheck: (id) => req(`/projects/${id}/final-check`),
  preview: (id) => req(`/projects/${id}/preview`),
  exportDocxUrl: (id, includeEvidence) => `/api/projects/${id}/export.docx?include_evidence=${includeEvidence ? "true" : "false"}`,
  // 한글(HWPX) 양식 보관함 — 양식은 사용자가 올린 원본을 그대로 보관한다
  listForms: () => req(`/forms`),
  deleteForm: (fid) => req(`/forms/${fid}`, { method: "DELETE" }),
  // multipart 대신 원시 바이트로 보낸다(python-multipart 의존성을 늘리지 않기 위해)
  uploadForm: (file, name, note) => req(
    `/forms?filename=${encodeURIComponent(file.name)}&name=${encodeURIComponent(name || "")}&note=${encodeURIComponent(note || "")}`,
    { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file }),
  exportHwpxUrl: (id, formId, org, pageBreak) =>
    `/api/projects/${id}/export.hwpx?form_id=${formId}&org=${encodeURIComponent(org || "")}&page_break=${pageBreak ? "true" : "false"}`,

  // 공모 가이드라인 — 올리고(원본 보관) → 분석(제안만) → 사람이 골라 심는다
  listGuidelines: (id) => req(`/projects/${id}/guidelines`),
  uploadGuideline: (id, file, kind) => req(
    `/projects/${id}/guidelines?filename=${encodeURIComponent(file.name)}&doc_kind=${encodeURIComponent(kind || "공고")}`,
    { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file }),
  deleteGuideline: (gid) => req(`/guidelines/${gid}`, { method: "DELETE" }),
  // 공모에 딸려 온 '서식'을 양식 보관함으로 넘긴다 — 같은 파일을 두 번 올리지 않게
  guidelineToForm: (gid) => req(`/guidelines/${gid}/to-form`, { method: "POST", body: "{}" }),
  guidelineBlocks: (gid, start, limit) => req(`/guidelines/${gid}/blocks?start=${start || 0}&limit=${limit || 400}`),
  analyzeGuideline: (gid, body) => req(`/guidelines/${gid}/analyze`, { method: "POST", body: JSON.stringify(body || {}) }),
  guidelineAnalysis: (gid) => req(`/guidelines/${gid}/analysis`),
  // 정정 공고 비교 — 저장된 분석 결과끼리 견준다(다시 읽지 않는다)
  guidelineCompare: (gid, against) => req(`/guidelines/${gid}/compare${against ? `?against=${against}` : ""}`),
  adoptGuidelineNeeds: (id, gid, items) => req(`/projects/${id}/guidelines/${gid}/adopt-needs`,
    { method: "POST", body: JSON.stringify({ items }) }),

  // 공통자료실 — 부서 폴더
  listDepartments: () => req(`/library/departments`),
  createDepartment: (name) => req(`/library/departments`, { method: "POST", body: JSON.stringify({ name }) }),
  renameDepartment: (did, name) => req(`/library/departments/${did}`, { method: "PUT", body: JSON.stringify({ name }) }),
  deleteDepartment: (did) => req(`/library/departments/${did}`, { method: "DELETE" }),
  // 공통자료실 — 자료
  listLibResources: (deptId, q) => req(`/library/resources?${deptId ? `dept_id=${deptId}&` : ""}${q ? `q=${encodeURIComponent(q)}` : ""}`),
  addLibResource: (r) => req(`/library/resources`, { method: "POST", body: JSON.stringify(r) }),
  updateLibResource: (rid, r) => req(`/library/resources/${rid}`, { method: "PUT", body: JSON.stringify(r) }),
  // 공통자료도 파일로 등록한다(업무 자료와 같은 엔진). 여럿이 함께 쓰는 자료라 원본 보관이 더 중요하다.
  uploadLibResource: (deptId, file, opt) => req(
    `/library/resources/upload?dept_id=${deptId}&filename=${encodeURIComponent(file.name)}`
    + `&name=${encodeURIComponent((opt && opt.name) || "")}`
    + `&kind=${encodeURIComponent((opt && opt.kind) || "부서자료")}`
    + `&source_org=${encodeURIComponent((opt && opt.source_org) || "")}`
    + `&base_date=${encodeURIComponent((opt && opt.base_date) || "")}`,
    { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file }),
  libFileUrl: (rid) => `/api/library/resources/${rid}/file`,
  setLibNote: (rid, note) => req(`/library/resources/${rid}/note`, { method: "PUT", body: JSON.stringify({ note }) }),
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
  reopenRequest: (pid, rid, reason) => req(`/projects/${pid}/requests/${rid}/reopen`, { method: "POST", body: JSON.stringify({ reason: reason || "" }) }),
  updateRequest: (pid, rid, patch) => req(`/projects/${pid}/requests/${rid}`, { method: "PUT", body: JSON.stringify(patch) }),
  deleteRequest: (pid, rid) => req(`/projects/${pid}/requests/${rid}`, { method: "DELETE" }),
  requestsXlsxUrl: (pid) => `/api/projects/${pid}/requests/export.xlsx`,
  registerRequestResource: (pid, rid) => req(`/projects/${pid}/requests/${rid}/register-resource`, { method: "POST", body: "{}" }),
  // 부서가 보낸 파일 그대로 회신 등록(엑셀·한글·워드·PDF). 읽어서 자료로 담기까지만 한다.
  uploadReceivedFile: (pid, rid, file) => req(
    `/projects/${pid}/requests/${rid}/received-file?filename=${encodeURIComponent(file.name)}`,
    { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file }),

  // 주민 설문 — ①근거 지도 ②문항 설계 ③점검(규칙, 의견만) ④폼으로 옮기기. 응답 파일 정리·분석은 실물을 받은 뒤.
  // 모든 쓰기는 설문 전체(설문·주장·문항·점검·폼 표)를 다시 돌려준다 — 점검이 바로 따라오게.
  listSurveys: (pid) => req(`/projects/${pid}/surveys`),
  createSurvey: (pid, body) => req(`/projects/${pid}/surveys`, { method: "POST", body: JSON.stringify(body || {}) }),
  getSurvey: (sid) => req(`/surveys/${sid}`),
  updateSurvey: (sid, patch) => req(`/surveys/${sid}`, { method: "PUT", body: JSON.stringify(patch) }),
  surveyDeletePreview: (sid) => req(`/surveys/${sid}/delete-preview`),
  deleteSurvey: (sid) => req(`/surveys/${sid}`, { method: "DELETE" }),
  addClaim: (sid, body) => req(`/surveys/${sid}/claims`, { method: "POST", body: JSON.stringify(body) }),
  updateClaim: (sid, cid, patch) => req(`/surveys/${sid}/claims/${cid}`, { method: "PUT", body: JSON.stringify(patch) }),
  deleteClaim: (sid, cid) => req(`/surveys/${sid}/claims/${cid}`, { method: "DELETE" }),
  // 통계로 받칠 주장 → 부서 자료요청(같은 주장은 한 번만 올라간다)
  claimToRequest: (sid, cid, need) => req(`/surveys/${sid}/claims/${cid}/to-request`, { method: "POST", body: JSON.stringify({ need }) }),
  addQuestion: (sid, body) => req(`/surveys/${sid}/questions`, { method: "POST", body: JSON.stringify(body) }),
  updateQuestion: (sid, qid, patch) => req(`/surveys/${sid}/questions/${qid}`, { method: "PUT", body: JSON.stringify(patch) }),
  deleteQuestion: (sid, qid) => req(`/surveys/${sid}/questions/${qid}`, { method: "DELETE" }),
  orderQuestions: (sid, ids) => req(`/surveys/${sid}/questions-order`, { method: "PUT", body: JSON.stringify({ ids }) }),
  surveyFormXlsxUrl: (sid) => `/api/surveys/${sid}/form.xlsx`,
};

export const REQUEST_STATUS = ["필요", "요청함", "회신옴", "반영", "보류"];

export async function fetchDashboard() { return req("/dashboard"); }

// 설정 · 진행상황 보고
export const reportApi = {
  getSettings: () => req("/settings"),
  // 보낸 항목만 바뀐다(부분수정). 이름만 고칠 때 부서가 지워지면 안 된다.
  putSettings: (patch) => req("/settings", { method: "PUT",
    body: JSON.stringify(typeof patch === "string" ? { author_name: patch } : patch) }),
  reportPreview: (pid) => req(`/projects/${pid}/report/preview`),
  reportExportUrl: (pid) => `/api/projects/${pid}/report/export`,
  // 받은 보고(팀장/과장)
  getInboxFolder: () => req("/inbox/settings"),
  setInboxFolder: (folder) => req("/inbox/settings", { method: "PUT", body: JSON.stringify({ folder }) }),
  pickFolder: () => req("/inbox/pick-folder", { method: "POST", body: "{}" }),
  readInbox: () => req("/inbox"),
};

export const RESOURCE_KINDS = ["기준자료", "내부자료", "부서자료", "외부자료", "웹자료", "메모", "담당자 진술"];
export const EVIDENCE_STATUS = ["확인", "진술", "확인 필요", "조건부", "충돌", "추정", "의견", "사용 보류"];
export const STRICTNESS = [["엄격", "엄격 — 확정 근거 안에서만"], ["유연", "유연 — 연결문장 허용, 추측은 표시"], ["자료목록", "자료목록만 — 필요한 자료 제시"]];
export const REVIEW_STATUS = ["미처리", "확인중", "반영", "일부반영", "반영안함", "보류"];
export const SEVERITY_ORDER = { "중대": 0, "중요": 1, "일반": 2, "참고": 3 };

export const STATUSES = ["작성 전", "자료 부족", "작성 가능", "초고 작성 중", "사용자 확인", "확정"];

// 작업 화면에서 고르는 회사. **여기 한 곳에서만 만든다** — 예전에는 네 화면이 각자
// 하드코딩해서, 회사를 하나 더하면 한 화면만 고쳐지고 나머지는 모르는 상태가 됐다.
// 이름은 백엔드 services/aiconfig.py 의 PROVIDERS 와 같아야 한다.
export const PROVIDERS = [["", "설정대로"], ["openai", "OpenAI"], ["claude", "Claude"],
                          ["gemini", "Gemini"], ["compat", "호환 서버"]];
