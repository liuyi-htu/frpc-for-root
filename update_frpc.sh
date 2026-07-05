#!/system/bin/sh

MODDIR="${0%/*}"
frpc="$MODDIR/frpc"
CONFIG="$MODDIR/frpc.toml"
DATA_DIR="/data/adb/frpc"
TMP_DIR="$DATA_DIR/update_tmp"
DOWNLOAD_DIR="$DATA_DIR/downloads"
UPDATE_LOG="$DATA_DIR/update.log"
DEFAULT_VERSION="v0.69.1"
REPO="fatedier/frp"
AUTO_MODE=0

case "$1" in
  --auto|auto|-a) AUTO_MODE=1 ;;
esac

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

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

is_number() {
  case "$1" in
    *[!0-9]*|"") return 1 ;;
    *) return 0 ;;
  esac
}

http_download() {
  URL="$1"
  OUT="$2"
  TMP_OUT="$OUT.part"

  rm -f "$OUT" "$TMP_OUT"

  if has_cmd curl; then
    say "使用 curl 下载"
    curl -fL --retry 3 --retry-delay 2 --connect-timeout 30 --max-time 900 \
      -A "frp-magisk-ksu" -o "$TMP_OUT" "$URL" && [ -s "$TMP_OUT" ] && mv -f "$TMP_OUT" "$OUT" && return 0
  fi

  if has_cmd wget; then
    say "使用 wget 下载"
    wget --no-check-certificate --timeout=30 --tries=3 -O "$TMP_OUT" "$URL" 2>/dev/null && [ -s "$TMP_OUT" ] && mv -f "$TMP_OUT" "$OUT" && return 0
    wget -O "$TMP_OUT" "$URL" 2>/dev/null && [ -s "$TMP_OUT" ] && mv -f "$TMP_OUT" "$OUT" && return 0
  fi

  for BB in /data/adb/magisk/busybox /data/adb/ksu/bin/busybox /data/adb/ap/bin/busybox /system/bin/busybox busybox; do
    if command -v "$BB" >/dev/null 2>&1 || [ -x "$BB" ]; then
      say "使用 busybox wget 下载：$BB"
      "$BB" wget --no-check-certificate -O "$TMP_OUT" "$URL" 2>/dev/null && [ -s "$TMP_OUT" ] && mv -f "$TMP_OUT" "$OUT" && return 0
      "$BB" wget -O "$TMP_OUT" "$URL" 2>/dev/null && [ -s "$TMP_OUT" ] && mv -f "$TMP_OUT" "$OUT" && return 0
    fi
  done

  if [ -x /system/bin/toybox ]; then
    say "使用 toybox wget 下载"
    /system/bin/toybox wget -O "$TMP_OUT" "$URL" 2>/dev/null && [ -s "$TMP_OUT" ] && mv -f "$TMP_OUT" "$OUT" && return 0
  fi

  rm -f "$TMP_OUT"
  return 1
}

get_latest_version() {
  API_FILE="$TMP_DIR/latest.json"
  rm -f "$API_FILE"

  if http_download "https://api.github.com/repos/$REPO/releases/latest" "$API_FILE" >/dev/null 2>&1; then
    TAG="$(sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$API_FILE" | head -n 1)"
    if [ -n "$TAG" ]; then
      echo "$TAG"
      return 0
    fi
  fi

  echo "$DEFAULT_VERSION"
}

get_arch_asset() {
  ARCH="$(uname -m 2>/dev/null)"

  case "$ARCH" in
    aarch64|arm64) echo "linux_arm64" ;;
    armv7l|armv8l) echo "linux_arm" ;;
    arm) echo "linux_arm" ;;
    x86_64|amd64) echo "linux_amd64" ;;
    i386|i686|x86) echo "linux_386" ;;
    *)
      say "错误：未知架构：$ARCH"
      say "当前脚本支持：arm64、arm、amd64、386"
      return 1
      ;;
  esac
}

get_pid() {
  for p in /proc/[0-9]*; do
    [ -r "$p/cmdline" ] || continue
    CMDLINE="$(tr '\000' ' ' < "$p/cmdline" 2>/dev/null)"
    case "$CMDLINE" in
      *"$frpc"*)
        echo "${p##*/}"
        return 0
        ;;
    esac
  done
  return 1
}

stop_frpc() {
  PID="$(get_pid)"
  if [ -n "$PID" ]; then
    kill "$PID" 2>/dev/null
    sleep 1
    PID2="$(get_pid)"
    [ -n "$PID2" ] && kill -9 "$PID2" 2>/dev/null
  fi
}

