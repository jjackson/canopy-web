/**
 * The video deep-link contract: a `#t=<seconds>` fragment on a `/w/<id>` viewer
 * URL means "start the video at that offset". Canopy's DDD product-findings
 * review links each finding cluster to `<clip_url>#t=<seconds>` (the start of
 * the scene the finding is about, from the recorder's per-scene timings), so a
 * reviewer lands on the exact moment instead of scrubbing.
 *
 * `#t=` (a fragment) deliberately does NOT collide with the `?t=<share_token>`
 * query param — fragment and query are separate URL parts, and the fragment
 * mirrors the Media Fragments URI syntax browsers already use on media URLs.
 */

/** A `#t=<seconds>` fragment matcher. Accepts an optional leading `#` and decimals. */
const TIME_HASH = /^#?t=(\d+(?:\.\d+)?)$/;

/**
 * Parse a raw `location.hash` into a start offset in seconds, or `null` when
 * it isn't a time deep-link. Only plain non-negative seconds are accepted —
 * anything else (scene anchors, junk, negative/NaN) yields `null` so callers
 * leave playback untouched.
 */
export function timeHashSeconds(rawHash: string | null | undefined): number | null {
  const m = (rawHash ?? "").match(TIME_HASH);
  if (!m) return null;
  const seconds = Number.parseFloat(m[1]);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

/**
 * Append a media-fragment start time to a media URL. The URL is assumed
 * fragment-free (content URLs are); browsers that honor Media Fragments seek
 * natively, and the viewer's `loadedmetadata` fallback covers the rest.
 */
export function withTimeFragment(url: string, seconds: number): string {
  return `${url}#t=${seconds}`;
}
