// Shared react-markdown configuration.
//
// External links in node bodies open in a new tab rather than navigating the
// SPA away. Relative and same-page (#anchor) links keep their default in-place
// behavior so intra-document navigation doesn't spawn a duplicate app tab.
// URL sanitization is left at react-markdown's safe default (http, https,
// mailto, tel, relative/same-page) — file:// and other local-path schemes are
// intentionally NOT supported, since browsers block navigation to them from an
// http(s) page anyway.

export const mdComponents = {
  a: ({ node, href, children, ...props }) => {
    const external = /^https?:\/\//i.test(href || "");
    return external ? (
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
