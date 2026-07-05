#!/system/bin/sh
MODDIR="${0%/*}"
DATA_DIR="/data/adb/frpc"

# Stop frpc started by this module before removing data.
stop_frpc() {
  for p in /proc/[0-9]*; do
    [ -r "$p/cmdline" ] || continue
    CMDLINE="$(tr '\000' ' ' < "$p/cmdline" 2>/dev/null)"
    case "$CMDLINE" in
      *"$MODDIR/frpc"*|*"/data/adb/modules/frpc/frpc"*|*"/data/adb/modules_update/frpc/frpc"*)
        kill "${p##*/}" 2>/dev/null
        ;;
    esac
  done
  sleep 1
  for p in /proc/[0-9]*; do
    [ -r "$p/cmdline" ] || continue
    CMDLINE="$(tr '\000' ' ' < "$p/cmdline" 2>/dev/null)"
    case "$CMDLINE" in
      *"$MODDIR/frpc"*|*"/data/adb/modules/frpc/frpc"*|*"/data/adb/modules_update/frpc/frpc"*)
        kill -9 "${p##*/}" 2>/dev/null
        ;;
    esac
  done
}


stop_webui() {
  for p in /proc/[0-9]*; do
    [ -r "$p/cmdline" ] || continue
    CMDLINE="$(tr '\000' ' ' < "$p/cmdline" 2>/dev/null)"
    case "$CMDLINE" in
      *"/data/adb/modules/frpc/webui.sh"*|*httpd*"/data/adb/frpc/web/www"*)
        kill "${p##*/}" 2>/dev/null
        ;;
    esac
  done
  sleep 1
  for p in /proc/[0-9]*; do
    [ -r "$p/cmdline" ] || continue
    CMDLINE="$(tr '\000' ' ' < "$p/cmdline" 2>/dev/null)"
    case "$CMDLINE" in
      *"/data/adb/modules/frpc/webui.sh"*|*httpd*"/data/adb/frpc/web/www"*)
        kill -9 "${p##*/}" 2>/dev/null
        ;;
    esac
  done
}

stop_frpc
stop_webui

# Clean runtime data created by this module outside the module directory.
rm -rf "$DATA_DIR" 2>/dev/null

exit 0
