// Canonical `cn` now lives in the shared package; re-export so existing
// `@/lib/utils` imports keep resolving to the one implementation.
export { cn } from "canopy-ui/lib"
