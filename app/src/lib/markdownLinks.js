// Classifies hrefs found in node bodies so the renderer knows whether to open
// a link in the browser, navigate in place, or hand it to the OS.

// Root directories a real filesystem path can start with. A bare leading slash
// is ambiguous — "/Users/me/spec.pdf" is a file but "/monogram.svg" and
// "/api/health" are web paths served by this same origin — so only these
// prefixes count as local files. Anything outside them can still be opened by
// writing it as an explicit file:// URI.
const FS_ROOTS = [
  "Users",
  "home",
  "root",
  "Applications",
  "Volumes",
  "System",
  "Library",
  "private",
  "mnt",
  "media",
  "srv",
  "opt",
  "usr",
  "tmp",
  "var",
  "etc",
];

const LOCAL_FILE_URI = /^file:\/\/(?:localhost)?\//i;
const WINDOWS_DRIVE = /^[A-Za-z]:[\\/]/;
const HOME_RELATIVE = /^~[\\/]/;
const FS_ROOT_PATH = new RegExp(`^/(?:${FS_ROOTS.join("|")})(?:/|$)`);

export function isExternalUrl(href = "") {
  return /^https?:\/\//i.test(href);
}

export function isLocalFileHref(href = "") {
  return (
    LOCAL_FILE_URI.test(href) ||
    WINDOWS_DRIVE.test(href) ||
    HOME_RELATIVE.test(href) ||
    FS_ROOT_PATH.test(href)
  );
}
