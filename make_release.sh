#!/bin/bash
# Fe-Pt MD - Linux release archive builder (tar.gz).
# Mirror of make_release.bat for Linux one-click bundles.
set -e
cd "$(dirname "$0")"
PROJ="$PWD"

VERSION=$(git describe --tags --abbrev=0 2>/dev/null || echo v1.7.0)
NAME="FePt-Thermal-Expansion-MD-${VERSION}-linux"
BUILD=$(mktemp -d)
mkdir -p "$BUILD/$NAME"

echo "Version: $VERSION"

echo "  [1/6] Root files ..."
cp README.md .gitattributes requirements.txt requirements-mace.txt \
   bootstrap.sh run_lammps.sh \
   _regenerate_plots.py "$BUILD/$NAME/"

echo "  [2/6] Scripts ..."
mkdir -p "$BUILD/$NAME/scripts"
cp scripts/*.py "$BUILD/$NAME/scripts/"
cp scripts/run_main_mace.sh "$BUILD/$NAME/scripts/"

echo "  [3/6] Data + potentials ..."
mkdir -p "$BUILD/$NAME/data"
cp data/*.lmp "$BUILD/$NAME/data/" 2>/dev/null || echo "    (no .lmp structures, skipping)"
mkdir -p "$BUILD/$NAME/potentials"
cp potentials/* "$BUILD/$NAME/potentials/"

echo "  [4/6] Docs ..."
mkdir -p "$BUILD/$NAME/docs"
cp docs/*.md "$BUILD/$NAME/docs/" 2>/dev/null || echo "    (no docs, skipping)"

echo "  [5/6] Pre-calculated results ..."
if [ -f output_v4_256/run_protocol.txt ]; then
    mkdir -p "$BUILD/$NAME/output_v4_256"
    cp -r output_v4_256/* "$BUILD/$NAME/output_v4_256/"
else
    echo "    (none, skipping)"
fi

echo "  [6/6] Packing ..."
find "$BUILD" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$BUILD" -name "*.pyc" -delete 2>/dev/null || true
chmod +x "$BUILD/$NAME"/*.sh "$BUILD/$NAME/scripts"/*.sh

rm -f "$PROJ/$NAME.tar.gz"
tar -czf "$PROJ/$NAME.tar.gz" -C "$BUILD" "$NAME"
rm -rf "$BUILD"

echo
echo "Created: $NAME.tar.gz"
ls -la "$PROJ/$NAME.tar.gz"
