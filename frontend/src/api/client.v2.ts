import createClient from "openapi-fetch";
import type { paths } from "./generated";

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function redirectToLogin(): never {
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.href = `/accounts/google/login/?next=${next}`;
  throw new Error("Redirecting to login");
}

// Per-token public-link routes (e.g. /review/<id>?t=…) self-gate on their share
// token, so a 401 from an incidental authenticated call (e.g. /api/me) must NOT
// bounce an anonymous visitor to login. Keep in sync with AuthProvider.
function isPublicLinkRoute(): boolean {
  const p = window.location.pathname;
  return (
    p.startsWith("/review/") ||
    p.startsWith("/walkthrough/") ||
    p.startsWith("/share/")
  );
}

export const apiV2 = createClient<paths>({
  baseUrl: "",
  credentials: "same-origin",
});

// Workspace-scoped apps: when the browser is under a tenant route (/w/:ws/…),
// rewrite their flat /api/<app>/… calls to the canonical tenant path
// /api/w/:ws/<app>/…. The schema documents the flat paths (openapi-fetch is
// typed off them); WorkspaceResolveMiddleware on the server gates membership
// and strips the prefix back to the flat mount. Off a tenant route the flat
// path is used and the server resolves the caller's default workspace.
const WS_SCOPED_API_PREFIXES = [
  "/api/projects",
  "/api/walkthroughs",
  "/api/reviews",
  "/api/shareouts",
  "/api/ddd",
  "/api/timeline",
];

function activeWorkspaceFromUrl(): string | null {
  const m = window.location.pathname.match(/^\/w\/([^/]+)(?:\/|$)/);
  return m ? m[1] : null;
}

apiV2.use({
  async onRequest({ request }) {
    const ws = activeWorkspaceFromUrl();
    if (!ws) return request;
    const url = new URL(request.url);
    if (WS_SCOPED_API_PREFIXES.some((p) => url.pathname.startsWith(p))) {
      url.pathname = `/api/w/${ws}${url.pathname.slice("/api".length)}`;
      return new Request(url, request);
    }
    return request;
  },
});

// CSRF + 401 handling globally via openapi-fetch middleware.
apiV2.use({
  async onRequest({ request }) {
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
      const token = getCsrfToken();
      if (token) request.headers.set("X-CSRFToken", token);
    }
    return request;
  },
  async onResponse({ response }) {
    if (response.status === 401 && !isPublicLinkRoute()) {
      redirectToLogin();
    }
    return response;
  },
});
