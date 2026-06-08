/**
 * The DDD deep-link contract: a `#scene-<N>` fragment on a run/deck URL means
 * "open the walkthrough deck on scene N". Surfaced judge findings and reviews
 * link to `<DECK_URL>#scene-N`, and the run page (`/ddd/<slug>/<runId>#scene-N`)
 * forwards that fragment into the embedded slides iframe. The deck's own JS
 * (canopy `generate_presentation.py`) resolves the anchor to a slide.
 *
 * These helpers keep the fragment shape in one place so the run page and the
 * standalone `/w/:id` viewer forward exactly the anchors the deck understands —
 * never an arbitrary hash (e.g. the run page's own section anchors).
 */

/** A `#scene-<N>` fragment matcher. Accepts an optional leading `#`. */
const SCENE_HASH = /^#?(scene-\d+)$/;

/**
 * Normalize a raw `location.hash` to a canonical `#scene-N` fragment, or `''`
 * if it isn't a scene deep-link. Only scene anchors are forwarded; anything
 * else (empty, a section id, junk) yields `''` so callers pass through unchanged.
 */
export function sceneHashFragment(rawHash: string | null | undefined): string {
  const m = (rawHash ?? "").match(SCENE_HASH);
  return m ? `#${m[1]}` : "";
}

/**
 * Append a scene fragment to a content URL. No-op when there's no scene hash.
 * The URL is assumed fragment-free (deck content/viewer URLs are), so we just
 * concatenate rather than rewrite an existing fragment.
 */
export function withSceneHash(url: string, rawHash: string | null | undefined): string {
  const frag = sceneHashFragment(rawHash);
  return frag ? `${url}${frag}` : url;
}
