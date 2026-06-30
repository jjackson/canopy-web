import createClient from "openapi-fetch";
import type { paths } from "./generated";

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function redirectToLogin(): never {
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  // Prefix-aware: BASE_URL is "/" at root and "/canopy/" as a labs tenant, so
  // this stays under the deployment instead of bouncing to a sibling tenant.
  window.location.href = `${import.meta.env.BASE_URL}accounts/google/login/?next=${next}`;
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
    p.startsWith("/review/") || p.startsWith("/w/") || p.startsWith("/share/")
  );
}

// Under a path prefix (e.g. /canopy), API calls must carry it too. BASE_URL is
// "/" at root (→ "") and "/canopy/" as a labs tenant (→ "/canopy").
const API_BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

export const apiV2 = createClient<paths>({
  baseUrl: API_BASE,
  credentials: "same-origin",
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
