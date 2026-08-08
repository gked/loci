import assert from "node:assert/strict";
import test from "node:test";

import { openLocalPath } from "./api.js";
import { isExternalUrl, isLocalFileHref } from "./markdownLinks.js";

test("recognizes web URLs that should open in the browser", () => {
  assert.equal(isExternalUrl("https://example.com/docs"), true);
  assert.equal(isExternalUrl("HTTP://example.com"), true);
  assert.equal(isExternalUrl("file:///Users/example/note.md"), false);
});

test("recognizes absolute paths and local file URIs", () => {
  assert.equal(isLocalFileHref("/Users/example/My%20File.pdf"), true);
  assert.equal(isLocalFileHref("/home/example/notes.md"), true);
  assert.equal(isLocalFileHref("/Volumes/Archive/scan.tiff"), true);
  assert.equal(isLocalFileHref("file:///Users/example/My%20File.pdf"), true);
  assert.equal(isLocalFileHref("file://localhost/Users/example/note.md"), true);
  assert.equal(isLocalFileHref("C:\\Users\\example\\note.md"), true);
  assert.equal(isLocalFileHref("~/notes/spec.pdf"), true);
  assert.equal(isLocalFileHref("notes/relative.md"), false);
  assert.equal(isLocalFileHref("https://example.com/file.pdf"), false);
});

test("leaves root-relative web paths alone", () => {
  // These are served by the app's own origin — treating them as filesystem
  // paths would swallow the click and try to open them with the OS.
  assert.equal(isLocalFileHref("/monogram.svg"), false);
  assert.equal(isLocalFileHref("/api/health"), false);
  assert.equal(isLocalFileHref("/graph"), false);
  assert.equal(isLocalFileHref("/assets/index-a1b2c3.js"), false);
  assert.equal(isLocalFileHref("#section-two"), false);
});

test("does not confuse a root directory with a longer name that shares its prefix", () => {
  assert.equal(isLocalFileHref("/Users"), true);
  assert.equal(isLocalFileHref("/usersettings"), false);
  assert.equal(isLocalFileHref("/vars"), false);
});

test("requests the local system handler for a file path", async () => {
  const calls = [];
  const fetchImpl = async (...args) => {
    calls.push(args);
    return { ok: true, json: async () => ({ opened: "/Users/example/My File.pdf" }) };
  };

  await openLocalPath("/Users/example/My File.pdf", fetchImpl);

  assert.equal(calls.length, 1);
  const [url, options] = calls[0];
  assert.equal(url, "/api/open-local?path=%2FUsers%2Fexample%2FMy%20File.pdf");
  assert.equal(options.method, "POST");
  // Sent as a custom header so the browser preflights cross-origin attempts.
  assert.ok("X-Loci-Token" in options.headers);
});

test("surfaces the server's error detail when opening fails", async () => {
  const fetchImpl = async () => ({
    ok: false,
    status: 403,
    statusText: "Forbidden",
    json: async () => ({ detail: "Missing or invalid API token" }),
  });

  await assert.rejects(
    () => openLocalPath("/Users/example/note.md", fetchImpl),
    { message: "Missing or invalid API token" },
  );
});
