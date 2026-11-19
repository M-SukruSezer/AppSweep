#!/bin/sh
# Re-extract strings from the source and merge them into each catalogue.
#
#   po/update.sh            refresh appsweep.pot and merge into every .po
#   po/update.sh compile    compile every .po into data/locale/
#
# Translations live in the .po files. Nothing here overwrites a translation:
# msgmerge keeps existing ones and marks changed strings as fuzzy.
set -e
cd "$(dirname "$0")/.."

DOMAIN=appsweep

if [ "$1" != "compile" ]; then
    echo "Extracting strings…"
    xgettext --language=Python --keyword=_ --keyword=N_:1,2 \
        --from-code=UTF-8 --package-name=AppSweep --package-version=0.1.0 \
        --copyright-holder="AppSweep contributors" \
        --msgid-bugs-address="https://github.com/M-SukruSezer/AppSweep/issues" \
        --add-comments=TRANSLATORS --sort-by-file \
        -o "po/$DOMAIN.pot" $(find appsweep -name '*.py' | sort)

    for po in po/*.po; do
        [ -e "$po" ] || continue
        echo "Merging $po…"
        msgmerge --update --backup=none --quiet "$po" "po/$DOMAIN.pot"
    done
fi

echo "Compiling…"
for po in po/*.po; do
    [ -e "$po" ] || continue
    lang=$(basename "$po" .po)
    mkdir -p "data/locale/$lang/LC_MESSAGES"
    msgfmt --check -o "data/locale/$lang/LC_MESSAGES/$DOMAIN.mo" "$po"
    printf '  %s: ' "$lang"
    msgfmt --statistics -o /dev/null "$po" 2>&1
done
echo "Done."
