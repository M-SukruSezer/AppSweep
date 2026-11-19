"""App-specific CSS. Colours come from libadwaita so themes keep working."""

CSS = b"""
.as-badge {
  padding: 1px 7px;
  border-radius: 7px;
  font-weight: 700;
  letter-spacing: 0.03em;
  background: alpha(currentColor, 0.10);
}
.badge-apt      { color: #e06c3b; }
.badge-dnf      { color: #3584e4; }
.badge-pacman   { color: #1793d1; }
.badge-flatpak  { color: #4a90d9; }
.badge-snap     { color: #e95420; }
.badge-appimage { color: #9141ac; }
.badge-pip      { color: #ffd43b; }
.badge-pipx     { color: #c9a227; }
.badge-npm      { color: #cb3837; }
.badge-cargo    { color: #b7410e; }

.as-conf-high   { color: #2ec27e; }
.as-conf-medium { color: #e5a50a; }
.as-conf-low    { color: #9a9996; }

.as-placeholder-icon {
  opacity: 0.45;
}
.as-hero {
  font-size: 2.1em;
  font-weight: 800;
}
textview.monospace, label.monospace {
  font-family: monospace;
}
.toolbar {
  background: alpha(currentColor, 0.04);
  border-top: 1px solid alpha(currentColor, 0.12);
}
"""
