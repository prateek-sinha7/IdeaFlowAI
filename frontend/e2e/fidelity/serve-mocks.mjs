#!/usr/bin/env node
/**
 * serve-mocks.mjs — a tiny static HTTP server for the VelocityAI target mocks.
 *
 * The `.dc.html` mocks load `./support.js` (the DC runtime) and Google-fonts
 * stylesheets. A `file://` origin cannot resolve the relative `support.js`
 * fetch nor apply the cross-origin font CSS, so the mocks must render over a
 * REAL HTTP origin — that is the sole job of this server.
 *
 * No dependency: Node's built-in `http` + `fs` only (plan 39-07 scope fence —
 * the harness adds NO new npm package).
 *
 * Usage:
 *   node e2e/fidelity/serve-mocks.mjs                 # serves on :4599
 *   MOCK_PORT=5000 node e2e/fidelity/serve-mocks.mjs  # custom port
 *   MOCK_DIR=/path/to/mocks node e2e/fidelity/serve-mocks.mjs
 *
 * Programmatic (used by capture-mocks.mjs):
 *   import { startMockServer } from "./serve-mocks.mjs";
 *   const { origin, close } = await startMockServer();
 */
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize, sep } from "node:path";

/** The directory holding the authored `.dc.html` mocks + `support.js`. */
export const MOCK_DIR =
  process.env.MOCK_DIR || "/Users/1000060523/Documents/Work/VelocityAI-New-UI";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

/**
 * Start the static server. Resolves once it is listening.
 * @returns {Promise<{ origin: string, port: number, close: () => Promise<void> }>}
 */
export function startMockServer({ port = Number(process.env.MOCK_PORT) || 4599, dir = MOCK_DIR } = {}) {
  const root = normalize(dir);
  const server = createServer(async (req, res) => {
    try {
      // Decode + strip query; default to the settled mock at "/".
      let rel = decodeURIComponent((req.url || "/").split("?")[0]);
      if (rel === "/" || rel === "") rel = "/Hexaware Run.dc.html";
      // Path-traversal guard: the resolved path must stay under root.
      const abs = normalize(join(root, rel));
      if (abs !== root && !abs.startsWith(root + sep)) {
        res.writeHead(403).end("forbidden");
        return;
      }
      const info = await stat(abs).catch(() => null);
      if (!info || !info.isFile()) {
        res.writeHead(404).end("not found");
        return;
      }
      const body = await readFile(abs);
      res.writeHead(200, {
        "content-type": MIME[extname(abs).toLowerCase()] || "application/octet-stream",
        "cache-control": "no-store",
      });
      res.end(body);
    } catch (err) {
      res.writeHead(500).end(String(err));
    }
  });

  return new Promise((resolve) => {
    server.listen(port, "127.0.0.1", () => {
      const origin = `http://127.0.0.1:${port}`;
      resolve({
        origin,
        port,
        close: () => new Promise((r) => server.close(() => r())),
      });
    });
  });
}

// Run standalone when invoked directly (`node serve-mocks.mjs`).
if (import.meta.url === `file://${process.argv[1]}`) {
  startMockServer().then(({ origin }) => {
    console.log(`[serve-mocks] serving ${MOCK_DIR}`);
    console.log(`[serve-mocks] listening on ${origin}`);
    console.log(`[serve-mocks]   ${origin}/Hexaware%20Run.dc.html`);
    console.log(`[serve-mocks]   ${origin}/Hexaware%20Run%20-%20Live.dc.html`);
    console.log(`[serve-mocks]   ${origin}/Hexaware%20Run%20-%20Failed.dc.html`);
    console.log("[serve-mocks] Ctrl-C to stop.");
  });
}