start_frpc() {
  if [ -x "$frpc" ] && [ -f "$CONFIG" ]; then
    nohup "$frpc" -c "$CONFIG" >/dev/null 2>&1 &
    sleep 1
  fi
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
    say "提示：系统没有 sha256sum，跳过校验。"
    return 0
  fi

  if ! http_download "$URL" "$SUM_FILE" >/dev/null 2>&1; then
    say "提示：校验文件下载失败，跳过校验。"
    return 0
  fi

  EXPECT="$(grep "[[:space:]]$PKG\$" "$SUM_FILE" | awk '{print $1}' | head -n 1)"
  [ -z "$EXPECT" ] && EXPECT="$(grep "$PKG" "$SUM_FILE" | awk '{print $1}' | head -n 1)"

  if [ -z "$EXPECT" ]; then
    say "提示：校验文件中未找到 $PKG，跳过校验。"
    return 0
  fi

  ACTUAL="$(sha256sum "$FILE" 2>/dev/null | awk '{print $1}')"
  if [ "$ACTUAL" = "$EXPECT" ]; then
    say "SHA256 校验通过。"
    return 0
  fi

  say "错误：SHA256 校验失败。"
  say "期望：$EXPECT"
  say "实际：$ACTUAL"
  return 1
}

install_from_archive() {
  FILE="$1"

  [ -f "$FILE" ] || {
    say "错误：安装包不存在：$FILE"
    return 1
  }

  [ -s "$FILE" ] || {
    say "错误：安装包为空：$FILE"
    return 1
  }

  say "使用安装包：$FILE"

  rm -rf "$TMP_DIR/extract"
  mkdir -p "$TMP_DIR/extract"

  if ! extract_pkg "$FILE" "$TMP_DIR/extract"; then
    say "错误：解压失败。"
    return 1
  fi

  say "解压完成，正在查找 frpc 二进制..."

  NEW_frpc="$(find "$TMP_DIR/extract" -type f -name frpc 2>/dev/null | head -n 1)"
  if [ -z "$NEW_frpc" ]; then
    say "错误：安装包中没有找到 frpc。"
    return 1
  fi

  if [ -f "$frpc" ]; then
    chmod 755 "$frpc" 2>/dev/null
    BACKUP="$DATA_DIR/frpc.bak.$(date '+%Y%m%d%H%M%S' 2>/dev/null)"
    cp -f "$frpc" "$BACKUP" 2>/dev/null && say "已备份旧版本：$BACKUP"
  fi

  cp -f "$NEW_frpc" "$frpc" || {
    say "错误：复制 frpc 失败。"
    return 1
  }

  chmod 755 "$frpc"
  rm -rf "$TMP_DIR/extract"

  VER="$($frpc -v 2>/dev/null)"
  [ -z "$VER" ] && VER="未知"

  say "安装完成：$frpc"
  say "frpc 版本：$VER"
  return 0
}

find_local_archive() {
  ASSET="$1"

  for DIR in "$DOWNLOAD_DIR" "/sdcard/Download" "/storage/emulated/0/Download" "/data/local/tmp" "$DATA_DIR"; do
    [ -d "$DIR" ] || continue
    CANDIDATE="$(ls "$DIR"/frp_*_${ASSET}.tar.gz 2>/dev/null | tail -n 1)"
    if [ -n "$CANDIDATE" ]; then
      echo "$CANDIDATE"
      return 0
    fi
  done

  return 1
}

install_local_if_exists() {
  ASSET="$(get_arch_asset)" || return 1
  LOCAL_FILE="$(find_local_archive "$ASSET")"
  if [ -n "$LOCAL_FILE" ]; then
    install_from_archive "$LOCAL_FILE"
    return $?
  fi
  return 1
}

install_version_github() {
  VERSION="$1"
  MANUAL_URL="$2"

  case "$VERSION" in
    v*) ;;
    *) VERSION="v$VERSION" ;;
  esac

  VERSION_NO="${VERSION#v}"
  ASSET="$(get_arch_asset)" || return 1
  PKG="frp_${VERSION_NO}_${ASSET}.tar.gz"
  FILE="$DOWNLOAD_DIR/$PKG"

  if [ -n "$MANUAL_URL" ]; then
    URL="$MANUAL_URL"
  else
    URL="https://github.com/$REPO/releases/download/$VERSION/$PKG"
  fi

  say "版本：$VERSION"
  say "架构：$ASSET"
  say "文件：$PKG"
  say "下载：$URL"

  mkdir -p "$DOWNLOAD_DIR"
  rm -f "$FILE"

  if ! http_download "$URL" "$FILE"; then
    say "错误：下载失败。"
    say "请在浏览器打开上面的下载地址确认是否可访问，或把安装包放到 /sdcard/Download 后选择本地安装。"
    return 1
  fi

  if [ -z "$MANUAL_URL" ]; then
    if ! verify_checksum "$VERSION" "$PKG" "$FILE"; then
      rm -f "$FILE"
      return 1
    fi
  fi

  install_from_archive "$FILE"
  return $?
}

