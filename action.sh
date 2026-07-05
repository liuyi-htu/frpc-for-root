#!/system/bin/sh

MODDIR="${0%/*}"
frpc="$MODDIR/frpc"
DATA_DIR="/data/adb/frpc"
CONFIG="$DATA_DIR/frpc.toml"
CONTROL_FILE="$DATA_DIR/disabled"
LOW_MEM_FILE="$DATA_DIR/low_memory_mode"
SERVICE_LOG="$DATA_DIR/service.log"
WEBUI="$MODDIR/webui.sh"
WEB_ROOT="$DATA_DIR/web/www"
WEB_PID_FILE="$DATA_DIR/web.pid"
TIMEZONE_FILE="$DATA_DIR/timezone"
WEB_PORT_FILE="$DATA_DIR/web_port"
PID_FILE="$DATA_DIR/frpc.pid"

mkdir -p "$DATA_DIR"

is_number() { case "$1" in *[!0-9]*|"") return 1 ;; *) return 0 ;; esac; }
get_web_port() { PORT="62930"; [ -f "$WEB_PORT_FILE" ] && TMP="$(cat "$WEB_PORT_FILE" 2>/dev/null | head -n 1)" && is_number "$TMP" && PORT="$TMP"; echo "$PORT"; }
web_pid_alive() { P="$1"; [ -n "$P" ] || return 1; [ -r "/proc/$P/cmdline" ] || return 1; CMDLINE="$(tr '\000' ' ' < "/proc/$P/cmdline" 2>/dev/null)"; case "$CMDLINE" in *"$WEBUI"*|*httpd*"$WEB_ROOT"*) return 0 ;; esac; return 1; }
get_webui_pid() { if [ -f "$WEB_PID_FILE" ]; then P="$(cat "$WEB_PID_FILE" 2>/dev/null | head -n 1)"; web_pid_alive "$P" && { echo "$P"; return 0; }; rm -f "$WEB_PID_FILE" 2>/dev/null; fi; return 1; }
start_webui() { [ -f "$WEBUI" ] || { echo "web 控制台脚本不存在：$WEBUI"; return 1; }; PID="$(get_webui_pid)"; [ -n "$PID" ] && { echo "web 控制台已经在运行，PID: $PID"; return 0; }; nohup sh "$WEBUI" >/dev/null 2>&1 & echo "web 控制台恢复命令已发送：http://127.0.0.1:$(get_web_port)"; log_msg "Action 已发送恢复 web 控制台命令"; return 0; }
get_timezone() { TZ_FILE="$MODDIR/zoneinfo/Asia/Shanghai"; if [ -f "$TZ_FILE" ]; then TZ_VALUE="$TZ_FILE"; else TZ_VALUE="Asia/Shanghai"; fi; echo "$TZ_VALUE" > "$TIMEZONE_FILE" 2>/dev/null; chmod 644 "$TIMEZONE_FILE" 2>/dev/null; echo "$TZ_VALUE"; }
apply_timezone() { export TZ="$(get_timezone)"; }
shell_ts() { TZ=CST-8 date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "0000-00-00 00:00:00"; }
log_msg() { echo "$(shell_ts) $1" >> "$SERVICE_LOG"; }

