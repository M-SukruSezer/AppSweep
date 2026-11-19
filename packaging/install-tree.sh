#!/bin/sh
# Lay the installed file tree into a staging root.
#
# One place describes where everything goes, so the .deb and the .rpm
# cannot drift apart. Called as:
#
#     packaging/install-tree.sh <destdir> [prefix]
#
# The Python package lives under <prefix>/share/appsweep rather than in
# site-packages: it is an application, not a library, and nothing should
# be able to `import appsweep` by accident.
set -eu

DESTDIR=${1:?usage: install-tree.sh <destdir> [prefix]}
PREFIX=${2:-/usr}
SRC=$(cd "$(dirname "$0")/.." && pwd)

install -d "$DESTDIR$PREFIX/share/appsweep"
cp -r "$SRC/appsweep" "$DESTDIR$PREFIX/share/appsweep/"
find "$DESTDIR$PREFIX/share/appsweep" -name '__pycache__' -type d \
    -exec rm -rf {} + 2>/dev/null || true
# A checkout may carry group-write bits; packaged files should not.
find "$DESTDIR$PREFIX/share/appsweep" -type f -exec chmod 644 {} +
find "$DESTDIR$PREFIX/share/appsweep" -type d -exec chmod 755 {} +

install -d "$DESTDIR$PREFIX/bin"
cat > "$DESTDIR$PREFIX/bin/appsweep" <<LAUNCHER
#!/bin/sh
exec python3 -c "import sys; sys.path.insert(0, '$PREFIX/share/appsweep'); \
from appsweep.__main__ import main; sys.exit(main())" "\$@"
LAUNCHER
chmod 755 "$DESTDIR$PREFIX/bin/appsweep"

install -d "$DESTDIR$PREFIX/share/applications"
install -m 644 "$SRC/data/io.github.appsweep.AppSweep.desktop" \
    "$DESTDIR$PREFIX/share/applications/"

for variant in scalable symbolic; do
    src="$SRC/data/icons/hicolor/$variant/apps"
    [ -d "$src" ] || continue
    install -d "$DESTDIR$PREFIX/share/icons/hicolor/$variant/apps"
    install -m 644 "$src"/*.svg \
        "$DESTDIR$PREFIX/share/icons/hicolor/$variant/apps/"
done

# Translations. Compiled from source when gettext is present, otherwise
# the catalogue committed to the repository is used as-is.
for po in "$SRC"/po/*.po; do
    [ -e "$po" ] || continue
    lang=$(basename "$po" .po)
    install -d "$DESTDIR$PREFIX/share/locale/$lang/LC_MESSAGES"
    if command -v msgfmt >/dev/null 2>&1; then
        msgfmt -o "$DESTDIR$PREFIX/share/locale/$lang/LC_MESSAGES/appsweep.mo" \
            "$po"
    elif [ -f "$SRC/data/locale/$lang/LC_MESSAGES/appsweep.mo" ]; then
        install -m 644 "$SRC/data/locale/$lang/LC_MESSAGES/appsweep.mo" \
            "$DESTDIR$PREFIX/share/locale/$lang/LC_MESSAGES/appsweep.mo"
    fi
done

install -d "$DESTDIR$PREFIX/share/doc/appsweep"
install -m 644 "$SRC/README.md" "$SRC/README.tr.md" \
    "$DESTDIR$PREFIX/share/doc/appsweep/"
install -m 644 "$SRC/LICENSE" "$DESTDIR$PREFIX/share/doc/appsweep/copyright"
