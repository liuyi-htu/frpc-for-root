#!/system/bin/sh

MODDIR="${0%/*}"
frpc="$MODDIR/frpc"
DATA_DIR="/data/adb/frpc"
CONFIG="$DATA_DIR/frpc.toml"
DEFAULT_CONFIG="$MODDIR/frpc.toml"
DELAY_FILE="$DATA_DIR/start_delay"
TIMEZONE_FILE="$DATA_DIR/timezone"
CONTROL_FILE="$DATA_DIR/disabled"
LOW_MEM_FILE="$DATA_DIR/low_memory_mode"
SERVICE_LOG="$DATA_DIR/service.log"
LOG_FILE="$DATA_DIR/frpc.log"
WEBUI="$MODDIR/webui.sh"
WEB_LOG="$DATA_DIR/web.log"
WEB_PID_FILE="$DATA_DIR/web.pid"
WEB_PORT_FILE="$DATA_DIR/web_port"
PID_FILE="$DATA_DIR/frpc.pid"
DEFAULTS_FILE="$DATA_DIR/.defaults_v312_done"

mkdir -p "$DATA_DIR"
[ -f "$CONFIG" ] || cp -f "$DEFAULT_CONFIG" "$CONFIG" 2>/dev/null
chmod 644 "$CONFIG" 2>/dev/null

# Do not pre-fill the server port on fresh/default configs.
if [ -f "$CONFIG" ] && grep -q '^serverAddr[[:space:]]*=[[:space:]]*""' "$CONFIG" 2>/dev/null && grep -q '^serverPort[[:space:]]*=[[:space:]]*7000' "$CONFIG" 2>/dev/null; then
  sed -i '/^serverPort[[:space:]]*=[[:space:]]*7000/d' "$CONFIG" 2>/dev/null
fi
if [ ! -f "$DEFAULTS_FILE" ]; then
  if [ -f "$CONFIG" ] && grep -q '^user[[:space:]]*=[[:space:]]*"F50"' "$CONFIG" 2>/dev/null; then
    sed -i 's/^user[[:space:]]*=[[:space:]]*"F50"/user = "zyh"/' "$CONFIG" 2>/dev/null
  fi
  if [ ! -f "$DELAY_FILE" ] || [ "$(cat "$DELAY_FILE" 2>/dev/null | head -n 1)" = "30" ]; then
    echo "10" > "$DELAY_FILE" 2>/dev/null
    chmod 644 "$DELAY_FILE" 2>/dev/null
  fi
  echo "1" > "$DEFAULTS_FILE" 2>/dev/null
  chmod 644 "$DEFAULTS_FILE" 2>/dev/null
fi

WATCH_INTERVAL=5
START_DELAY=10
NOT_READY_COUNTER=0

is_number() {
  case "$1" in
    *[!0-9]*|"") return 1 ;;
    *) return 0 ;;
  esac
}

get_timezone() {

  TZ_FILE="$MODDIR/zoneinfo/Asia/Shanghai"
  if [ -f "$TZ_FILE" ]; then
    TZ_VALUE="$TZ_FILE"
  else
    TZ_VALUE="Asia/Shanghai"
  fi
  echo "$TZ_VALUE" > "$TIMEZONE_FILE" 2>/dev/null
  chmod 644 "$TIMEZONE_FILE" 2>/dev/null
  echo "$TZ_VALUE"
}

apply_timezone() {
  export TZ="$(get_timezone)"
}

rotate_service_log() {
  [ -f "$SERVICE_LOG" ] || return
  SIZE="$(wc -c < "$SERVICE_LOG" 2>/dev/null)"
  is_number "$SIZE" || return
  if [ "$SIZE" -gt 262144 ]; then
    mv "$SERVICE_LOG" "$SERVICE_LOG.1" 2>/dev/null
    : > "$SERVICE_LOG"
  fi
}

shell_ts() {
  TZ=CST-8 date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "0000-00-00 00:00:00"
}

log_msg() {
  rotate_service_log
  echo "$(shell_ts) $1" >> "$SERVICE_LOG"
}

pid_alive() {
  P="$1"
  [ -n "$P" ] || return 1
  [ -d "/proc/$P" ] || return 1
  [ -r "/proc/$P/cmdline" ] || return 1
  CMDLINE="$(tr '\000' ' ' < "/proc/$P/cmdline" 2>/dev/null)"
  case "$CMDLINE" in
    *"$frpc"*"-c $CONFIG"*|*"$frpc"*" -c "*"/data/adb/frpc/frpc.toml"*) return 0 ;;
  esac
  return 1
}

