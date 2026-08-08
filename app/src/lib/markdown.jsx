// Shared react-markdown configuration.
//
// Links in node bodies fall into three buckets. Web URLs open in a new tab.
// Relative and same-page (#anchor) links keep their default in-place behavior.
// Paths that name a file on this machine are handed to the API, which asks the
// operating system to open them — browsers cannot navigate to a local path
// from an http(s) page, so a plain <a href> would do nothing.

import { useState } from "react";
import { defaultUrlTransform } from "react-markdown";
import { openLocalPath } from "./api.js";
import { isExternalUrl, isLocalFileHref } from "./markdownLinks.js";

export function markdownUrlTransform(url) {
  return isLocalFileHref(url) ? url : defaultUrlTransform(url);
}

export function LocalFileLink({ href, children, ...props }) {
  const [error, setError] = useState(null);

  // Middle-click fires auxclick rather than click. Without handling it the
  // browser would resolve the filesystem path against the app's origin and
  // open a broken tab, so both events route through the same handler.
  const open = (event) => {
    event.preventDefault();
    setError(null);
    openLocalPath(href).catch((cause) => {
      setError(cause.message || "Could not open this file");
    });
  };

  return (
    <>
      <a
        href={href}
        onClick={open}
        onAuxClick={open}
        data-open-error={error ? "true" : undefined}
        title={error ? `${error} — ${href}` : href}
        {...props}
      >
        {children}
      </a>
      {error && (
        <span
          role="status"
          style={{
            marginLeft: 6,
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--vault-danger)",
          }}
        >
          ⚠ {error}
        </span>
      )}
    </>
  );
}

export const mdComponents = {
  a: ({ node, href, children, ...props }) => {
    if (isLocalFileHref(href)) {
      return <LocalFileLink href={href} {...props}>{children}</LocalFileLink>;
    }
    return isExternalUrl(href) ? (
      <a href={href} target="_blank" rel="noreferrer noopener" {...props}>
        {children}
      </a>
    ) : (
      <a href={href} {...props}>
        {children}
      </a>
    );
  },
};
