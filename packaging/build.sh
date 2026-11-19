#!/bin/sh
# Build the release artefacts into dist/.
#
#     packaging/build.sh            everything available on this machine
#     packaging/build.sh tar        source tarball only
#     packaging/build.sh deb        Debian package only
#     packaging/build.sh rpm        RPM package only
#
# The .deb and the .rpm are both laid out by packaging/install-tree.sh, so
# the two packages always install the same files in the same places.
set -eu

cd "$(dirname "$0")/.."
ROOT=$(pwd)
DIST="$ROOT/dist"
NAME=appsweep
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' appsweep/__init__.py)
MAINTAINER="Muhammed Şükrü SEZER <M-SukruSezer@users.noreply.github.com>"

[ -n "$VERSION" ] || { echo "could not read the version" >&2; exit 1; }
WHAT=${1:-all}
mkdir -p "$DIST"
echo "AppSweep $VERSION"

# ----------------------------------------------------------------- tar.gz
build_tar() {
    out="$DIST/$NAME-$VERSION.tar.gz"
    staging=$(mktemp -d)
    trap 'rm -rf "$staging"' EXIT
    mkdir -p "$staging/$NAME-$VERSION"
    # Only what belongs in a source release: no VCS data, no caches, no
    # build output.
    tar -c \
        --exclude='.git' --exclude='dist' --exclude='__pycache__' \
        --exclude='*.pyc' --exclude='.oil-ui' \
        appsweep bin data docs packaging po tests \
        install.sh LICENSE README.md README.tr.md requirements.txt \
        .gitignore \
      | tar -x -C "$staging/$NAME-$VERSION"
    tar -czf "$out" -C "$staging" "$NAME-$VERSION"
    rm -rf "$staging"
    trap - EXIT
    echo "  $(basename "$out")  $(du -h "$out" | cut -f1)"
}

# -------------------------------------------------------------------- deb
build_deb() {
    command -v dpkg-deb >/dev/null 2>&1 || { echo "  dpkg-deb missing, skipping .deb"; return; }
    pkgroot=$(mktemp -d)
    trap 'rm -rf "$pkgroot"' EXIT
    sh packaging/install-tree.sh "$pkgroot" /usr

    mkdir -p "$pkgroot/DEBIAN"
    installed_kb=$(du -s --exclude=DEBIAN "$pkgroot" | cut -f1)
    cat > "$pkgroot/DEBIAN/control" <<CONTROL
Package: $NAME
Version: $VERSION
Section: admin
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0 (>= 4.10), gir1.2-adw-1 (>= 1.4)
Recommends: policykit-1 | polkitd, gettext-base
Installed-Size: $installed_kb
Maintainer: $MAINTAINER
Homepage: https://github.com/M-SukruSezer/AppSweep
Description: one uninstaller for every way Linux installs software
 AppSweep lists everything installed on the machine, whichever package
 manager put it there, with the space it occupies; removes any of it in
 one step; and then finds the configuration, caches and data that
 uninstalling leaves behind.
 .
 It reads apt/dpkg, dnf/rpm, pacman, Flatpak, Snap, AppImage, pip, pipx,
 npm and cargo. Every removal is shown as the exact commands it will run
 before anything happens, protected paths are refused outright, and
 deleted leftovers go to the trash rather than being destroyed.
 .
 Interface in English and Turkish.
CONTROL

    cat > "$pkgroot/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
fi
POSTINST
    cp "$pkgroot/DEBIAN/postinst" "$pkgroot/DEBIAN/postrm"
    sed -i 's/= "configure"/= "remove"/' "$pkgroot/DEBIAN/postrm"
    chmod 755 "$pkgroot/DEBIAN/postinst" "$pkgroot/DEBIAN/postrm"

    out="$DIST/${NAME}_${VERSION}_all.deb"
    if command -v fakeroot >/dev/null 2>&1; then
        fakeroot dpkg-deb --build -Zxz "$pkgroot" "$out" >/dev/null
    else
        dpkg-deb --build -Zxz "$pkgroot" "$out" >/dev/null
    fi
    rm -rf "$pkgroot"
    trap - EXIT
    echo "  $(basename "$out")  $(du -h "$out" | cut -f1)"
}

# -------------------------------------------------------------------- rpm
build_rpm() {
    command -v rpmbuild >/dev/null 2>&1 || { echo "  rpmbuild missing, skipping .rpm"; return; }
    [ -f "$DIST/$NAME-$VERSION.tar.gz" ] || build_tar
    top=$(mktemp -d)
    trap 'rm -rf "$top"' EXIT
    mkdir -p "$top/SOURCES" "$top/SPECS"
    cp "$DIST/$NAME-$VERSION.tar.gz" "$top/SOURCES/"
    cp packaging/appsweep.spec "$top/SPECS/"
    rpmbuild --define "_topdir $top" -bb "$top/SPECS/appsweep.spec" \
        >"$top/build.log" 2>&1 || {
            echo "  rpmbuild failed; last lines:" >&2
            tail -25 "$top/build.log" >&2
            rm -rf "$top"; trap - EXIT; return 1
        }
    found=$(find "$top/RPMS" -name '*.rpm' | head -1)
    cp "$found" "$DIST/"
    out="$DIST/$(basename "$found")"
    rm -rf "$top"
    trap - EXIT
    echo "  $(basename "$out")  $(du -h "$out" | cut -f1)"
}

case "$WHAT" in
    tar) build_tar ;;
    deb) build_deb ;;
    rpm) build_rpm ;;
    all) build_tar; build_deb; build_rpm ;;
    *) echo "unknown target: $WHAT" >&2; exit 1 ;;
esac

echo
echo "dist/:"
ls -1 "$DIST"
