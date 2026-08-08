import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

// e2e runs the API on an ephemeral port, so the proxy target is overridable.
const API_TARGET = process.env.LOCI_API_URL || "http://localhost:8765";

// The API requires a token on /api/open-local. Read it out of config.yml so
// `make dev` needs no extra setup — the server writes the token there on first
// start. A hand-set LOCI_API_TOKEN wins, matching the server's own precedence.
function readApiToken() {
  if (process.env.LOCI_API_TOKEN) return process.env.LOCI_API_TOKEN;
  try {
    const config = readFileSync(resolve(projectRoot, "config.yml"), "utf8");
    const match = config.match(/^api_token:\s*(.+)$/m);
    return match ? match[1].trim().replace(/^["']|["']$/g, "") : "";
  } catch {
    // No config.yml yet — the server has not been started for the first time.
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
