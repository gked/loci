const BASE = "/api";

const TOKEN_HEADER = "X-Loci-Token";
const TOKEN_STORAGE_KEY = "loci_api_token";

// The token proves a request came from this app rather than from some other
// page the user has open. In dev, vite injects it from config.yml; when the
// frontend is hosted somewhere the server cannot reach, the user pastes it in
// once and it lives in localStorage. Sending it as a custom header (rather
// than a query param) is deliberate — custom headers force a CORS preflight,
// so the browser enforces the server's origin allowlist before the request is
// ever sent.
export function getApiToken() {
  try {
    if (typeof localStorage !== "undefined") {
      const stored = localStorage.getItem(TOKEN_STORAGE_KEY);
      if (stored) return stored;
    }
  } catch {
    // localStorage throws in some sandboxed/private-browsing contexts.
  }
  return import.meta.env?.VITE_LOCI_TOKEN || "";
}

export function setApiToken(token) {
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

async function request(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json();
}

function qs(params) {
  const p = Object.entries(params)
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
  return p.length ? "?" + p.join("&") : "";
}

export function getNodes(params = {}) {
  return request(`/nodes${qs(params)}`);
}

export function getNode(uid) {
  return request(`/nodes/${uid}`);
}

export function getNodeNeighbors(uid) {
  return request(`/nodes/${uid}/neighbors`);
}

export function getRecentNodes(params = {}) {
  return request(`/nodes/recent${qs(params)}`);
}

export function searchNodes(q, state) {
  return request(`/search${qs({ q, state })}`);
}

export function getGraph() {
  return request("/graph");
}

export async function openLocalPath(path, fetchImpl = fetch) {
  const url = `${BASE}/open-local${qs({ path })}`;
  const res = await fetchImpl(url, {
    method: "POST",
    headers: { [TOKEN_HEADER]: getApiToken() },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // Keep the HTTP status when the response has no JSON error body.
    }
    throw new Error(detail);
  }
  return res.json();
}
