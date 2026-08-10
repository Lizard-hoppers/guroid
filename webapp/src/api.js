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

export function search(username) {
  return request(`/api/search?username=${encodeURIComponent(username)}`);
}

export function searchByUserId(userId) {
  return request(`/api/search?user_id=${encodeURIComponent(userId)}`);
}

export function directorySearch(query) {
  return request(`/api/directory?q=${encodeURIComponent(query)}`);
}

export function createPartnership({ confirmerUsername, vertical, geo }) {
  return request("/api/partnerships", {
    method: "POST",
    body: JSON.stringify({
      confirmer_username: confirmerUsername,
      vertical: vertical || null,
      geo: geo || null,
    }),
  });
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

export { ApiError };
