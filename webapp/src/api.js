import { getInitData } from "./telegram.js";

// Тот же контракт, что guro_id_api.py: Authorization: tma <initData>,
// относительные пути — сервис отдаёт и API, и статику с одного origin
// (см. guro_id_api.create_app).

class ApiError extends Error {
  // details (27.08.2026, ТЗ "Тарифы и лимиты") — полное тело ответа об
  // ошибке (например resets_at/limit у лимитов), не только code — раньше
  // терялось, экраны могли показать только общий текст без "когда обновится".
  constructor(status, code, details) {
    super(code);
    this.status = status;
    this.code = code;
    this.details = details || null;
  }
}

async function request(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      Authorization: `tma ${getInitData()}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  let body = null;
  try {
    body = await res.json();
  } catch {
    // пустое/не-JSON тело — оставляем null
  }
  if (!res.ok) {
    throw new ApiError(res.status, body?.error || "UNKNOWN", body);
  }
  return body;
}

// workspace="recruiter" (Фаза 3, 12.08.2026) — кабинет рекрутера вместо
// личного профиля, см. guro_id_api.py::_recruiter_summary.
export function getMe({ workspace } = {}) {
  return request(`/api/me${workspace ? `?workspace=${workspace}` : ""}`);
}

// Универсальный поиск (10.08.2026): одно поле q= — бэкенд сам решает,
// точный это юзернейм (mode=profile) или описание (mode=list,
// платный directory-поиск), см. handle_search в guro_id_api.py. top=true
// (Фаза 2) — сортировка "ТОП рейтинга" для описания (на точный юзернейм
// не влияет, там всегда один профиль).
export function search(query, { top } = {}) {
  return request(`/api/search?q=${encodeURIComponent(query)}${top ? "&top=1" : ""}`);
}

export function searchByUserId(userId, { workspace } = {}) {
  return request(
    `/api/search?user_id=${encodeURIComponent(userId)}${workspace ? `&workspace=${workspace}` : ""}`,
  );
}

export function createPartnership({
  confirmerUsername, vertical, geo, offer, amountReceived, amountPaid, review, amountVisible, txHash,
  ptype, txNetwork, asCompany,
}) {
  return request("/api/partnerships", {
    method: "POST",
    body: JSON.stringify({
      confirmer_username: confirmerUsername,
      vertical: vertical || null,
      geo: geo || null,
      offer: offer || null,
      amount_received: amountReceived || null,
      amount_paid: amountPaid || null,
      review: review || null,
      amount_visible: !!amountVisible,
      tx_hash: txHash || null,
      ptype,
      tx_network: txHash ? txNetwork : null,
      // as_company (27.08.2026, ТЗ "Роли и команда") — "действую как
      // компания": сделка попадает в общую историю компании (см. company_id
      // в partnerships), лимит новых заявок считается на компанию.
      as_company: !!asCompany,
    }),
  });
}

// Оценка партнёрства, Шаг 2 (ТЗ 6.1, 25.08.2026) — независимо от контрагента,
// обе оценки скрыты друг от друга до раскрытия (см. guro_id_api.py).
export function ratePartnership(partnershipId, verdict, comment) {
  return request(`/api/partnerships/${encodeURIComponent(partnershipId)}/rate`, {
    method: "POST",
    body: JSON.stringify({ verdict, comment: comment || null }),
  });
}

// Удаление своей оценки (25.08.2026, фидбек владельца "Правки.pdf").
export function deleteRating(partnershipId) {
  return request(`/api/partnerships/${encodeURIComponent(partnershipId)}/rate/delete`, {
    method: "POST",
  });
}

export function getPendingRatings() {
  return request("/api/partnerships/pending_ratings");
}

// Верификация адреса компании (ТЗ 5.5, 25.08.2026) — кабинет "Компания".
export function submitCompanyAddress(network, address) {
  return request("/api/company/address", {
    method: "POST",
    body: JSON.stringify({ network, address }),
  });
}

export function getCompanyAddresses() {
  return request("/api/company/addresses");
}

// Browse по вертикали (Фаза 2, 11.08.2026) — альтернатива текстовому
// поиску для тех, кто не знает точного юзернейма. top=true — сортировка
// "ТОП рейтинга" вместо силы совпадения (тот же флаг, что у search()).
export function browseVertical(vertical, { top } = {}) {
  return request(`/api/search?vertical=${encodeURIComponent(vertical)}${top ? "&top=1" : ""}`);
}

// «Резюме» (Фаза 4, 12.08.2026) — фильтр work_status=looking поверх того
// же поиска, vertical опционален (пустая строка/undefined -> без фильтра
// по вертикали, просто все, кто ищет работу).
export function browseResumes(vertical, { top } = {}) {
  return request(
    `/api/search?resumes=1${vertical ? `&vertical=${encodeURIComponent(vertical)}` : ""}${top ? "&top=1" : ""}`,
  );
}

// «Поиск кандидатов» кабинета Рекрутер/Компания (27.08.2026, ТЗ "экраны по
// ТЗ от 23.08") — тот же /api/search, что и browseVertical/browseResumes
// выше, просто в одном запросе сразу вертикаль+грейд+должность+"ищет
// работу"+топ-рейтинг (см. _directory_browse/_resume_browse в guro_id_api.py).
export function searchCandidates({ vertical, grade, position, looking, top } = {}) {
  const params = new URLSearchParams();
  if (looking) params.set("resumes", "1");
  if (vertical) params.set("vertical", vertical);
  if (grade) params.set("grade", grade);
  if (position) params.set("position", position);
  if (top) params.set("top", "1");
  return request(`/api/search?${params.toString()}`);
}

export function getInviteLink() {
  return request("/api/invite_link");
}

// Вакансии (Фаза 4, 12.08.2026; переписано 26.08.2026 под ТЗ "Recruitment —
// ВАКАНСИИ") — публикует подписчик кабинета Рекрутер ИЛИ Компания,
// просматривает любой с базовой подпиской GURO ID.
export function getPositions() {
  return request("/api/positions");
}

export function getVacancies({ lang, vertical, grade, position, q, companyType } = {}) {
  const params = new URLSearchParams();
  if (lang) params.set("lang", lang);
  if (vertical) params.set("vertical", vertical);
  if (grade) params.set("grade", grade);
  if (position) params.set("position", position);
  if (q) params.set("q", q);
  if (companyType) params.set("company_type", companyType);
  const qs = params.toString();
  return request(`/api/vacancies${qs ? `?${qs}` : ""}`);
}

export function getMyVacancies() {
  return request("/api/vacancies/mine");
}

export function getVacancy(id) {
  return request(`/api/vacancies/${encodeURIComponent(id)}`);
}

export function createVacancy(data) {
  return request("/api/vacancies", { method: "POST", body: JSON.stringify(data) });
}

export function editVacancy(id, fields) {
  return request(`/api/vacancies/${encodeURIComponent(id)}/edit`, {
    method: "POST",
    body: JSON.stringify(fields),
  });
}

export function pauseVacancy(id) {
  return request(`/api/vacancies/${encodeURIComponent(id)}/pause`, { method: "POST" });
}

export function resumeVacancy(id) {
  return request(`/api/vacancies/${encodeURIComponent(id)}/resume`, { method: "POST" });
}

export function extendVacancy(id, durationDays) {
  return request(`/api/vacancies/${encodeURIComponent(id)}/extend`, {
    method: "POST",
    body: JSON.stringify({ duration_days: durationDays }),
  });
}

export function closeVacancy(id, reason) {
  return request(`/api/vacancies/${encodeURIComponent(id)}/close`, {
    method: "POST",
    body: JSON.stringify({ reason: reason || null }),
  });
}

export function respondVacancy(id, message) {
  return request(`/api/vacancies/${encodeURIComponent(id)}/respond`, {
    method: "POST",
    body: JSON.stringify({ message: message || null }),
  });
}

export function getVacancyResponses(id, { status } = {}) {
  return request(`/api/vacancies/${encodeURIComponent(id)}/responses${status ? `?status=${status}` : ""}`);
}

export function getMyResponses({ status } = {}) {
  return request(`/api/responses${status ? `?status=${status}` : ""}`);
}

export function updateResponseStatus(id, status) {
  return request(`/api/responses/${encodeURIComponent(id)}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

// product="recruiter" (Фаза 3) — тарифы/оплата кабинета рекрутера вместо
// базовой подписки GURO ID, та же платёжная цепочка на бэкенде.
export function getPlans({ product } = {}) {
  return request(`/api/plans${product ? `?product=${product}` : ""}`);
}

export function subscribe(plan, { product } = {}) {
  return request("/api/subscribe", { method: "POST", body: JSON.stringify({ plan, product }) });
}

export function subscribeCrypto(plan, { product } = {}) {
  return request("/api/subscribe/crypto", { method: "POST", body: JSON.stringify({ plan, product }) });
}

export function setPrivacyField(field, value) {
  return request("/api/privacy", {
    method: "POST",
    body: JSON.stringify({ field, value }),
  });
}

export function setProfileField(field, value) {
  return request("/api/profile", {
    method: "POST",
    body: JSON.stringify({ field, value }),
  });
}

// Кабинет рекрутера (Фаза 3) — отдельная витрина/приватность, отдельные
// эндпоинты (не workspace= у /api/profile — разные таблицы/наборы полей).
export function setRecruiterProfileField(field, value) {
  return request("/api/recruiter/profile", {
    method: "POST",
    body: JSON.stringify({ field, value }),
  });
}

export function setRecruiterPrivacyField(field, value) {
  return request("/api/recruiter/privacy", {
    method: "POST",
    body: JSON.stringify({ field, value }),
  });
}

// Кабинет "Компания" (16.08.2026) — третий воркспейс, зеркало рекрутера.
export function setCompanyProfileField(field, value) {
  return request("/api/company/profile", {
    method: "POST",
    body: JSON.stringify({ field, value }),
  });
}

export function setCompanyPrivacyField(field, value) {
  return request("/api/company/privacy", {
    method: "POST",
    body: JSON.stringify({ field, value }),
  });
}

// Загрузка лого/обложки файлом (28.08.2026) — FormData, НЕ через общий
// request(): та жёстко ставит Content-Type: application/json на любое
// тело, а multipart нужен свой boundary, который браузер проставляет сам
// ТОЛЬКО если Content-Type вообще не задан руками.
export async function uploadCompanyImage(kind, file) {
  const formData = new FormData();
  formData.append("kind", kind);
  formData.append("file", file);
  const res = await fetch("/api/company/image", {
    method: "POST",
    headers: { Authorization: `tma ${getInitData()}` },
    body: formData,
  });
  let body = null;
  try {
    body = await res.json();
  } catch {
    // пустое/не-JSON тело — оставляем null
  }
  if (!res.ok) {
    throw new ApiError(res.status, body?.error || "UNKNOWN", body);
  }
  return body;
}

// Верификация бейджа компании (26.08.2026, ТЗ "Компания. каб") — ручной MVP,
// эндпоинт только фиксирует запрос, реальная сверка — админом в /admin.
export function requestCompanyVerification() {
  return request("/api/company/verification/request", { method: "POST" });
}

// Роли и команда (27.08.2026, ТЗ "Роли и управление командой") — компания
// теперь МНОГИХ людей: создание, запрос на присоединение, экран "Команда"
// (участники + заявки), одобрение/отклонение/удаление/передача владения.
export function createCompany(fields) {
  return request("/api/company/create", { method: "POST", body: JSON.stringify(fields) });
}

export function requestJoinCompany(companyId, positionText) {
  return request("/api/company/join_request", {
    method: "POST",
    body: JSON.stringify({ company_id: companyId, position_text: positionText || null }),
  });
}

export function getCompanyTeam() {
  return request("/api/company/team");
}

export function approveJoinRequest(requestId) {
  return request(`/api/company/team/requests/${encodeURIComponent(requestId)}/approve`, { method: "POST" });
}

export function rejectJoinRequest(requestId) {
  return request(`/api/company/team/requests/${encodeURIComponent(requestId)}/reject`, { method: "POST" });
}

export function removeCompanyMember(userId) {
  return request(`/api/company/team/members/${encodeURIComponent(userId)}/remove`, { method: "POST" });
}

export function transferCompanyOwnership(userId) {
  return request(`/api/company/team/members/${encodeURIComponent(userId)}/transfer`, { method: "POST" });
}

export function setWorkStatus(status) {
  return request("/api/work_status", {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

// Статус активности кабинета "Рекрутер" (26.08.2026) — отдельный от work_status.
export function setRecruiterActivityStatus(status) {
  return request("/api/recruiter/activity_status", {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export function getQr({ workspace } = {}) {
  return request(`/api/qr${workspace ? `?workspace=${workspace}` : ""}`);
}

// Расширение "Моё CV" (12.08.2026) — см. guro_id_api.py /api/cv/*.
export function setCvField(field, value) {
  return request("/api/cv/field", { method: "POST", body: JSON.stringify({ field, value }) });
}

export function setCvProfession(value) {
  return request("/api/cv/profession", { method: "POST", body: JSON.stringify({ value }) });
}

export function setCvGrade(value) {
  return request("/api/cv/grade", { method: "POST", body: JSON.stringify({ value }) });
}

export function setCvFlag(field, value) {
  return request("/api/cv/flag", { method: "POST", body: JSON.stringify({ field, value }) });
}

export function setCvSalary({ salaryFrom, salaryTo, negotiable }) {
  return request("/api/cv/salary", {
    method: "POST",
    body: JSON.stringify({ salary_from: salaryFrom || null, salary_to: salaryTo || null, negotiable: !!negotiable }),
  });
}

export function addCvExperience(entry) {
  return request("/api/cv/experience", { method: "POST", body: JSON.stringify(entry) });
}

export function deleteCvExperience(id) {
  return request(`/api/cv/experience/${encodeURIComponent(id)}/delete`, { method: "POST" });
}

// Личные сообщения внутри прилы (Фаза 1, 11.08.2026) — см. guro_id_api.py.
export function getMessages() {
  return request("/api/messages");
}

export function getThread(otherUserId) {
  return request(`/api/messages/with/${encodeURIComponent(otherUserId)}`);
}

export function sendMessage({ recipientId, body, viaWorkspace }) {
  return request("/api/messages", {
    method: "POST",
    body: JSON.stringify({ recipient_id: recipientId, body, via_workspace: viaWorkspace || "personal" }),
  });
}

export { ApiError };
