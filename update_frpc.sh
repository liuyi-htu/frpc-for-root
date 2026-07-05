#!/system/bin/sh

SCRIPT_PATH="$0"
case "$SCRIPT_PATH" in
  */*) SCRIPT_DIR="${SCRIPT_PATH%/*}" ;;
  *) SCRIPT_DIR="." ;;
esac

MODDIR="$(cd "$SCRIPT_DIR" 2>/dev/null && pwd)"
[ -n "$MODDIR" ] || MODDIR="/data/adb/modules/frpc"

frpc="$MODDIR/frpc"
DATA_DIR="/data/adb/frpc"
TMP_DIR="$DATA_DIR/update_tmp"
DOWNLOAD_DIR="$DATA_DIR/downloads"
UPDATE_LOG="$DATA_DIR/update.log"
UPDATE_STATUS="$DATA_DIR/update.status"
REPO="fatedier/frp"

mkdir -p "$DATA_DIR" "$DOWNLOAD_DIR" "$TMP_DIR"

ts() {
  TZ=CST-8 date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "0000-00-00 00:00:00"
}

log_msg() {
  echo "$(ts) $1" >> "$UPDATE_LOG" 2>/dev/null
}

say() {
  echo "$1"
  log_msg "$1"
}

set_status() {
  echo "$1" > "$UPDATE_STATUS" 2>/dev/null
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

normalize_version() {
  echo "$1" | sed 's/^v//' | tr -d '\r\n '
}

get_current_version() {
  if [ ! -x "$frpc" ]; then
    echo "not installed"
    return
  fi

  chmod 755 "$frpc" 2>/dev/null
  VER="$("$frpc" -v 2>/dev/null | head -n 1 | tr -d '\r')"
  [ -n "$VER" ] || VER="unknown"
  echo "$VER"
}

http_download() {
  URL="$1"
  OUT="$2"
  TMP_OUT="$OUT.part"

  rm -f "$OUT" "$TMP_OUT"

  if has_cmd curl; then
    curl -fL --retry 3 --retry-delay 2 --connect-timeout 30 --max-time 900 \
      -A "frp-magisk-ksu" -o "$TMP_OUT" "$URL" \
      && [ -s "$TMP_OUT" ] \
      && mv -f "$TMP_OUT" "$OUT" \
      && return 0
  fi

  if has_cmd wget; then
    wget --no-check-certificate --timeout=30 --tries=3 -O "$TMP_OUT" "$URL" 2>/dev/null \
      && [ -s "$TMP_OUT" ] \
      && mv -f "$TMP_OUT" "$OUT" \
      && return 0

    wget -O "$TMP_OUT" "$URL" 2>/dev/null \
      && [ -s "$TMP_OUT" ] \
      && mv -f "$TMP_OUT" "$OUT" \
      && return 0
  fi

  for BB in /data/adb/magisk/busybox /data/adb/ksu/bin/busybox /data/adb/ap/bin/busybox /system/bin/busybox busybox; do
    if command -v "$BB" >/dev/null 2>&1 || [ -x "$BB" ]; then
      "$BB" wget --no-check-certificate -O "$TMP_OUT" "$URL" 2>/dev/null \
        && [ -s "$TMP_OUT" ] \
        && mv -f "$TMP_OUT" "$OUT" \
        && return 0

      "$BB" wget -O "$TMP_OUT" "$URL" 2>/dev/null \
        && [ -s "$TMP_OUT" ] \
        && mv -f "$TMP_OUT" "$OUT" \
        && return 0
    fi
  done

  if [ -x /system/bin/toybox ]; then
    /system/bin/toybox wget -O "$TMP_OUT" "$URL" 2>/dev/null \
      && [ -s "$TMP_OUT" ] \
      && mv -f "$TMP_OUT" "$OUT" \
      && return 0
  fi

  rm -f "$TMP_OUT"
  return 1
}

get_latest_version() {
  API_FILE="$TMP_DIR/latest.json"
  rm -f "$API_FILE"

  if ! http_download "https://api.github.com/repos/$REPO/releases/latest" "$API_FILE"; then
    return 1
  fi

  TAG="$(sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$API_FILE" | head -n 1)"
  [ -n "$TAG" ] || return 1

  echo "$TAG"
  return 0
}

get_arch_asset() {
  ARCH="$(uname -m 2>/dev/null)"

  case "$ARCH" in
    aarch64|arm64) echo "linux_arm64" ;;
    armv7l|armv8l|arm) echo "linux_arm" ;;
    x86_64|amd64) echo "linux_amd64" ;;
    i386|i686|x86) echo "linux_386" ;;
    *)
      say "Error: unsupported architecture: $ARCH"
      say "Supported architectures: arm64, arm, amd64, 386"
      return 1
      ;;
  esac
}

extract_pkg() {
  FILE="$1"
  DEST="$2"

  mkdir -p "$DEST"

  if tar -xzf "$FILE" -C "$DEST" 2>/dev/null; then
    return 0
  fi

  for BB in /data/adb/magisk/busybox /data/adb/ksu/bin/busybox /data/adb/ap/bin/busybox /system/bin/busybox busybox; do
    if command -v "$BB" >/dev/null 2>&1 || [ -x "$BB" ]; then
      "$BB" tar -xzf "$FILE" -C "$DEST" 2>/dev/null && return 0
    fi
  done

  if [ -x /system/bin/toybox ]; then
    /system/bin/toybox tar -xzf "$FILE" -C "$DEST" 2>/dev/null && return 0
  fi

  if has_cmd gzip; then
    gzip -dc "$FILE" | tar -x -C "$DEST" 2>/dev/null && return 0
  fi

  return 1
}

verify_checksum() {
  VERSION="$1"
  PKG="$2"
  FILE="$3"
  SUM_FILE="$TMP_DIR/frp_sha256_checksums.txt"
  URL="https://github.com/$REPO/releases/download/$VERSION/frp_sha256_checksums.txt"

  if ! has_cmd sha256sum; then
    say "Notice: sha256sum is not available. Skipping checksum verification."
    return 0
  fi

  if ! http_download "$URL" "$SUM_FILE"; then
    say "Notice: checksum file download failed. Skipping checksum verification."
    return 0
  fi

  EXPECT="$(grep "[[:space:]]$PKG\$" "$SUM_FILE" | awk '{print $1}' | head -n 1)"
  [ -z "$EXPECT" ] && EXPECT="$(grep "$PKG" "$SUM_FILE" | awk '{print $1}' | head -n 1)"

  if [ -z "$EXPECT" ]; then
    say "Notice: $PKG was not found in checksum file. Skipping checksum verification."
    return 0
  fi

  ACTUAL="$(sha256sum "$FILE" 2>/dev/null | awk '{print $1}')"

  if [ "$ACTUAL" = "$EXPECT" ]; then
    say "SHA256 checksum passed."
    return 0
  fi

  say "Error: SHA256 checksum failed."
  say "Expected: $EXPECT"
  say "Actual: $ACTUAL"
  return 1
}

install_from_archive() {
  FILE="$1"

  [ -f "$FILE" ] || {
    say "Error: package file does not exist: $FILE"
    return 1
  }

  [ -s "$FILE" ] || {
    say "Error: package file is empty: $FILE"
    return 1
  }

  say "Update started: extracting package and replacing frpc."

  rm -rf "$TMP_DIR/extract"
  mkdir -p "$TMP_DIR/extract"

  if ! extract_pkg "$FILE" "$TMP_DIR/extract"; then
    say "Error: failed to extract package."
    return 1
  fi

  NEW_frpc="$(find "$TMP_DIR/extract" -type f -name frpc 2>/dev/null | head -n 1)"

  if [ -z "$NEW_frpc" ]; then
    say "Error: frpc binary was not found in the package."
    return 1
  fi

  if [ -f "$frpc" ]; then
    BACKUP="$DATA_DIR/frpc.bak.$(date '+%Y%m%d%H%M%S' 2>/dev/null)"
    cp -f "$frpc" "$BACKUP" 2>/dev/null && say "Old version backed up: $BACKUP"
  fi

  cp -f "$NEW_frpc" "$frpc.tmp" || {
    say "Error: failed to copy frpc."
    return 1
  }

  chmod 755 "$frpc.tmp" 2>/dev/null

  mv -f "$frpc.tmp" "$frpc" || {
    say "Error: failed to replace frpc."
    rm -f "$frpc.tmp" 2>/dev/null
    return 1
  }

  chmod 755 "$frpc" 2>/dev/null
  rm -rf "$TMP_DIR/extract"

  NEW_VER="$("$frpc" -v 2>/dev/null | head -n 1 | tr -d '\r')"
  [ -n "$NEW_VER" ] || NEW_VER="unknown"

  say "Update completed: frpc version $NEW_VER."
  return 0
}

main() {
  set_status "running"

  say "========== frpc update started =========="

  CURRENT_VERSION="$(get_current_version)"

  LATEST_VERSION="$(get_latest_version)"
  if [ -z "$LATEST_VERSION" ]; then
    say "Version check: installed=$CURRENT_VERSION, failed to get latest version."
    say "Error: failed to get the official latest version. Update stopped."
    set_status "failed"
    return 1
  fi

  say "Version check: installed=$CURRENT_VERSION, latest=$LATEST_VERSION."

  CURRENT_NORM="$(normalize_version "$CURRENT_VERSION")"
  LATEST_NORM="$(normalize_version "$LATEST_VERSION")"

  if [ "$CURRENT_NORM" = "$LATEST_NORM" ]; then
    say "Already latest. No update needed."
    say "========== frpc update finished =========="
    set_status "latest"
    return 0
  fi

  ASSET="$(get_arch_asset)" || {
    set_status "failed"
    return 1
  }

  VERSION_NO="${LATEST_VERSION#v}"
  PKG="frp_${VERSION_NO}_${ASSET}.tar.gz"
  FILE="$DOWNLOAD_DIR/$PKG"
  URL="https://github.com/$REPO/releases/download/$LATEST_VERSION/$PKG"

  mkdir -p "$DOWNLOAD_DIR"
  rm -f "$FILE"

  say "Download started: $URL"

  if ! http_download "$URL" "$FILE"; then
    say "Error: download failed."
    set_status "failed"
    return 1
  fi

  say "Download completed: $FILE"

  if ! verify_checksum "$LATEST_VERSION" "$PKG" "$FILE"; then
    rm -f "$FILE"
    set_status "failed"
    return 1
  fi

  if install_from_archive "$FILE"; then
    say "========== frpc update finished =========="
    set_status "updated"
    return 0
  fi

  say "Error: update failed."
  set_status "failed"
  return 1
}

main "$@"
exit $?