run_auto() {
  say "自动安装/更新 frpc 开始。"

  if install_local_if_exists; then
    say "已从本地安装包安装 frpc。"
    return 0
  fi

  VERSION="$(get_latest_version)"
  [ -z "$VERSION" ] && VERSION="$DEFAULT_VERSION"

  say "自动模式使用 GitHub 官方下载源。"
  if install_version_github "$VERSION" ""; then
    say "自动安装/更新 frpc 成功。"
    return 0
  fi

  if [ "$VERSION" != "$DEFAULT_VERSION" ]; then
    say "最新版下载失败，回退到默认版本：$DEFAULT_VERSION"
    if install_version_github "$DEFAULT_VERSION" ""; then
      say "自动安装/更新 frpc 成功。"
      return 0
    fi
  fi

  say "自动安装/更新 frpc 失败。"
  say "可手动运行：sh /data/adb/modules/frpc/update_frpc.sh"
  say "或把 frp_版本_架构.tar.gz 放到 /sdcard/Download 后选择本地安装。"
  return 1
}

run_interactive() {
  clear
  echo "========================================"
  echo "             update_frpc.sh"
  echo "========================================"
  echo "模块目录：$MODDIR"
  echo "frpc 路径：$frpc"
  echo

  if [ -f "$frpc" ]; then
    chmod 755 "$frpc" 2>/dev/null
    echo "当前版本：$($frpc -v 2>/dev/null || echo 未知)"
  else
    echo "当前版本：未安装"
  fi

  echo
  echo "下载源：GitHub 官方 Release"
  echo "本地安装包搜索目录："
  echo "  /sdcard/Download"
  echo "  /storage/emulated/0/Download"
  echo "  /data/local/tmp"
  echo "  /data/adb/frpc/downloads"
  echo
  echo "菜单："
  echo "1) 自动安装/更新最新版"
  echo "2) 指定版本下载"
  echo "3) 使用本地安装包"
  echo "4) 手动输入下载 URL"
  echo "0) 退出"
  echo
  printf "请输入序号 [1]: "
  read MODE
  [ -z "$MODE" ] && MODE="1"

  case "$MODE" in
    1)
      run_auto
      ;;
    2)
      printf "请输入 frp 版本，例如 0.69.1，直接回车使用 $DEFAULT_VERSION: "
      read INPUT_VERSION
      [ -z "$INPUT_VERSION" ] && INPUT_VERSION="$DEFAULT_VERSION"
      install_version_github "$INPUT_VERSION" ""
      ;;
    3)
      if ! install_local_if_exists; then
        echo "未找到本地安装包。"
        echo "请把 frp_版本_架构.tar.gz 放到 /sdcard/Download 或 /data/local/tmp。"
      fi
      ;;
    4)
      printf "请输入完整下载 URL: "
      read MANUAL_URL
      if [ -z "$MANUAL_URL" ]; then
        echo "URL 不能为空。"
      else
        printf "请输入版本号，例如 0.69.1，直接回车使用 $DEFAULT_VERSION: "
        read INPUT_VERSION
        [ -z "$INPUT_VERSION" ] && INPUT_VERSION="$DEFAULT_VERSION"
        install_version_github "$INPUT_VERSION" "$MANUAL_URL"
      fi
      ;;
    0) exit 0 ;;
    *) echo "无效选择。" ;;
  esac

  echo
  if [ -f "$frpc" ]; then
    chmod 755 "$frpc" 2>/dev/null
    printf "是否重启 frpc？[y/N]: "
    read RESTART
    case "$RESTART" in
      y|Y)
        stop_frpc
        start_frpc
        echo "已尝试重启 frpc。"
        ;;
      *) echo "未重启 frpc。" ;;
    esac
  fi
}

if [ "$AUTO_MODE" = "1" ]; then
  run_auto
else
  run_interactive
fi
