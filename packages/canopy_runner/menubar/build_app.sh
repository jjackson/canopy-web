#!/usr/bin/env bash
# Build "Canopy Runner.app" — a menu-bar control surface for the runner daemon.
#
# Produces ~/Applications/Canopy Runner.app (LSUIElement: menu-bar only, no dock
# icon), Spotlight-launchable like "Emdash CDP". The app runs a dedicated venv so
# rumps/pyobjc never touch system python, and points PYTHONPATH at the runner
# package so it shares one source of truth with the daemon.
#
# Re-run any time to pick up menubar.py changes (the .app is a thin launcher — no
# rebuild needed for code changes, only if you move paths). Idempotent.
set -euo pipefail

PKG_DIR="${CANOPY_RUNNER_PKG:-$HOME/emdash-projects/canopy-web/packages/canopy_runner}"
VENV="${CANOPY_RUNNER_VENV:-$HOME/.canopy/menubar-venv}"
APP="${CANOPY_RUNNER_APP:-$HOME/Applications/Canopy Runner.app}"

[ -d "$PKG_DIR/canopy_runner" ] || { echo "ERROR: runner package not at $PKG_DIR" >&2; exit 1; }

echo "==> venv + rumps ($VENV)"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip >/dev/null
"$VENV/bin/pip" install -q rumps >/dev/null

echo "==> app bundle ($APP)"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Canopy Runner</string>
  <key>CFBundleDisplayName</key><string>Canopy Runner</string>
  <key>CFBundleIdentifier</key><string>com.canopy.runner.menubar</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>CanopyRunner</string>
  <!-- menu-bar-only agent: no dock icon, no app-switcher entry -->
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

echo "APPL????" > "$APP/Contents/PkgInfo"

cat > "$APP/Contents/MacOS/CanopyRunner" <<LAUNCH
#!/usr/bin/env bash
# Single-instance guard: if a menu-bar app is already running, just exit (a second
# launch from Spotlight should be a no-op, not a duplicate icon).
if pgrep -f "canopy_runner.menubar" | grep -qv \$\$ ; then exit 0; fi
export PYTHONPATH="$PKG_DIR"
exec "$VENV/bin/python" -m canopy_runner.menubar
LAUNCH
chmod +x "$APP/Contents/MacOS/CanopyRunner"

# Nudge Launch Services / Spotlight so it shows up immediately.
touch "$APP"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
  -f "$APP" 2>/dev/null || true

echo "==> done. Launch from Spotlight: 'Canopy Runner'  (or: open \"$APP\")"