get_pid_quick() {
  if [ -f "$PID_FILE" ]; then
    P="$(cat "$PID_FILE" 2>/dev/null | head -n 1)"
    if pid_alive "$P"; then
      echo "$P"
      return 0
    fi
    rm -f "$PID_FILE" 2>/dev/null
  fi
  if command -v pidof >/dev/null 2>&1; then
    for P in $(pidof frpc 2>/dev/null); do
      if pid_alive "$P"; then
        echo "$P" > "$PID_FILE" 2>/dev/null
        echo "$P"
        return 0
      fi
    done
  fi
  return 1
}

get_pid() {

  PID_NOW="$(get_pid_quick 2>/dev/null)"
  if [ -n "$PID_NOW" ]; then
    echo "$PID_NOW"
    return 0
  fi
  if command -v pgrep >/dev/null 2>&1; then
    for P in $(pgrep -x frpc 2>/dev/null); do
      if pid_alive "$P"; then
        echo "$P" > "$PID_FILE" 2>/dev/null
        echo "$P"
        return 0
      fi
    done
    P="$(pgrep -f "$frpc.*-c $CONFIG" 2>/dev/null | head -n 1)"
    if [ -n "$P" ] && pid_alive "$P"; then
      echo "$P" > "$PID_FILE" 2>/dev/null
      echo "$P"
      return 0
    fi
  fi
  return 1
}

get_server_addr() {
  [ -f "$CONFIG" ] || return
  sed -n 's/^serverAddr[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "$CONFIG" | head -n 1
}

get_server_port() {
  [ -f "$CONFIG" ] || return
  sed -n 's/^serverPort[[:space:]]*=[[:space:]]*\([0-9]*\).*/\1/p' "$CONFIG" | head -n 1
}

get_proxy_count() {
  [ -f "$CONFIG" ] || { echo 0; return; }
  grep -c '^\[\[proxies\]\]' "$CONFIG" 2>/dev/null
}

ensure_frpc() {
  if [ -f "$frpc" ]; then
    chmod 755 "$frpc" 2>/dev/null
    return 0
  fi
  echo "frpc 文件不存在：$frpc"
  return 1
}

ready_reason() {
  ensure_frpc || return
  [ -f "$CONFIG" ] || { echo "配置文件不存在：$CONFIG"; return; }
  [ -n "$(get_server_addr)" ] || { echo "serverAddr 未配置"; return; }
  [ -n "$(get_server_port)" ] || { echo "serverPort 未配置"; return; }
  [ "$(get_proxy_count)" -gt 0 ] || { echo "代理未配置"; return; }
  echo "ready"
}

ready_to_start() {
  [ "$(ready_reason)" = "ready" ]
}

log_not_ready() {
  NOT_READY_COUNTER=$((NOT_READY_COUNTER + 1))
  if [ "$NOT_READY_COUNTER" -eq 1 ] || [ "$NOT_READY_COUNTER" -ge 10 ]; then
    REASON="$(ready_reason)"
    log_msg "frpc 暂未启动：$REASON"
    NOT_READY_COUNTER=1
  fi
}

start_frpc() {
  if [ -f "$CONTROL_FILE" ]; then
    log_msg "frpc 已手动关闭，不启动"
    return 1
  fi
  if ! ready_to_start; then
    log_not_ready
    return 1
  fi
  PID="$(get_pid)"
  [ -n "$PID" ] && return 0
  apply_timezone
  chmod 755 "$frpc" 2>/dev/null
  touch "$LOG_FILE" 2>/dev/null
  chmod 644 "$LOG_FILE" 2>/dev/null
  nohup "$frpc" -c "$CONFIG" >> "$LOG_FILE" 2>&1 &
  NEWPID="$!"
  echo "$NEWPID" > "$PID_FILE" 2>/dev/null
  sleep 2
  PID="$(get_pid)"
  if [ -n "$PID" ]; then
    log_msg "frpc 已启动，PID: $PID"
    NOT_READY_COUNTER=0
  else
    rm -f "$PID_FILE" 2>/dev/null
    log_msg "frpc 启动失败，请查看 /data/adb/frpc/frpc.log"
  fi
  update_module_prop
}

stop_frpc() {
  PID="$(get_pid)"
  if [ -n "$PID" ]; then
    kill "$PID" 2>/dev/null
    sleep 1
    PID2="$(get_pid)"
    [ -n "$PID2" ] && kill -9 "$PID2" 2>/dev/null
  fi
  rm -f "$PID_FILE" 2>/dev/null
  update_module_prop
}

get_web_port() {
  PORT="62930"
  if [ -f "$WEB_PORT_FILE" ]; then
    TMP_PORT="$(cat "$WEB_PORT_FILE" 2>/dev/null | head -n 1)"
    if is_number "$TMP_PORT"; then PORT="$TMP_PORT"; fi
  fi
  echo "$PORT"
}

