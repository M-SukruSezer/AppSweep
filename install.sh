#!/bin/sh
# Install AppSweep for the current user. No root needed.
set -e

PREFIX="${PREFIX:-$HOME/.local}"
SRC="$(cd "$(dirname "$0")" && pwd)"

echo "Installing AppSweep to $PREFIX"

mkdir -p "$PREFIX/share/appsweep" "$PREFIX/bin" "$PREFIX/share/applications"
cp -r "$SRC/appsweep" "$PREFIX/share/appsweep/"

# Compiled translations. Built from po/*.po by po/update.sh; compile them now
# if the tree only has the sources.
if [ ! -d "$SRC/data/locale" ] && command -v msgfmt >/dev/null 2>&1; then
    echo "Compiling translations…"
    "$SRC/po/update.sh" compile >/dev/null 2>&1 || true
fi
if [ -d "$SRC/data/locale" ]; then
    cp -r "$SRC/data/locale" "$PREFIX/share/appsweep/"
    for mo in "$SRC"/data/locale/*/LC_MESSAGES/appsweep.mo; do
        [ -e "$mo" ] || continue
        lang=$(basename "$(dirname "$(dirname "$mo")")")
        mkdir -p "$PREFIX/share/locale/$lang/LC_MESSAGES"
        cp "$mo" "$PREFIX/share/locale/$lang/LC_MESSAGES/appsweep.mo"
        echo "  translation: $lang"
    done
fi

cat > "$PREFIX/bin/appsweep" <<LAUNCHER
#!/bin/sh
exec python3 -c "import sys; sys.path.insert(0, '$PREFIX/share/appsweep'); \
from appsweep.__main__ import main; sys.exit(main())" "\$@"
LAUNCHER
chmod +x "$PREFIX/bin/appsweep"

# Application icon, in the places the icon theme actually looks.
for variant in scalable symbolic; do
    src_dir="$SRC/data/icons/hicolor/$variant/apps"
    [ -d "$src_dir" ] || continue
    mkdir -p "$PREFIX/share/icons/hicolor/$variant/apps"
    cp "$src_dir"/*.svg "$PREFIX/share/icons/hicolor/$variant/apps/"
    echo "  icon: $variant"
done
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "$PREFIX/share/icons/hicolor" 2>/dev/null || true
fi

sed "s|^Exec=appsweep$|Exec=$PREFIX/bin/appsweep|" \
    "$SRC/data/io.github.appsweep.AppSweep.desktop" \
    > "$PREFIX/share/applications/io.github.appsweep.AppSweep.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
fi

echo
echo "Done. Run 'appsweep' for the window, or 'appsweep --help' for the CLI."
case ":$PATH:" in
    *":$PREFIX/bin:"*) ;;
    *) echo "Note: $PREFIX/bin is not on your PATH yet." ;;
esac
