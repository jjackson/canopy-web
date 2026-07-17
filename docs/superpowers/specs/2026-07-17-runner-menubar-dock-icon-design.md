# Canopy Runner menu-bar app — Dock icon + shared window

**Date:** 2026-07-17
**Status:** Approved, not yet implemented
**Component:** `packages/canopy-runner-menubar` (native Swift/AppKit app)

## Problem

The Canopy Runner menu-bar app is `LSUIElement` / `.accessory` — menu-bar-only,
no Dock icon. On a notched MacBook the menu-bar tree icon gets clipped behind the
notch and becomes invisible, so the app looks like it isn't running (it is). The
user has been bitten by this repeatedly, and launching from Spotlight appears to
do nothing because a single-instance menu-bar-only app has no window to show.

**Ask:** give the app a Dock icon as an always-visible "it's running" signal, and
make clicking the Dock icon open the same `/supervisor` WKWebView UI the menu-bar
popover shows.

## Decisions (from brainstorming)

- **One shared window, both icons open it.** Replace the popover with a single
  resizable `NSWindow`; the menu-bar tree icon and the Dock icon both show/focus
  that one window. "Open the same window," literally — one surface, two ways in.
- **Standard `.regular` app.** Dock icon + Cmd-Tab + an app menu when focused.
  No fragile Cmd-Tab suppression.

## Changes

Two files in `packages/canopy-runner-menubar/`.

### `build.sh` — Info.plist

`build.sh:42` emits `<key>LSUIElement</key><true/>`. Change to `<false/>` (or
remove the key). This is the plist half of "no Dock icon"; without flipping it,
the `.regular` policy in code is fought by the plist.

### `Sources/main.swift` — `Controller`

1. **Activation policy.** `main.swift:341` `app.setActivationPolicy(.accessory)`
   → `.regular`. The Dock icon uses the already-bundled `AppIcon.icns`; it shows
   whenever the app runs.

2. **Popover → shared window.** Replace the `NSPopover` (`popover`, `buildPopover`,
   `togglePopover`) with a single lazily-built resizable `NSWindow` hosting the
   *same* `WKWebView` (`web`). The auth + load logic (`authenticateThenLoad`,
   `loadSupervisor`, the PAT-mint cookie injection, the `.default()` data store)
   is unchanged — only its container changes from popover to window.
   - Window: titled "Canopy Runner", `[.titled, .closable, .miniaturizable,
     .resizable]`, default content size 420×640 (the current popover size) but
     resizable, centered on first show.
   - `showWindow()`: if `authed` reload `/supervisor`, else `authenticateThenLoad`;
     then `NSApp.activate(ignoringOtherApps: true)` + `window.makeKeyAndOrderFront`.
     Matches today's "always open on the supervisor home" behavior.

3. **Both icons open the one window.**
   - Menu-bar **left-click** (`statusClicked`, the non-right-click branch): call
     `showWindow()` instead of `togglePopover()`. **Right-click** → the local
     controls menu, unchanged.
   - **Dock-icon click**: implement `applicationShouldHandleReopen(_ sender:
     hasVisibleWindows:) -> Bool` on the delegate → `showWindow()`; return `true`.
     This is the AppKit hook for a Dock-icon click (and re-open when no windows
     are visible).

4. **Closing the window must not quit the app.** It remains a background runner
   controller. Add `applicationShouldTerminateAfterLastWindowClosed(_:) -> Bool`
   returning `false`. Closing the window hides it; the menu-bar tree icon, the
   5-second status poll, the right-click menu, and the daemon-control all keep
   running. Quit stays available via the right-click "Quit Canopy Runner" item
   (`main.swift:337`) and Cmd-Q while focused.

## Preserved (do not touch)

- The 5-second `Timer` → `rebuild()` that tints the menu-bar tree by status.
- The right-click local-controls menu (`buildMenu`, `currentState`).
- Shared-PAT auth (mint session from `~/.canopy/runner.json`, inject cookie).
- Single-instance behavior (`build.sh:59` — the app reactivates rather than
  spawning a duplicate).
- The tree icon assets; the Dock icon is the separate `AppIcon.icns`.

## Build & deploy

`build.sh` compiles the Swift and assembles `~/Applications/Canopy Runner.app`.
The app **auto-starts on login** (commit #272) and one instance is currently
running. Rollout:

1. `./build.sh` — rebuild the `.app` (needs the Swift toolchain / Xcode CLT).
2. Quit the running instance, replace the app bundle, relaunch.
3. Verify (below).

## Testing

Compiled Swift app, no unit harness — verification is driving the real app after
rebuild + relaunch:

1. **Dock icon appears** while the app runs (the "it's running" signal).
2. **Dock click opens the window** on `/supervisor`, authenticated.
3. **Menu-bar tree click opens the *same* window** (not a second one).
4. **Closing the window leaves the app running** — Dock icon stays, menu-bar tree
   stays, status still polls.
5. **Right-click menu** (local controls, Quit) still works; Quit terminates.
6. **Relaunch-on-login** works with the rebuilt bundle (single instance, no
   duplicate).

## Non-goals

- Persisting window size/position across launches (center-on-open is enough).
- Cmd-Tab suppression.
- Any change to the daemon, the schedule system, or the web `/supervisor` surface
  (the app just hosts the existing deployed React UI).
