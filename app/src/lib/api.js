const BASE = "/api";

const TOKEN_HEADER = "X-Loci-Token";
const TOKEN_STORAGE_KEY = "loci_api_token";

// The token proves a request came from this app rather than from some other
// page the user has open. Sending it as a custom header (rather than a query
// param) is deliberate — custom headers force a CORS preflight, so the browser
// enforces the server's origin allowlist before the request is ever sent.
//
// Three sources, in order of how much they can be trusted to be current:
//
//   1. A meta tag, when the API served this page itself (an installed Loci,
//      where the bundle ships inside the wheel). The server stamps in its own
//      token as it serves index.html, so this is right by construction — and
//      it is why the token is not baked into the bundle at build time, where
//      it would be whatever the machine that ran the build happened to have.
//   2. localStorage, for a frontend hosted somewhere the server cannot reach.
//      The user pastes the token in once.
//   3. The build-time value vite injects from config.yml, which is what makes
//      `make dev` work with no setup.
export function getApiToken() {
  try {
    const meta = document?.querySelector('meta[name="loci-token"]');
    const injected = meta?.getAttribute("content");
    if (injected) return injected;
  } catch {
    // No DOM (unit tests run this module under node).
  }

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

export function getHealth() {
  return request("/health");
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