pid_alive() {
  P="$1"; [ -n "$P" ] || return 1; [ -r "/proc/$P/cmdline" ] || return 1
  CMDLINE="$(tr '\000' ' ' < "/proc/$P/cmdline" 2>/dev/null)"
  case "$CMDLINE" in *"$frpc"*"-c $CONFIG"*|*"$frpc"*" -c "*"/data/adb/frpc/frpc.toml"*) return 0 ;; esac
  return 1
}
get_pid_quick() {
  if [ -f "$PID_FILE" ]; then P="$(cat "$PID_FILE" 2>/dev/null | head -n 1)"; pid_alive "$P" && { echo "$P"; return 0; }; rm -f "$PID_FILE" 2>/dev/null; fi
  if command -v pidof >/dev/null 2>&1; then for P in $(pidof frpc 2>/dev/null); do pid_alive "$P" && { echo "$P" > "$PID_FILE" 2>/dev/null; echo "$P"; return 0; }; done; fi
  return 1
}
get_pid() {
  PID_NOW="$(get_pid_quick 2>/dev/null)"; [ -n "$PID_NOW" ] && { echo "$PID_NOW"; return 0; }
  if command -v pgrep >/dev/null 2>&1; then for P in $(pgrep -x frpc 2>/dev/null); do pid_alive "$P" && { echo "$P" > "$PID_FILE" 2>/dev/null; echo "$P"; return 0; }; done; P="$(pgrep -f "$frpc.*-c $CONFIG" 2>/dev/null | head -n 1)"; [ -n "$P" ] && pid_alive "$P" && { echo "$P" > "$PID_FILE" 2>/dev/null; echo "$P"; return 0; }; fi
  return 1
}
get_server_addr() { [ -f "$CONFIG" ] && sed -n 's/^serverAddr[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "$CONFIG" | head -n 1; }
get_server_port() { [ -f "$CONFIG" ] && sed -n 's/^serverPort[[:space:]]*=[[:space:]]*\([0-9]*\).*/\1/p' "$CONFIG" | head -n 1; }
get_proxy_count() { [ -f "$CONFIG" ] || { echo 0; return; }; grep -c '^\[\[proxies\]\]' "$CONFIG" 2>/dev/null; }
ensure_frpc() { [ -f "$frpc" ] || { echo "frpc 文件不存在：$frpc"; return 1; }; chmod 755 "$frpc" 2>/dev/null; return 0; }
ready_reason() { ensure_frpc || return; [ -f "$CONFIG" ] || { echo "配置文件不存在：$CONFIG"; return; }; [ -n "$(get_server_addr)" ] || { echo "serverAddr 未配置"; return; }; [ -n "$(get_server_port)" ] || { echo "serverPort 未配置"; return; }; [ "$(get_proxy_count)" -gt 0 ] || { echo "代理未配置"; return; }; echo "ready"; }
start_frpc() { REASON="$(ready_reason)"; [ "$REASON" = "ready" ] || { echo "启动失败：$REASON"; log_msg "Action 启动失败：$REASON"; return 1; }; PID="$(get_pid)"; [ -n "$PID" ] && { echo "frpc 已经在运行，PID: $PID"; return 0; }; apply_timezone; chmod 755 "$frpc" 2>/dev/null; nohup "$frpc" -c "$CONFIG" >> "$DATA_DIR/frpc.log" 2>&1 & echo "$!" > "$PID_FILE" 2>/dev/null; sleep 2; PID="$(get_pid)"; [ -n "$PID" ] && { echo "frpc 已启动，PID: $PID"; log_msg "Action 已启动 frpc，PID: $PID"; return 0; }; echo "frpc 启动失败，请查看日志"; log_msg "Action 启动 frpc 失败"; return 1; }
stop_frpc() { PID="$(get_pid)"; if [ -n "$PID" ]; then kill "$PID" 2>/dev/null; sleep 1; PID2="$(get_pid)"; [ -n "$PID2" ] && kill -9 "$PID2" 2>/dev/null; echo "frpc 已停止。"; log_msg "Action 已停止 frpc"; else echo "frpc 当前没有运行。"; fi; rm -f "$PID_FILE" 2>/dev/null; }

update_module_prop() {
  MODULE_PROP="$MODDIR/module.prop"
  [ -f "$MODULE_PROP" ] || return 0
  WEB_MODE_ZH="web常驻"
  WEB_MODE_EN="resident"
  if [ -f "$LOW_MEM_FILE" ]; then
    WEB_MODE_ZH="最小内存"
    WEB_MODE_EN="low memory"
  fi
  FRP_STATUS_ZH="未运行"
  FRP_STATUS_EN="not running"
  PID_NOW="$(get_pid_quick 2>/dev/null)"
  if [ -n "$PID_NOW" ]; then
    FRP_STATUS_ZH="运行中"
    FRP_STATUS_EN="running"
  elif [ -f "$CONTROL_FILE" ]; then
    FRP_STATUS_ZH="已停止"
    FRP_STATUS_EN="stopped"
  fi
  PORT_NOW=""
  if command -v get_web_port >/dev/null 2>&1; then
    PORT_NOW="$(get_web_port 2>/dev/null)"
  fi
  if [ -z "$PORT_NOW" ] && command -v get_port >/dev/null 2>&1; then
    PORT_NOW="$(get_port 2>/dev/null)"
  fi
  [ -n "$PORT_NOW" ] || PORT_NOW="62930"
DESC="web mode: ${WEB_MODE_EN}; frpc: ${FRP_STATUS_EN}; web URL: http://127.0.0.1:${PORT_NOW}\nweb模式：${WEB_MODE_ZH}；frpc：${FRP_STATUS_ZH}；web地址：http://127.0.0.1:${PORT_NOW}"
  CURRENT_DESC="$(sed -n 's/^description=//p' "$MODULE_PROP" 2>/dev/null | head -n 1)"
  [ "$CURRENT_DESC" = "$DESC" ] && return 0
  TMP_PROP="$MODULE_PROP.$$"
  FOUND_DESC=0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      description=*) printf 'description=%s\n' "$DESC"; FOUND_DESC=1 ;;
      *) echo "$line" ;;
    esac
  done < "$MODULE_PROP" > "$TMP_PROP" 2>/dev/null
  [ "$FOUND_DESC" = "1" ] || printf 'description=%s\n' "$DESC" >> "$TMP_PROP"
  mv "$TMP_PROP" "$MODULE_PROP" 2>/dev/null
  chmod 644 "$MODULE_PROP" 2>/dev/null
}

update_module_prop
echo "=============================="
echo "      frpc 启动 / 停止"
echo "Root 管理器状态已刷新"
echo "web 控制台：http://127.0.0.1:$(get_web_port)"
echo "配置文件：/data/adb/frpc/frpc.toml"
echo "=============================="

PID="$(get_pid_quick)"
if [ -f "$LOW_MEM_FILE" ]; then
  echo "当前状态：最小内存运行模式"
  [ -n "$PID" ] && echo "frpc 运行中，PID: $PID" || echo "frpc 当前未运行"
  echo "正在退出最小内存模式并恢复 web 控制台..."
  rm -f "$LOW_MEM_FILE" 2>/dev/null
  start_webui
  update_module_prop
  exit $?
fi
PID="$(get_pid)"
if [ -f "$CONTROL_FILE" ]; then
  echo "当前状态：已手动关闭"
  echo "正在切换为启动 frpc..."
  rm -f "$CONTROL_FILE" 2>/dev/null
  start_frpc
  update_module_prop
  exit $?
fi
if [ -n "$PID" ]; then
  echo "当前状态：运行中，PID: $PID"
  echo "正在切换为关闭 frpc..."
  echo "1" > "$CONTROL_FILE"; chmod 644 "$CONTROL_FILE" 2>/dev/null
  stop_frpc
  update_module_prop
  exit 0
fi

echo "当前状态：未运行"
echo "正在切换为启动 frpc..."
rm -f "$CONTROL_FILE" 2>/dev/null
start_frpc
update_module_prop
exit $?
