// The full @marshellis/workbench surface, re-exported from the subpath modules.
// Prefer the subpath imports (@marshellis/workbench/ui, /shell, /lib) in app code;
// this barrel keeps the convenience top-level entry working.
export * from './lib'
export * from './shell'
export * from './ui'
