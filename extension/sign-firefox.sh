#!/usr/bin/env bash
# Podpisuje paczke Firefoksa w addons.mozilla.org jako "unlisted" (dodatek NIE jest
# publikowany w sklepie, Mozilla tylko go podpisuje). Podpisany .xpi mozna
# zainstalowac na stale w zwyklym Firefoksie: about:addons -> kolo zebate ->
# "Zainstaluj dodatek z pliku…".
#
# Wymaga kluczy API z https://addons.mozilla.org/developers/addon/api/key/ :
#   AMO_JWT_ISSUER=user:12345:678 AMO_JWT_SECRET=abc... extension/sign-firefox.sh
#
# Kazde podpisanie wymaga NOWEGO numeru wersji w manifest.json (AMO nie podpisze
# drugi raz tej samej wersji).
set -euo pipefail
cd "$(dirname "$0")"

: "${AMO_JWT_ISSUER:?Ustaw AMO_JWT_ISSUER (JWT issuer z addons.mozilla.org)}"
: "${AMO_JWT_SECRET:?Ustaw AMO_JWT_SECRET (JWT secret z addons.mozilla.org)}"

./build.sh >/dev/null
version=$(python3 -c 'import json; print(json.load(open("manifest.json"))["version"])')
src=$(mktemp -d)
trap 'rm -rf "$src"' EXIT
# zrodlo = dokladnie zawartosc paczki Firefoksa (bez testow, skryptow, README)
python3 -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' \
  "../dist/hermes-finder-${version}.xpi" "$src"

npx --yes web-ext@8 sign \
  --channel=unlisted \
  --source-dir="$src" \
  --artifacts-dir=../dist/signed \
  --api-key="$AMO_JWT_ISSUER" \
  --api-secret="$AMO_JWT_SECRET"

echo "Podpisany dodatek: $(ls -t ../dist/signed/*.xpi | head -1)"
