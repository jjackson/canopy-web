import createClient from "openapi-fetch";
import type { paths } from "./generated";
import { API_BASE, getCsrfToken } from "./base";

function redirectToLogin(): never {
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  // Prefix-aware: BASE_URL is "/" at root and "/canopy/" as a labs tenant, so
  // this stays under the deployment instead of bouncing to a sibling tenant.
  window.location.href = `${import.meta.env.BASE_URL.replace(/\/$/, '')}/accounts/google/login/?next=${next}`;
  throw new Error("Redirecting to login");
}

// Per-token public-link routes (e.g. /review/<id>?t=…) self-gate on their share
// token, so a 401 from an incidental authenticated call (e.g. /api/me) must NOT
// bounce an anonymous visitor to login. Keep in sync with AuthProvider.
function isPublicLinkRoute(): boolean {
  // Strip the deployment prefix (/canopy) before matching the app route.
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  const p = window.location.pathname.slice(base.length);
  return (
    p.startsWith("/review/") ||
    p.startsWith("/walkthrough/") ||
    p.startsWith("/share/")
  );
}

// Under a path prefix (e.g. /canopy), API calls must carry it too. API_BASE is
// "" at root and "/canopy" as a labs tenant (see ./base).
export const apiV2 = createClient<paths>({
  baseUrl: API_BASE,
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
  // Strip the deployment prefix (/canopy) before reading the app route.
  const p = window.location.pathname.slice(API_BASE.length);
  const m = p.match(/^\/w\/([^/]+)(?:\/|$)/);
  return m ? m[1] : null;
}

apiV2.use({
  async onRequest({ request }) {
    const ws = activeWorkspaceFromUrl();
    if (!ws) return request;
    const url = new URL(request.url);
    // openapi-fetch already prefixed API_BASE; match + rewrite against the
    // deployment-relative path so /canopy/api/projects → /canopy/api/w/:ws/projects.
    const rel = url.pathname.slice(API_BASE.length);
    if (WS_SCOPED_API_PREFIXES.some((p) => rel.startsWith(p))) {
      url.pathname = `${API_BASE}/api/w/${ws}${rel.slice("/api".length)}`;
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
