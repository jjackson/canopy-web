// The full @canopy/workbench surface, re-exported from the subpath modules.
// Prefer the subpath imports (@canopy/workbench/ui, /shell, /lib) in app code;
// this barrel keeps the convenience top-level entry working.
export * from './lib'
export * from './shell'
export * from './ui'
