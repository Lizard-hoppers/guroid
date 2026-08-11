import { getInitData } from "./telegram.js";

// Тот же контракт, что guro_id_api.py: Authorization: tma <initData>,
// относительные пути — сервис отдаёт и API, и статику с одного origin
// (см. guro_id_api.create_app).

class ApiError extends Error {
  constructor(status, code) {
    super(code);
    this.status = status;
    this.code = code;
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
    throw new ApiError(res.status, body?.error || "UNKNOWN");
  }
  return body;
}

export function getMe() {
  return request("/api/me");
}

// Универсальный поиск (10.08.2026): одно поле q= — бэкенд сам решает,
// точный это юзернейм (mode=profile) или описание (mode=list,
// платный directory-поиск), см. handle_search в guro_id_api.py. top=true
// (Фаза 2) — сортировка "ТОП рейтинга" для описания (на точный юзернейм
// не влияет, там всегда один профиль).
export function search(query, { top } = {}) {
  return request(`/api/search?q=${encodeURIComponent(query)}${top ? "&top=1" : ""}`);
}

export function searchByUserId(userId) {
  return request(`/api/search?user_id=${encodeURIComponent(userId)}`);
}

export function createPartnership({
  confirmerUsername, vertical, geo, offer, amountReceived, amountPaid, review, amountVisible,
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
    }),
  });
}

// Browse по вертикали (Фаза 2, 11.08.2026) — альтернатива текстовому
// поиску для тех, кто не знает точного юзернейма. top=true — сортировка
// "ТОП рейтинга" вместо силы совпадения (тот же флаг, что у search()).
export function browseVertical(vertical, { top } = {}) {
  return request(`/api/search?vertical=${encodeURIComponent(vertical)}${top ? "&top=1" : ""}`);
}

export function getInviteLink() {
  return request("/api/invite_link");
}

export function getPlans() {
  return request("/api/plans");
}

export function subscribe(plan) {
  return request("/api/subscribe", { method: "POST", body: JSON.stringify({ plan }) });
}

export function subscribeCrypto(plan) {
  return request("/api/subscribe/crypto", { method: "POST", body: JSON.stringify({ plan }) });
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

export function setWorkStatus(status) {
  return request("/api/work_status", {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export function getQr() {
  return request("/api/qr");
}

// Личные сообщения внутри прилы (Фаза 1, 11.08.2026) — см. guro_id_api.py.
export function getMessages() {
  return request("/api/messages");
}

export function getThread(otherUserId) {
  return request(`/api/messages/with/${encodeURIComponent(otherUserId)}`);
}

export function sendMessage({ recipientId, body }) {
  return request("/api/messages", {
    method: "POST",
    body: JSON.stringify({ recipient_id: recipientId, body }),
  });
}

export { ApiError };
