#!/bin/sh
set -eu

release=${MGESTURE_RELEASE:-latest}
repo=${MGESTURE_GITHUB_REPOSITORY:-christiandoxa/mgesture}
base=${MGESTURE_RELEASE_BASE_URL:-}
app_root=${MGESTURE_INSTALL_DIR:-"$HOME/.local/share/mgesture"}
bin_dir=${MGESTURE_BIN_DIR:-"$HOME/.local/bin"}
tmp=
stage=

fail() { echo "mgesture installer: $1" >&2; exit 1; }
cleanup() { [ -z "$stage" ] || rm -rf "$stage"; [ -z "$tmp" ] || rm -rf "$tmp"; }
trap cleanup EXIT INT TERM

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print tolower($1)}';
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print tolower($1)}';
  elif command -v openssl >/dev/null 2>&1; then openssl dgst -sha256 "$1" | sed 's/^.*= //' | tr 'A-F' 'a-f';
  else fail 'sha256sum, shasum, or openssl is required'; fi
}

download() {
  case "$1" in file://*) cp "${1#file://}" "$2"; return;; esac
  [ -f "$1" ] && { cp "$1" "$2"; return; }
  if command -v curl >/dev/null 2>&1; then curl --proto '=https' --tlsv1.2 --retry 3 --fail --silent --show-error --location "$1" -o "$2";
  elif command -v wget >/dev/null 2>&1; then wget -q -O "$2" "$1";
  else fail 'curl or wget is required'; fi
}

uninstall() {
  rm -rf "$app_root"
  [ -f "$bin_dir/mgesture" ] && rm -f "$bin_dir/mgesture"
  echo "Removed releases from $app_root; configuration and cache preserved."
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --release) [ "$#" -gt 1 ] || fail '--release requires a value'; release=$2; shift 2;;
    --uninstall) uninstall; exit 0;;
    --help|-h) echo 'Usage: install.sh [--release VERSION] [--uninstall]'; exit 0;;
    *) fail "unknown argument: $1";;
  esac
done
[ -n "${HOME:-}" ] || fail 'HOME is required'
case "$release" in latest|[0-9]*.[0-9]*.[0-9]*) ;; *) fail 'release must be latest or x.y.z';; esac

case "$(uname -s):$(uname -m)" in
  Linux:x86_64|Linux:amd64|Linux:x64) target=x86_64-unknown-linux-gnu;;
  Linux:aarch64|Linux:arm64) target=aarch64-unknown-linux-gnu;;
  Darwin:x86_64|Darwin:amd64|Darwin:x64) target=x86_64-apple-darwin;;
  Darwin:arm64|Darwin:aarch64) target=aarch64-apple-darwin;;
  *) fail "unsupported target: $(uname -s)-$(uname -m)";;
esac
if [ -z "$base" ]; then
  if [ "$release" = latest ]; then base="https://github.com/$repo/releases/latest/download"; else base="https://github.com/$repo/releases/download/$release"; fi
fi