web_pid_alive() {
  P="$1"
  [ -n "$P" ] || return 1
  [ -r "/proc/$P/cmdline" ] || return 1
  CMDLINE="$(tr '\000' ' ' < "/proc/$P/cmdline" 2>/dev/null)"
  case "$CMDLINE" in
    *"$WEBUI"*|*httpd*"/data/adb/frpc/web/www"*) return 0 ;;
  esac
  return 1
}

get_webui_pid() {
  if [ -f "$WEB_PID_FILE" ]; then
    P="$(cat "$WEB_PID_FILE" 2>/dev/null | head -n 1)"
    if web_pid_alive "$P"; then
      echo "$P"
      return 0
    fi
    rm -f "$WEB_PID_FILE" 2>/dev/null
  fi
  for p in /proc/[0-9]*; do
    [ -r "$p/cmdline" ] || continue
    CMDLINE="$(tr '\000' ' ' < "$p/cmdline" 2>/dev/null)"
    case "$CMDLINE" in
      *"$WEBUI"*|*httpd*"/data/adb/frpc/web/www"*) echo "${p##*/}" > "$WEB_PID_FILE" 2>/dev/null; echo "${p##*/}"; return 0 ;;
    esac
  done
  return 1
}

start_webui() {
  [ -f "$WEBUI" ] || return 1
  PID="$(get_webui_pid)"
  [ -n "$PID" ] && return 0
  nohup sh "$WEBUI" >/dev/null 2>&1 &
  sleep 1
  PID="$(get_webui_pid)"
  if [ -n "$PID" ]; then
    log_msg "web 控制台已启动：http://127.0.0.1:$(get_web_port)"
  else
    log_msg "web 控制台启动失败，请查看 $WEB_LOG"
  fi
}

stop_webui() {
  PID="$(get_webui_pid)"
  [ -n "$PID" ] && kill "$PID" 2>/dev/null && sleep 1
  for p in /proc/[0-9]*; do
    [ -r "$p/cmdline" ] || continue
    CMDLINE="$(tr '\000' ' ' < "$p/cmdline" 2>/dev/null)"
    case "$CMDLINE" in
      *"$WEBUI"*|*httpd*"/data/adb/frpc/web/www"*) kill -9 "${p##*/}" 2>/dev/null ;;
    esac
  done
}

get_config_mark() {
  if [ -f "$CONFIG" ]; then
    ls -l "$CONFIG" 2>/dev/null | awk '{print $5":"$6":"$7":"$8}'
  else
    echo "none"
  fi
}

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

if [ -f "$DELAY_FILE" ]; then START_DELAY="$(cat "$DELAY_FILE" 2>/dev/null)"; fi
is_number "$START_DELAY" || START_DELAY=10

if [ -f "$LOW_MEM_FILE" ]; then
  log_msg "service.sh 启动，最小内存模式已开启，不启动 web 控制台；frpc 开机延迟 ${START_DELAY} 秒"
  stop_webui
else
  log_msg "service.sh 启动，优先启动 web 控制台；frpc 开机延迟 ${START_DELAY} 秒"
  start_webui
fi

[ "$START_DELAY" -gt 0 ] && sleep "$START_DELAY"

LAST_MARK="$(get_config_mark)"

update_module_prop

if [ -f "$CONTROL_FILE" ]; then
  log_msg "frpc 已手动关闭，等待 web 控制台开启"
else
  start_frpc
fi
update_module_prop

while true; do
  sleep "$WATCH_INTERVAL"
  if [ -f "$MODDIR/disable" ]; then
    log_msg "检测到模块已禁用，停止 frpc 和 web 控制台"
    stop_frpc
    stop_webui
    update_module_prop
    exit 0
  fi
  if [ -f "$LOW_MEM_FILE" ]; then
    if [ -n "$(get_webui_pid)" ]; then
      log_msg "最小内存模式已开启，关闭 web 控制台"
      stop_webui
    fi
  else
    if [ -z "$(get_webui_pid)" ]; then start_webui; fi
  fi
  if [ -f "$CONTROL_FILE" ]; then
    PID="$(get_pid)"
    if [ -n "$PID" ]; then
      log_msg "检测到手动关闭标记，停止 frpc"
      stop_frpc
    fi
    LAST_MARK="$(get_config_mark)"
    continue
  fi
  CURRENT_MARK="$(get_config_mark)"
  if [ "$CURRENT_MARK" != "$LAST_MARK" ]; then
    log_msg "检测到配置变化，仅记录变化，不自动启动或重启 frpc"
    LAST_MARK="$CURRENT_MARK"
  fi
  if ! ready_to_start; then
    log_not_ready
    continue
  fi
  PID="$(get_pid)"
  if [ -z "$PID" ]; then
    log_msg "检测到 frpc 异常退出，自动重启"
    start_frpc
  fi
done
