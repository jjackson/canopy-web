// The full canopy-ui surface, re-exported from the subpath modules.
// Prefer the subpath imports (canopy-ui/ui, /shell, /lib) in app code;
// this barrel keeps the convenience top-level entry working.
export * from './lib'
export * from './shell'
export * from './ui'
