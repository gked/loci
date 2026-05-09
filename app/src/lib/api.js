const BASE = "/api";

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
