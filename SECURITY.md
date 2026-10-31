# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Report it through GitHub's private vulnerability reporting: open the
repository's **Security** tab and choose **Report a vulnerability**. The report
stays private between you and the maintainer until a fix is released.

Include the Loci version you installed, what you did, and what happened. Do not
paste private vault content; a minimal example that shows the problem is enough.

## What to expect

This is a one-person project. I will acknowledge a report and reply as soon as
I can. I will say whether I can reproduce it. A fix ships in a normal release.

## Supported versions

Only the latest release is supported. Fixes are not backported.

## Scope

Loci runs on your machine against your own files. It is in scope if a crafted
vault file, URL, or MCP request can make Loci read or write outside the vault,
run a command, or send data somewhere you did not ask it to. The local web app
and the HTTP API bind to loopback by default; exposing them on a network is a
deliberate choice and outside the default threat model.

A web page open in your browser can also try to reach the local API. Loci
refuses such requests with three checks:

- **Host header.** Every request is refused unless its Host names this machine
  (`127.0.0.1`, `localhost` or `[::1]`) or an entry in `allowed_hosts` in
  `config.yml`. This stops DNS rebinding. The port is not compared, so an
  `allowed_hosts` entry allows every port on that name. Restart Loci after you
  edit the list.
- **Origin header.** The routes that change files or open them require an Origin
  that is the server itself or is listed in `allowed_origins`.
- **API token.** Those same routes also require the token in the
  `X-Loci-Token` header.

A way to get around any of these checks from a web page is in scope.

By design, the server gives the token to any program on your machine that
requests the home page, because the packaged web app needs it. Another local
program that reads the token is therefore out of scope. I may add stronger
protection later, but I do not promise it.