tmp=$(mktemp -d "${TMPDIR:-/tmp}/mgesture-install.XXXXXX")
download "${base%/}/SHA256SUMS" "$tmp/SHA256SUMS"
download "${base%/}/release-manifest.json" "$tmp/release-manifest.json"
download "${base%/}/release-manifest.tsv" "$tmp/release-manifest.tsv"
schema=$(awk -F '\t' '$1 == "# schema_version" {print $2; exit}' "$tmp/release-manifest.tsv")
[ "$schema" = 1 ] || fail 'unsupported release manifest schema'
asset=$(awk -F '\t' -v target="$target" '$1 == target {print $2; exit}' "$tmp/release-manifest.tsv")
[ -n "$asset" ] || fail "release manifest has no matching target $target"
case "$asset" in "mgesture-$target.tar.gz") ;; *) fail 'release manifest asset mismatch';; esac
manifest_version=$(awk -F '\t' '$1 == "# version" {print $2; exit}' "$tmp/release-manifest.tsv")
manifest_commit=$(awk -F '\t' '$1 == "# commit" {print $2; exit}' "$tmp/release-manifest.tsv")
printf '%s' "$manifest_commit" | grep -Eq '^[0-9a-fA-F]{40}$' || fail 'manifest commit is not a full SHA'
grep -F '"schema_version": 1' "$tmp/release-manifest.json" >/dev/null || fail 'JSON manifest schema mismatch'
grep -F "\"$target\"" "$tmp/release-manifest.json" >/dev/null || fail "JSON manifest has no $target"
grep -F "\"asset\": \"$asset\"" "$tmp/release-manifest.json" >/dev/null || fail 'JSON manifest asset mismatch'
[ "$(awk '$2 == "release-manifest.json" {print tolower($1); exit}' "$tmp/SHA256SUMS")" = "$(sha256 "$tmp/release-manifest.json")" ] || fail 'JSON manifest checksum mismatch'
[ "$(awk '$2 == "release-manifest.tsv" {print tolower($1); exit}' "$tmp/SHA256SUMS")" = "$(sha256 "$tmp/release-manifest.tsv")" ] || fail 'TSV manifest checksum mismatch'
expected=$(awk -v asset="$asset" '$2 == asset {print tolower($1); exit}' "$tmp/SHA256SUMS")
printf '%s' "$expected" | grep -Eq '^[0-9a-f]{64}$' || fail 'asset checksum missing'
manifest_asset_sha=$(awk -F '\t' -v target="$target" '$1 == target {print tolower($5); exit}' "$tmp/release-manifest.tsv")
[ "$manifest_asset_sha" = "$expected" ] || fail 'manifest asset checksum does not match SHA256SUMS'
download "${base%/}/$asset" "$tmp/$asset"
[ "$expected" = "$(sha256 "$tmp/$asset")" ] || fail 'asset checksum mismatch'

stage="$tmp/stage"
mkdir -p "$stage"
tar -xzf "$tmp/$asset" -C "$stage"
root="$stage/mgesture"
binary="$root/bin/mgesture"
[ -x "$binary" ] || fail 'archive missing mgesture/bin/mgesture'
case "$(uname -s)" in
  Darwin) native_library=libmgesture_mojo.dylib;;
  Linux) native_library=libmgesture_mojo.so;;
  *) fail 'unsupported native Mojo library platform';;
esac
[ -f "$root/runtime/mojo/$native_library" ] || fail "archive missing runtime/mojo/$native_library"
version_line=$(MGESTURE_BUNDLE_ROOT="$root" "$binary" --version)
case "$version_line" in mgesture\ *) ;; *) fail 'staged executable did not report mgesture';; esac
installed_version=${version_line#'mgesture '}
[ "$manifest_version" = "$installed_version" ] || fail 'binary version differs from manifest'
MGESTURE_BUNDLE_ROOT="$root" "$binary" self-test --headless --fake-input --engine mojo >/dev/null || fail 'staged native Mojo self-test failed'
MGESTURE_BUNDLE_ROOT="$root" "$binary" doctor --runtime --json >/dev/null || fail 'staged runtime diagnostics failed'

mkdir -p "$app_root/releases" "$bin_dir"
staged_release="$app_root/releases/.${installed_version}.$$"
mv "$root" "$staged_release"
shim="$bin_dir/.mgesture.$$"
printf '%s\n' '#!/bin/sh' "exec \"$app_root/current/bin/mgesture\" \"\$@\"" > "$shim"
chmod 0755 "$shim"
mv -f "$shim" "$bin_dir/mgesture"
current_tmp="$app_root/.current.$$"
ln -s "$staged_release" "$current_tmp"
mv -f "$current_tmp" "$app_root/current"
stage=
echo "mgesture $installed_version installed at $app_root/current"
case ":${PATH:-}:" in *":$bin_dir:"*) ;; *) echo "Current shell: export PATH=\"$bin_dir:\$PATH\"";; esac
echo 'Next: mgesture doctor; mgesture calibrate; mgesture'
