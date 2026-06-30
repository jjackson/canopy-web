/**
 * canopy-ui/tokens — the shared token contract.
 *
 * The substance of the token system is CSS, imported directly:
 *   import "canopy-ui/tokens/preset.css"   // Tailwind v4 @theme name → var mapping
 *   import "canopy-ui/tokens/tokens.css"    // default :root / .dark VALUES
 *
 * This module exposes the canonical list of token names so tooling/tests can
 * assert an app's palette covers the contract.
 */
export const TOKEN_NAMES = [
  'background',
  'foreground',
  'card',
  'card-foreground',
  'popover',
  'popover-foreground',
  'primary',
  'primary-foreground',
  'secondary',
  'secondary-foreground',
  'accent',
  'accent-foreground',
  'muted',
  'muted-foreground',
  'foreground-secondary',
  'foreground-subtle',
  'border',
  'input',
  'ring',
  'destructive',
  'destructive-foreground',
  'success',
  'success-foreground',
  'warning',
  'warning-foreground',
  'info',
  'info-foreground',
  'special',
  'special-foreground',
  'radius',
] as const

export type TokenName = (typeof TOKEN_NAMES)[number]
