import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { resolve } from "node:path";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// e2e runs the API on an ephemeral port, so the proxy target is overridable.
const API_TARGET = process.env.LOCI_API_URL || "http://localhost:8765";

// Python's Path.expanduser(): config_path() applies it to both env vars, so a
// value that reaches us with a literal leading ~ (quoted in a shell rc, set in
// a .env, handed over by a launcher) must resolve the same way here. Without
// it readFileSync throws, the catch below swallows it, and the UI runs with an
// empty token and no diagnostic.
function expandHome(value) {
  const home = process.env.HOME || homedir();
  if (value === "~") return home;
  if (value.startsWith("~/")) return resolve(home, value.slice(2));
  return value;
}

// Mirrors config_path() in server/tools/vault_init.py. Config lives outside the
// checkout so a uvx install — which has no checkout — keeps its settings.
function configPath() {
  if (process.env.LOCI_CONFIG) return expandHome(process.env.LOCI_CONFIG);
  const base = process.env.XDG_CONFIG_HOME
    ? expandHome(process.env.XDG_CONFIG_HOME)
    : resolve(process.env.HOME || homedir(), ".config");
  return resolve(base, "loci", "config.yml");
}

// The API requires a token on /api/open-local. Read it out of the config file
// so `make dev` needs no extra setup — the Makefile writes the token there.
// A hand-set LOCI_API_TOKEN wins, matching the server's own precedence.
function readApiToken() {
  if (process.env.LOCI_API_TOKEN) return process.env.LOCI_API_TOKEN;
  try {
    const config = readFileSync(configPath(), "utf8");
    const match = config.match(/^api_token:\s*(.+)$/m);
    return match ? match[1].trim().replace(/^["']|["']$/g, "") : "";
  } catch {
    // No config file yet — the server has not been started for the first time.
    return "";
  }
}

// Shared by `serve` and `preview` so the e2e suite exercises the same token
// forwarding the dev server uses.
const apiProxy = {
  target: API_TARGET,
  // The server writes the token to config.yml on its first start, which
  // can land after vite has already read the file. Resolving per request
  // means a first `make dev` works without restarting the UI.
  configure: (proxy) => {
    let cached = "";
    proxy.on("proxyReq", (proxyReq) => {
      if (proxyReq.getHeader("X-Loci-Token")) return;
      cached = cached || readApiToken();
      if (cached) proxyReq.setHeader("X-Loci-Token", cached);
    });
  },
};

export default defineConfig({
  plugins: [react()],
  define: {
    "import.meta.env.VITE_LOCI_TOKEN": JSON.stringify(readApiToken()),
  },
  server: {
    port: 5173,
    proxy: {
      "/api": apiProxy,
    },
  },
  // `vite preview` serves the built bundle — used by the e2e suite so tests
  // exercise the production build rather than the dev server.
  preview: {
    port: 4173,
    proxy: {
      "/api": apiProxy,
    },
  },
});
