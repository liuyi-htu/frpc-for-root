#!/system/bin/sh

MODDIR="/data/adb/modules/frpc"
frpc="$MODDIR/frpc"
DATA_DIR="/data/adb/frpc"
CONFIG="$DATA_DIR/frpc.toml"
DEFAULT_CONFIG="$MODDIR/frpc.toml"
UPDATE_SCRIPT="$MODDIR/update_frpc.sh"
PID_FILE="$DATA_DIR/frpc.pid"
LOG_FILE="$DATA_DIR/frpc.log"
SERVICE_LOG="$DATA_DIR/service.log"
UPDATE_LOG="$DATA_DIR/update.log"
WEB_LOG="$DATA_DIR/web.log"
CONTROL_FILE="$DATA_DIR/disabled"
LOW_MEM_FILE="$DATA_DIR/low_memory_mode"
WEBUI="$MODDIR/webui.sh"
WEB_ROOT="$DATA_DIR/web/www"
WEB_PID_FILE="$DATA_DIR/web.pid"
TIMEZONE_FILE="$DATA_DIR/timezone"
PORT_FILE="$DATA_DIR/web_port"
BIND_FILE="$DATA_DIR/web_bind"
AUTH_FILE="$DATA_DIR/web_auth.conf"
SESSION_DIR="$DATA_DIR/web_sessions"
DEFAULT_PORT="62930"
DEFAULT_BIND="0.0.0.0"
DEFAULTS_FILE="$DATA_DIR/.defaults_v312_done"
COOKIE_NAME="frpc_session"
SESSION_TTL="86400"

mkdir -p "$DATA_DIR" "$SESSION_DIR"
[ -f "$CONFIG" ] || cp -f "$DEFAULT_CONFIG" "$CONFIG" 2>/dev/null
chmod 644 "$CONFIG" 2>/dev/null
chmod 700 "$SESSION_DIR" 2>/dev/null

if [ -f "$CONFIG" ] && grep -q '^serverAddr[[:space:]]*=[[:space:]]*""' "$CONFIG" 2>/dev/null && grep -q '^serverPort[[:space:]]*=[[:space:]]*7000' "$CONFIG" 2>/dev/null; then
  sed -i '/^serverPort[[:space:]]*=[[:space:]]*7000/d' "$CONFIG" 2>/dev/null
fi
if [ ! -f "$DEFAULTS_FILE" ]; then
  if [ -f "$CONFIG" ] && grep -q '^user[[:space:]]*=[[:space:]]*"F50"' "$CONFIG" 2>/dev/null; then
    sed -i 's/^user[[:space:]]*=[[:space:]]*"F50"/user = "user"/' "$CONFIG" 2>/dev/null
  fi
  if [ ! -f "$DATA_DIR/start_delay" ] || [ "$(cat "$DATA_DIR/start_delay" 2>/dev/null | head -n 1)" = "30" ]; then
    echo "10" > "$DATA_DIR/start_delay" 2>/dev/null
    chmod 644 "$DATA_DIR/start_delay" 2>/dev/null
  fi
  echo "1" > "$DEFAULTS_FILE" 2>/dev/null
  chmod 644 "$DEFAULTS_FILE" 2>/dev/null
fi

BODY_READ=0
POST_BODY=""

is_number() {
  case "$1" in
    *[!0-9]*|"") return 1 ;;
    *) return 0 ;;
  esac
}

get_port() {
  PORT="$DEFAULT_PORT"
  if [ -f "$PORT_FILE" ]; then
    TMP_PORT="$(cat "$PORT_FILE" 2>/dev/null | head -n 1)"
    if is_number "$TMP_PORT"; then
      PORT="$TMP_PORT"
    fi
  fi
  echo "$PORT"
}

get_bind() {
  BIND="$DEFAULT_BIND"
  if [ -f "$BIND_FILE" ]; then
    TMP_BIND="$(cat "$BIND_FILE" 2>/dev/null | head -n 1)"
    case "$TMP_BIND" in
      127.0.0.1|0.0.0.0) BIND="$TMP_BIND" ;;
    esac
  fi
  echo "$BIND"
}

html_escape() {
  sed 's/\&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g'
}

urldecode() {
  printf '%b' "$(printf '%s' "$1" | sed 's/+/ /g; s/%/\\x/g')"
}

read_body() {
  if [ "$BODY_READ" != "1" ]; then
    LEN="${CONTENT_LENGTH:-0}"
    if ! is_number "$LEN"; then LEN=0; fi
    POST_BODY="$(dd bs=1 count="$LEN" 2>/dev/null)"
    BODY_READ=1
  fi
}

get_query_value() {
  KEY="$1"
  printf '%s' "${QUERY_STRING:-}" | tr '&' '\n' | sed -n "s/^${KEY}=//p" | head -n 1
}

get_post_value() {
  KEY="$1"
  read_body
  printf '%s' "$POST_BODY" | tr '&' '\n' | sed -n "s/^${KEY}=//p" | head -n 1
}

get_param() {
  KEY="$1"
  RAW="$(get_post_value "$KEY")"
  if [ -z "$RAW" ]; then
    RAW="$(get_query_value "$KEY")"
  fi
  urldecode "$RAW"
}

hash_password() {
  PASS="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$PASS" | sha256sum 2>/dev/null | awk '{print $1}'
    return
  fi
  if command -v toybox >/dev/null 2>&1; then
    printf '%s' "$PASS" | toybox sha256sum 2>/dev/null | awk '{print $1}'
    return
  fi
  echo ""
}

valid_username() {
  case "$1" in
    ""|*[!A-Za-z0-9._-]*) return 1 ;;
    *) return 0 ;;
  esac
}

migrate_default_auth() {
  [ -f "$AUTH_FILE" ] || return 0
  AUTH_USER_OLD="$(sed -n '1p' "$AUTH_FILE" 2>/dev/null | head -n 1)"
  AUTH_SECRET_OLD="$(sed -n '2p' "$AUTH_FILE" 2>/dev/null | head -n 1)"
  [ "$AUTH_USER_OLD" = "admin" ] || return 0
  case "$AUTH_SECRET_OLD" in
    P:admin)
      rm -f "$AUTH_FILE" 2>/dev/null
      return 0
      ;;
    H:*)
      DEFAULT_HASH="$(hash_password admin)"
      if [ -n "$DEFAULT_HASH" ] && [ "${AUTH_SECRET_OLD#H:}" = "$DEFAULT_HASH" ]; then
        rm -f "$AUTH_FILE" 2>/dev/null
      fi
      ;;
  esac
  return 0
}

init_auth() {
  migrate_default_auth
  return 0
}

get_auth_user() {
  migrate_default_auth
  sed -n '1p' "$AUTH_FILE" 2>/dev/null | head -n 1
}

get_auth_secret() {
  migrate_default_auth
  sed -n '2p' "$AUTH_FILE" 2>/dev/null | head -n 1
}

auth_configured() {
  migrate_default_auth
  [ -f "$AUTH_FILE" ] || return 1
  AUTH_USER_NOW="$(sed -n '1p' "$AUTH_FILE" 2>/dev/null | head -n 1)"
  AUTH_SECRET_NOW="$(sed -n '2p' "$AUTH_FILE" 2>/dev/null | head -n 1)"
  valid_username "$AUTH_USER_NOW" || return 1
  case "$AUTH_SECRET_NOW" in
    H:?*|P:?*) return 0 ;;
    *) return 1 ;;
  esac
}

write_auth() {
  NEW_USER="$1"
  NEW_PASS="$2"
  valid_username "$NEW_USER" || return 1
  [ -n "$NEW_PASS" ] || return 1
  HASH="$(hash_password "$NEW_PASS")"
  if [ -n "$HASH" ]; then
    {
      echo "$NEW_USER"
      echo "H:$HASH"
    } > "$AUTH_FILE"
  else
    {
      echo "$NEW_USER"
      echo "P:$NEW_PASS"
    } > "$AUTH_FILE"
  fi
  chmod 600 "$AUTH_FILE" 2>/dev/null
  return 0
}

verify_password() {
  auth_configured || return 1
  USER_IN="$1"
  PASS_IN="$2"
  AUTH_USER="$(get_auth_user)"
  AUTH_SECRET="$(get_auth_secret)"
  [ "$USER_IN" = "$AUTH_USER" ] || return 1
  case "$AUTH_SECRET" in
    H:*)
      HASH_STORED="${AUTH_SECRET#H:}"
      HASH_NOW="$(hash_password "$PASS_IN")"
      [ -n "$HASH_NOW" ] && [ "$HASH_NOW" = "$HASH_STORED" ]
      ;;
    P:*)
      [ "$PASS_IN" = "${AUTH_SECRET#P:}" ]
      ;;
    *)
      return 1
      ;;
  esac
}

make_token() {
  if [ -r /proc/sys/kernel/random/uuid ]; then
    cat /proc/sys/kernel/random/uuid 2>/dev/null | tr -d '\n-'
    return
  fi
  if command -v od >/dev/null 2>&1; then
    od -An -N24 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n'
    return
  fi
  echo "$(date +%s 2>/dev/null)$$"
}

valid_token() {
  case "$1" in
    ""|*[!A-Za-z0-9._-]*) return 1 ;;
    *) return 0 ;;
  esac
}

get_cookie_token() {
  printf '%s' "${HTTP_COOKIE:-}" | tr ';' '\n' | sed 's/^ *//' | sed -n "s/^${COOKIE_NAME}=//p" | head -n 1
}

now_epoch() {
  date +%s 2>/dev/null || echo 0
}

clear_expired_sessions() {
  NOW="$(now_epoch)"
  is_number "$NOW" || return 0
  for SFILE in "$SESSION_DIR"/*; do
    [ -f "$SFILE" ] || continue
    TS="$(sed -n '2p' "$SFILE" 2>/dev/null | head -n 1)"
    is_number "$TS" || { rm -f "$SFILE" 2>/dev/null; continue; }
    AGE=$((NOW - TS))
    [ "$AGE" -gt "$SESSION_TTL" ] 2>/dev/null && rm -f "$SFILE" 2>/dev/null
  done
}

current_session_user() {
  TOKEN="$(get_cookie_token)"
  valid_token "$TOKEN" || return 1
  SFILE="$SESSION_DIR/$TOKEN"
  [ -f "$SFILE" ] || return 1
  USER_LINE="$(sed -n '1p' "$SFILE" 2>/dev/null | head -n 1)"
  TS="$(sed -n '2p' "$SFILE" 2>/dev/null | head -n 1)"
  NOW="$(now_epoch)"
  is_number "$TS" || { rm -f "$SFILE" 2>/dev/null; return 1; }
  is_number "$NOW" || return 1
  AGE=$((NOW - TS))
  if [ "$AGE" -gt "$SESSION_TTL" ] 2>/dev/null || [ "$AGE" -lt 0 ] 2>/dev/null; then
    rm -f "$SFILE" 2>/dev/null
    return 1
  fi
  echo "$USER_LINE"
}

is_authed() {
  auth_configured || return 0
  USER_NOW="$(current_session_user)" || return 1
  [ -n "$USER_NOW" ] || return 1
  [ "$USER_NOW" = "$(get_auth_user)" ] || return 1
  return 0
}

create_session() {
  USER_IN="$1"
  clear_expired_sessions
  TOKEN="$(make_token)"
  valid_token "$TOKEN" || TOKEN="$(date +%s 2>/dev/null)$$"
  NOW="$(now_epoch)"
  {
    echo "$USER_IN"
    echo "$NOW"
  } > "$SESSION_DIR/$TOKEN"
  chmod 600 "$SESSION_DIR/$TOKEN" 2>/dev/null
  echo "$TOKEN"
}

clear_sessions() {
  rm -f "$SESSION_DIR"/* 2>/dev/null
}

print_header() {
  echo "Content-Type: text/html; charset=UTF-8"
  echo "Cache-Control: no-store"
  echo ""
}

print_header_cookie() {
  COOKIE_LINE="$1"
  echo "Content-Type: text/html; charset=UTF-8"
  echo "Cache-Control: no-store"
  [ -n "$COOKIE_LINE" ] && echo "Set-Cookie: $COOKIE_LINE"
  echo ""
}

apply_timezone() {
  TZ_FILE="$MODDIR/zoneinfo/Asia/Shanghai"
  if [ -f "$TZ_FILE" ]; then
    TZ_VALUE="$TZ_FILE"
  else
    TZ_VALUE="Asia/Shanghai"
  fi
  echo "$TZ_VALUE" > "$TIMEZONE_FILE" 2>/dev/null
  chmod 644 "$TIMEZONE_FILE" 2>/dev/null
  export TZ="$TZ_VALUE"
}

shell_ts() {
  TZ=CST-8 date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "0000-00-00 00:00:00"
}

log_msg() {
  echo "$(shell_ts) $1" >> "$SERVICE_LOG"
}

pid_alive() {
  P="$1"
  [ -n "$P" ] || return 1
  [ -r "/proc/$P/cmdline" ] || return 1
  CMDLINE="$(tr '\000' ' ' < "/proc/$P/cmdline" 2>/dev/null)"
  case "$CMDLINE" in
    *"$frpc"*"-c $CONFIG"*|*"$frpc"*" -c "*"/data/adb/frpc/frpc.toml"*) return 0 ;;
  esac
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

get_user() {
  [ -f "$CONFIG" ] || return
  sed -n 's/^user[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "$CONFIG" | head -n 1
}

get_dns_server() {
  [ -f "$CONFIG" ] || return
  sed -n 's/^dnsServer[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "$CONFIG" | head -n 1
}

get_token() {
  [ -f "$CONFIG" ] || return
  sed -n 's/^auth\.token[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "$CONFIG" | head -n 1
}

get_log_level() {
  [ -f "$CONFIG" ] || return
  sed -n 's/^log\.level[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "$CONFIG" | head -n 1
}

get_log_max_days() {
  [ -f "$CONFIG" ] || return
  sed -n 's/^log\.maxDays[[:space:]]*=[[:space:]]*\([0-9]*\).*/\1/p' "$CONFIG" | head -n 1
}

get_start_delay() {
  DELAY="10"
  if [ -f "$DATA_DIR/start_delay" ]; then
    TMP="$(cat "$DATA_DIR/start_delay" 2>/dev/null | head -n 1)"
    is_number "$TMP" && DELAY="$TMP"
  fi
  echo "$DELAY"
}

toml_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

valid_port() {
  is_number "$1" || return 1
  [ "$1" -ge 1 ] 2>/dev/null || return 1
  [ "$1" -le 65535 ] 2>/dev/null || return 1
  return 0
}

list_proxies_tsv() {
  if [ ! -f "$CONFIG" ] || [ "$(get_proxy_count)" -eq 0 ]; then
    return
  fi
  awk '
  BEGIN { idx=0; name="-"; type="-"; localIP="-"; localPort="-"; remotePort="-"; domain="-" }
  function clean(v) { sub(/^[^=]*=[[:space:]]*/, "", v); gsub(/"/, "", v); gsub(/\[/, "", v); gsub(/\]/, "", v); return v }
  function flush() { if (idx > 0) { printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n", idx, name, type, localIP, localPort, remotePort, domain } }
  /^\[\[proxies\]\]/ { flush(); idx++; name="-"; type="-"; localIP="-"; localPort="-"; remotePort="-"; domain="-"; next }
  /^name[[:space:]]*=/ { name=clean($0); next }
  /^type[[:space:]]*=/ { type=clean($0); next }
  /^localIP[[:space:]]*=/ { localIP=clean($0); next }
  /^localPort[[:space:]]*=/ { localPort=clean($0); next }
  /^remotePort[[:space:]]*=/ { remotePort=clean($0); next }
  /^customDomains[[:space:]]*=/ { domain=clean($0); next }
  END { flush() }
  ' "$CONFIG"
}

show_proxy_list_html() {
  SHOW_DELETE="$1"
  if [ ! -f "$CONFIG" ] || [ "$(get_proxy_count)" -eq 0 ]; then
    echo '<div class="proxy-empty">当前没有代理。</div>'
    return
  fi
  echo '<div class="proxy-list">'
  while IFS='	' read -r idx name type localIP localPort remotePort domain; do
    [ -n "$idx" ] || continue
    label="远端端口"
    target="$remotePort"
    if [ -z "$target" ] || [ "$target" = "-" ]; then
      label="绑定域名"
      target="$domain"
    fi
    safe_idx="$(printf '%s' "$idx" | html_escape)"
    safe_name="$(printf '%s' "$name" | html_escape)"
    safe_type="$(printf '%s' "$type" | html_escape)"
    safe_local="$(printf '%s:%s' "$localIP" "$localPort" | html_escape)"
    safe_target="$(printf '%s' "$target" | html_escape)"
    safe_label="$(printf '%s' "$label" | html_escape)"
    cat <<HTML
<div class="proxy-box">
  <div class="proxy-title"><span>序号 $safe_idx</span><strong>$safe_name</strong></div>
  <div class="proxy-row"><span class="proxy-key">类型</span><span class="proxy-val">$safe_type</span></div>
  <div class="proxy-row"><span class="proxy-key">本地</span><span class="proxy-val">$safe_local</span></div>
  <div class="proxy-row"><span class="proxy-key">$safe_label</span><span class="proxy-val">$safe_target</span></div>
HTML
    if [ "$SHOW_DELETE" = "delete" ]; then
      cat <<HTML
  <form class="proxy-delete-form" method="post" action="/cgi-bin/frpc.cgi?action=delete_proxy">
    <input type="hidden" name="proxy_index" value="$safe_idx">
    <button class="btn bad" type="submit">删除</button>
  </form>
HTML
    fi
    cat <<HTML
</div>
HTML
  done <<EOF
$(list_proxies_tsv)
EOF
  echo '</div>'
}


preserve_proxies() {
  TMP="$DATA_DIR/.proxies.tmp"
  if [ -f "$CONFIG" ]; then
    awk 'BEGIN{p=0} /^\[\[proxies\]\]/{p=1} p{print}' "$CONFIG" > "$TMP"
  else
    : > "$TMP"
  fi
}

append_preserved_proxies() {
  TMP="$DATA_DIR/.proxies.tmp"
  [ -f "$TMP" ] && cat "$TMP" >> "$CONFIG"
  rm -f "$TMP" 2>/dev/null
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

get_pid_quick() {
  # 页面状态走轻量检测：PID 文件 + pidof，不做 /proc 全量扫描。
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

start_frpc() {
  PID="$(get_pid 2>/dev/null)"
  if [ -n "$PID" ]; then
    echo "frpc 已经在运行，PID: $PID"
    return 0
  fi
  REASON="$(ready_reason)"
  if [ "$REASON" != "ready" ]; then
    log_msg "webUI 启动失败：$REASON"
    echo "启动失败：$REASON"
    return 1
  fi
  apply_timezone
  chmod 755 "$frpc" 2>/dev/null
  nohup "$frpc" -c "$CONFIG" >> "$LOG_FILE" 2>&1 &
  NEWPID="$!"
  echo "$NEWPID" > "$PID_FILE" 2>/dev/null
  sleep 1
  PID="$(get_pid 2>/dev/null)"
  if [ -n "$PID" ]; then
    log_msg "webUI 已启动 frpc，PID: $PID"
    echo "frpc 已启动，PID: $PID"
    return 0
  fi
  log_msg "webUI 已发送启动 frpc，临时 PID: $NEWPID"
  echo "启动命令已发送，请稍后刷新状态或查看日志。"
  return 0
}

stop_frpc() {
  PID="$(get_pid_quick)"
  rm -f "$PID_FILE" 2>/dev/null
  (
    [ -n "$PID" ] && kill "$PID" 2>/dev/null
    if command -v pkill >/dev/null 2>&1; then
      pkill -f "$frpc.*-c $CONFIG" 2>/dev/null
    else
      for p in /proc/[0-9]*; do
        [ -r "$p/cmdline" ] || continue
        CMDLINE="$(tr '\000' ' ' < "$p/cmdline" 2>/dev/null)"
        case "$CMDLINE" in
          *"$frpc"*"-c $CONFIG"*|*"$frpc"*" -c "*"/data/adb/frpc/frpc.toml"*) kill "${p##*/}" 2>/dev/null ;;
        esac
      done
    fi
    sleep 0.2
    [ -n "$PID" ] && pid_alive "$PID" && kill -9 "$PID" 2>/dev/null
    rm -f "$PID_FILE" 2>/dev/null
  ) >/dev/null 2>&1 &
  log_msg "webUI 已发送停止 frpc"
  echo "停止命令已发送。"
}

web_pid_alive() {
  P="$1"
  [ -n "$P" ] || return 1
  [ -r "/proc/$P/cmdline" ] || return 1
  CMDLINE="$(tr '\000' ' ' < "/proc/$P/cmdline" 2>/dev/null)"
  case "$CMDLINE" in
    *"$WEBUI"*|*httpd*"$WEB_ROOT"*) return 0 ;;
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
      *"$WEBUI"*|*httpd*"$WEB_ROOT"*) echo "${p##*/}" > "$WEB_PID_FILE" 2>/dev/null; echo "${p##*/}"; return 0 ;;
    esac
  done
  return 1
}

stop_webui_now() {
  PID="$(get_webui_pid)"
  [ -n "$PID" ] && kill "$PID" 2>/dev/null && sleep 1
  for p in /proc/[0-9]*; do
    [ -r "$p/cmdline" ] || continue
    CMDLINE="$(tr '\000' ' ' < "$p/cmdline" 2>/dev/null)"
    case "$CMDLINE" in
      *"$WEBUI"*|*httpd*"$WEB_ROOT"*) kill -9 "${p##*/}" 2>/dev/null ;;
    esac
  done
}

stop_webui_delayed() {
  ( sleep 2; stop_webui_now ) >/dev/null 2>&1 &
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

quick_status() {
  echo "Content-Type: text/plain; charset=UTF-8"
  echo "Cache-Control: no-store"
  echo ""
  PID_NOW="$(get_pid_quick 2>/dev/null)"
  if [ -n "$PID_NOW" ]; then
    echo "运行中"
    return 0
  fi
  if [ -f "$CONTROL_FILE" ]; then
    echo "已停止"
  else
    echo "未运行"
  fi
}

running_proxies() {
  echo "Content-Type: text/html; charset=UTF-8"
  echo "Cache-Control: no-store"
  echo ""
  PID="$(get_pid_quick 2>/dev/null)"
  [ -n "$PID" ] || return 0
  if [ ! -f "$CONFIG" ] || [ "$(get_proxy_count)" -eq 0 ]; then
    return 0
  fi
  echo '<div class="card" id="runningProxyCard">'
  echo '<h3>运行中的代理</h3>'
  show_proxy_list_html delete
  echo '</div>'
}

restart_frpc() {
  rm -f "$CONTROL_FILE" 2>/dev/null
  stop_frpc >/dev/null 2>&1
  start_frpc
}

enable_low_memory() {
  PID="$(get_pid_quick 2>/dev/null)"
  if [ -z "$PID" ]; then
    REASON="$(ready_reason)"
    if [ "$REASON" != "ready" ]; then
      show_status "最小内存运行失败：$REASON"
      return
    fi
    rm -f "$CONTROL_FILE" 2>/dev/null
    MSG="$(start_frpc)"
    PID="$(get_pid_quick 2>/dev/null)"
    if [ -z "$PID" ]; then
      show_status "最小内存运行失败：$MSG"
      return
    fi
  else
    MSG="frpc 已经在运行，PID: $PID"
    rm -f "$CONTROL_FILE" 2>/dev/null
  fi
  echo "1" > "$LOW_MEM_FILE" 2>/dev/null
  chmod 644 "$LOW_MEM_FILE" 2>/dev/null
  update_module_prop
  log_msg "已开启最小内存运行模式：关闭 web 控制台，仅保留 frpc 和轻量守护"
  page_top "最小内存运行"
  cat <<HTML
<div class="card msg">
  <b>已进入最小内存运行模式。</b><br>
  frpc 已启动，PID: $(printf '%s' "$PID" | html_escape)。本页面显示后 web 控制台会自动关闭。
</div>
<div class="card">
  <h3>说明</h3>
  <ul class="info-list">
    <li>该模式只保留 <code>frpc</code> 和轻量守护脚本，关闭 <code>webui.sh/httpd</code>，减少常驻内存。</li>
    <li>守护仍然保留：如果 <code>frpc</code> 异常退出，<code>service.sh</code> 会按 5 秒轮询自动拉起。</li>
    <li>进入该模式后网页后台将无法访问；需要改配置时，在 Magisk/KernelSU/APatch 模块页点击本模块的操作按钮，会退出最小内存模式并恢复 web 控制台。</li>
    <li>也可以手动删除 <code>/data/adb/frpc/low_memory_mode</code> 后重启模块服务。</li>
  </ul>
</div>
HTML
  page_bottom
  stop_webui_delayed
}

disable_low_memory() {
  rm -f "$LOW_MEM_FILE" 2>/dev/null
  update_module_prop
  log_msg "已退出最小内存运行模式，web 控制台保持常驻"
  show_status "已退出最小内存运行模式，web 控制台将保持常驻。"
}

page_top() {
  TITLE="$1"
  print_header
  USER_NOW="$(current_session_user 2>/dev/null)"
  [ -z "$USER_NOW" ] && USER_NOW="未登录"
  RETURN_HTML=""
  if [ "$TITLE" != "frpc 控制台" ]; then
    [ -n "$RETURN_URL" ] || RETURN_URL="/cgi-bin/frpc.cgi"
    [ -n "$RETURN_TEXT" ] || RETURN_TEXT="返回"
    RETURN_HTML="<a class=\"btn secondary top-return\" href=\"$RETURN_URL\">$RETURN_TEXT</a>"
  fi
  cat <<HTML
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$TITLE</title>
<style>
:root{color-scheme:light dark;--bg:#f5f7fb;--card:#fff;--text:#172033;--muted:#657083;--line:#dce3ee;--primary:#2563eb;--ok:#16a34a;--bad:#dc2626;--warn:#ca8a04}
@media (prefers-color-scheme:dark){:root{--bg:#111827;--card:#1f2937;--text:#f3f4f6;--muted:#aeb6c2;--line:#374151;--primary:#60a5fa}}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.45}
.wrap{max-width:960px;margin:0 auto;padding:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;margin:14px 0;box-shadow:0 8px 26px rgba(15,23,42,.06)}
h1{font-size:24px;margin:4px 0 2px}.head{position:relative;padding-right:120px}.top-return{position:absolute;right:16px;top:16px;padding:8px 12px;border-radius:10px}.langbar{position:absolute;right:16px;bottom:16px;display:flex;gap:6px;align-items:center}.lang-toggle{appearance:none;border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:10px;padding:7px 12px;font-size:12px;font-weight:700;cursor:pointer}.sub{color:var(--muted);font-size:13px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.kv{padding:10px;border:1px solid var(--line);border-radius:12px}.k{color:var(--muted);font-size:12px}.v{font-weight:650;word-break:break-all}.btns{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px}.btn{appearance:none;border:0;border-radius:12px;padding:11px 14px;text-decoration:none;background:var(--primary);color:white;font-weight:700;display:inline-block;cursor:pointer}.btn.secondary{background:#64748b}.btn.ok{background:var(--ok)}.btn.bad{background:var(--bad)}.btn.warn{background:var(--warn)}.btn.tip{background:#d4a62d;color:#fff}

.info-list{margin:8px 0 0 18px;padding:0}.info-list li{margin:4px 0}.mode-tag{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:3px 9px;font-size:12px;color:var(--muted);margin-bottom:8px}
pre{white-space:pre-wrap;word-break:break-word;background:rgba(100,116,139,.12);border:1px solid var(--line);border-radius:12px;padding:12px;max-height:68vh;overflow:auto}.msg{border-left:4px solid var(--primary);padding:10px 12px;background:rgba(37,99,235,.12);border-radius:10px}.status-ok{color:var(--ok)}.status-bad{color:var(--bad)}.status-warn{color:var(--warn)}.header-status{font-size:18px;font-weight:800;line-height:1.25;margin:4px 0 6px}.run-status{font-size:22px;font-weight:850;line-height:1.25;margin-bottom:12px}textarea{width:100%;min-height:70vh;border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--card);color:var(--text);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}input,select{width:100%;border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--card);color:var(--text);font-size:15px}.nav a{margin-right:10px;color:var(--primary);text-decoration:none;font-weight:650}.form-row{margin:12px 0}.form-row label{display:block;font-weight:650;margin-bottom:6px}.small{font-size:12px;color:var(--muted)}.proxy-list{display:grid;gap:12px}.proxy-box{background:rgba(100,116,139,.10);border:1px solid var(--line);border-radius:14px;padding:12px}.proxy-title{display:flex;justify-content:space-between;gap:12px;align-items:center;font-weight:700;margin-bottom:8px}.proxy-title span{color:var(--muted);font-weight:650}.proxy-title strong{text-align:right;word-break:break-all}.proxy-row{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:5px 0;border-top:1px dashed rgba(100,116,139,.28)}.proxy-key{color:var(--muted);white-space:nowrap}.proxy-val{text-align:right;word-break:break-all}.proxy-empty{color:var(--muted);padding:8px 0}.proxy-delete-form{margin-top:10px;display:flex;justify-content:flex-end}.proxy-delete-form input{display:none}
@media (max-width:560px){.head{padding-right:16px}.top-return{position:static;margin-bottom:8px}.langbar{position:static;margin-top:10px}
</style>
</head>
<body><div class="wrap">
<div class="card head">
$RETURN_HTML
<h1>frpc 控制台</h1>
<div class="header-status status-warn" id="runStatus">frpc 检测中...</div>
<div class="langbar"><button type="button" id="langToggle" class="lang-toggle" aria-label="Toggle language">中文</button></div>
</div>

<script>
(function(){
  var dict={
    'frpc 控制台':'frpc Web Console',
    'frpc web 控制台':'frpc Web Console',
    'frpc 登录':'frpc Login',
    'frpc 日志':'frpc Logs',
    'frpc 配置':'frpc Configuration',
    '基础设置':'Basic Settings',
    '代理管理':'Proxy Manager',
    '新增代理':'Add Proxy',
    '账号设置':'Account Settings',
    '更新 frpc':'Update frpc',
    '更新 frpc 二进制':'Update frpc Binary',
    'frpc 说明':'frpc Guide',
    '最小内存运行':'Low Memory Mode',
    '返回':'Back',
    '返回账号设置':'Back to Account Settings',
    'frpc 检测中...':'Checking frpc...',
    'frpc 运行中':'frpc Running',
    'frpc 已停止':'frpc Stopped',
    '启动':'Start',
    '停止':'Stop',
    '恢复网页':'Restore Web UI',
    '配置与维护':'Configuration and Maintenance',
    '配置文件':'Configuration File',
    '日志':'Logs',
    '退出登录':'Log Out',
    '赞赏码':'Donation QR Code',
    '长按或截图保存后识别也可以。':'You can also long-press or take a screenshot, then scan it later.',
    '感谢支持！':'Thank you for your support!',
    '恢复后再次打开默认地址：':'After restoring, open the default address again:',
    '模块会退出最小内存模式，并重新拉起 web 控制台。':'The module will exit low memory mode and start the web console again.',
    '需要恢复 web 常驻时：打开 Magisk / KernelSU / APatch 的模块页面，点击本模块的“操作 / Action”按钮。':'To restore resident web mode: open this module page in Magisk / KernelSU / APatch, then tap this module’s “Action” button.',
    '进入最小内存模式后，web 控制台会关闭，无法直接访问。':'After entering low memory mode, the web console is stopped and cannot be accessed directly.',
    '最小内存模式提示':'Low Memory Mode Tip',
    '返回首页点击“启动”；需要排错时查看“日志”。':'Return to the home page and tap “Start”; check “Logs” when troubleshooting.',
    '在“代理管理”添加代理。':'Add proxies in “Proxy Manager”.',
    '在“基础设置”填写服务器信息。':'Fill in server information in “Basic Settings”.',
    '配置保存在 /data/adb/frpc/frpc.toml，升级模块不会覆盖。':'The configuration is stored at /data/adb/frpc/frpc.toml, and module updates will not overwrite it.',
    '支持最小内存运行，稳定后可关闭 web 常驻，减少后台占用。':'Supports low memory mode; after the setup is stable, you can stop the resident web service to reduce background usage.',
    '轻量 web 控制台，支持启动、停止、日志、配置和代理管理。':'Lightweight web console for start, stop, logs, configuration, and proxy management.',
    '如需只允许本机访问，请在 /data/adb/frpc/web_bind 中写入 127.0.0.1，然后重启模块服务。':'To allow only local access, write 127.0.0.1 into /data/adb/frpc/web_bind, then restart the module service.',
    '网页端口默认为 62930；如需修改端口，请编辑 /data/adb/frpc/web_port。':'The default web port is 62930; to change it, edit /data/adb/frpc/web_port.',
    '提示':'Tips',
    '高级配置文件路径':'Advanced Configuration File Path',
    '默认访问地址':'Default Access Address',
    '如需高级手动调整，可在“配置文件”页面直接编辑':'If you need advanced manual adjustments, you can directly edit',
    '如果希望长期稳定运行但尽量减少内存占用，可以在确认配置正常后使用“最小内存运行”。':'If you want long-term stable operation while reducing memory usage as much as possible, use “Low Memory Mode” after confirming that the configuration works normally.',
    '完成配置后返回首页，点击“启动”运行 frpc；如果需要排错，可到“日志”页面查看运行日志。':'After finishing the configuration, return to the home page and click “Start” to run frpc; if you need troubleshooting, open “Logs” to view runtime logs.',
    '进入“代理管理”添加你的代理项目，按需填写代理名称、类型、本地 IP、本地端口、远端端口或绑定域名。':'Open “Proxy Manager” to add your proxy items, and fill in the proxy name, type, local IP, local port, remote port, or custom domain as needed.',
    '进入“基础设置”填写 serverAddr、serverPort、user、dnsServer、log.level 等常用参数。':'Go to “Basic Settings” and fill in common parameters such as serverAddr, serverPort, user, dnsServer, and log.level.',
    '局域网设备访问':'Access from another device on the LAN at',
    '打开网页后台：本机访问':'Open the web panel: access locally at',
    '先安装模块，然后进入“更新 frpc”下载官方 frpc 二进制。':'First install the module, then open “Update frpc” to download the official frpc binary.',
    '网页支持中英文切换，并可按需设置登录账号密码。':'The web panel supports Chinese/English switching and lets you set a login account and password when needed.',
    '配置文件保存在用户目录，升级模块不会覆盖现有配置。':'The configuration file is stored in the user directory, so updating the module will not overwrite your existing configuration.',
    '提供最小内存运行模式；进入后只保留 frpc 与轻量守护，进一步减少常驻资源占用。':'It provides a low memory mode; after entering it, only frpc and a lightweight guard remain running to further reduce resident resource usage.',
    '支持基础设置、代理管理、配置文件编辑、日志查看、账号设置和一键更新。':'It supports basic settings, proxy management, configuration editing, log viewing, account settings, and one-click updates.',
    '界面轻量，打开首页时异步检测运行状态，不拖慢页面加载。':'The interface is lightweight, and the home page checks runtime status asynchronously so page loading stays fast.',
    '使用方法':'How to Use',
    '项目优势':'Project Advantages',
    '保存':'Save',
    '保存基础设置':'Save Basic Settings',
    '添加代理':'Add Proxy',
    '删除':'Delete',
    '清除当前日志':'Clear Current Log',
    '查看 update.log':'View update.log',
    '开始更新':'Start Update',
    '用户名':'Username',
    '密码':'Password',
    '登录':'Log In',
    '当前密码':'Current Password',
    '新用户名':'New Username',
    '新密码':'New Password',
    '再次输入新密码':'Confirm New Password',
    '再次输入密码':'Confirm Password',
    '保存账号设置':'Save Account Settings',
    '修改网页登录账号':'Change Web Login Account',
    '首次设置网页登录账号':'Set Web Login Account',
    '服务器地址 serverAddr':'Server Address serverAddr',
    '服务器端口 serverPort':'Server Port serverPort',
    '用户 user':'User user',
    'DNS 服务器 dnsServer':'DNS Server dnsServer',
    '日志等级 log.level':'Log Level log.level',
    '日志保存天数 log.maxDays':'Log Retention Days log.maxDays',
    '开机延迟启动，单位秒':'Boot Start Delay, seconds',
    '代理类型':'Proxy Type',
    '代理名称':'Proxy Name',
    '本地 IP':'Local IP',
    '本地端口':'Local Port',
    '远端端口':'Remote Port',
    '绑定域名':'Custom Domain',
    '运行中的代理':'Running Proxies',
    '当前没有代理。':'No proxies yet.',
    '类型':'Type',
    '本地':'Local',
    '远端端口':'Remote Port',
    '绑定域名':'Custom Domain',
    '说明':'Guide',
    '精简 web 页面版本说明':'Compact Web UI Notes',
    '语言':'Language',
    '当前 web 后台未设置用户名和密码，默认免登录。建议进入':'No web username or password is set, so login is skipped by default. Please open',
    '后先设置用户名和密码。':'to set a username and password first.',
    '配置文件：/data/adb/frpc/frpc.toml':'Configuration file: /data/adb/frpc/frpc.toml',
    '适合高级手动编辑。':'For advanced manual editing.',
    '这里替代原来的 config.sh。保存后会保留现有代理。':'This replaces the old config.sh. Existing proxies are kept after saving.',
    '留空则不写入 user。':'Leave blank to omit user.',
    '留空则不写入 dnsServer。':'Leave blank to omit dnsServer.',
    '留空则不启用 token。':'Leave blank to disable token.',
    '修改后会退出登录，需要用新账号重新进入。':'After saving, you will be logged out and must sign in again with the new account.',
    '当前 web 后台默认免密码进入。请先设置用户名和密码，保存后会退出并要求重新登录。':'The web panel currently allows password-free access. Set a username and password first; after saving, you will be logged out and asked to log in.',
    '只能使用字母、数字、点、下划线、横线。':'Use only letters, numbers, dots, underscores, and hyphens.',
    '不填则只修改用户名。':'Leave blank to change only the username.',
    '点击后会运行 update_frpc.sh，从 frp 官方开源发布地址下载 frpc。下载失败时模块不会坏，可以查看 update.log。':'This runs update_frpc.sh and downloads frpc from the official open-source frp release. If the download fails, the module is not damaged; check update.log.',
    '已进入最小内存运行模式。':'Low memory mode is enabled.',
    '该模式只保留':'This mode keeps only',
    '和轻量守护脚本，关闭':'and the lightweight guard script, and stops',
    '，减少常驻内存。':'to reduce resident memory.',
    '守护仍然保留：如果':'The guard remains active: if',
    '异常退出，':'exits unexpectedly,',
    '会按 5 秒轮询自动拉起。':'polls every 5 seconds and restarts it automatically.',
    '进入该模式后网页后台将无法访问；需要改配置时，在 Magisk/KernelSU/APatch 模块页点击本模块的操作按钮，会退出最小内存模式并恢复 web 控制台。':'After entering this mode, the web panel cannot be accessed. To change settings, tap this module action button in Magisk/KernelSU/APatch to exit low memory mode and restore the web console.',
    '也可以手动删除':'You can also manually delete',
    '后重启模块服务。':'and then restart the module service.',
    '当前未设置网页登录账号密码，直接进入控制台。':'No web login account is set. Entering the console directly.',
    '登录成功，正在进入控制台。':'Login successful. Entering the console.',
    '已退出。':'Logged out.',
    '账号设置已保存，请用新账号重新登录。':'Account settings saved. Please log in with the new account.'
  };
  var attrDict={
    'example.com 或 IP':'example.com or IP',
    '例如 ssh':'e.g. ssh',
    '例如 22':'e.g. 22',
    '例如 60022':'e.g. 60022',
    '例如 f50.example.com':'e.g. f50.example.com',
    '留空保持当前用户名':'Leave blank to keep current username',
    'trace/debug/info/warn/error':'trace/debug/info/warn/error'
  };
  function getLang(){
    try { return localStorage.getItem('frpc_lang') || 'en'; } catch(e) { return 'en'; }
  }
  function setStoredLang(l){
    try { localStorage.setItem('frpc_lang', l); } catch(e) {}
  }
  function revLookup(obj, value){
    var keys=Object.keys(obj);
    for(var i=0;i<keys.length;i++){ if(obj[keys[i]]===value){return keys[i];} }
    return null;
  }
  function trText(text, lang){
    var key=(text || '').trim();
    if(!key){return text;}
    if(lang==='zh'){
      var original=revLookup(dict, key);
      return original || text;
    }
    return dict[key] || text;
  }
  function trAttr(text, lang){
    var key=(text || '').trim();
    if(!key){return text;}
    if(lang==='zh'){
      var original=revLookup(attrDict, key);
      return original || text;
    }
    return attrDict[key] || text;
  }
  window.frpcT=function(text){return trText(text, getLang());};
  window.frpcApplyLang=function(root){
    var lang=getLang();
    var base=root || document.body;
    document.documentElement.lang=(lang==='zh')?'zh-CN':'en';
    var btn=document.getElementById('langToggle');
    if(btn){btn.textContent=(lang==='zh')?'English':'中文';}
    document.title=trText(document.title, lang);
    if(!base){return;}
    var walker=document.createTreeWalker(base, NodeFilter.SHOW_TEXT, {
      acceptNode:function(node){
        var p=node.parentNode;
        if(!p){return NodeFilter.FILTER_REJECT;}
        var tag=p.nodeName;
        if(tag==='SCRIPT'||tag==='STYLE'||tag==='TEXTAREA'||tag==='PRE'||tag==='CODE'){
          return NodeFilter.FILTER_REJECT;
        }
        return node.nodeValue.trim()?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT;
      }
    });
    var nodes=[], n;
    while((n=walker.nextNode())){nodes.push(n);}
    nodes.forEach(function(node){
      var raw=node.nodeValue;
      var key=raw.trim();
      var start=raw.indexOf(key);
      var lead=start>0?raw.slice(0,start):'';
      var tail=start>=0?raw.slice(start+key.length):'';
      node.nodeValue=lead+trText(raw, lang)+tail;
    });
    if(base.querySelectorAll){
      var fields=base.querySelectorAll('input[placeholder],textarea[placeholder]');
      for(var i=0;i<fields.length;i++){
        fields[i].setAttribute('placeholder', trAttr(fields[i].getAttribute('placeholder'), lang));
      }
    }
  };
  window.frpcSetLang=function(lang){
    lang=(lang==='zh')?'zh':'en';
    setStoredLang(lang);
    window.frpcApplyLang(document.body);
  };
  document.addEventListener('DOMContentLoaded', function(){
    var btn=document.getElementById('langToggle');
    if(btn){btn.onclick=function(){window.frpcSetLang(getLang()==='zh'?'en':'zh');};}
    window.frpcApplyLang(document.body);
  });
})();
</script>
<script>
(function(){
  var el=document.getElementById('runStatus');
  if(!el){return;}
  fetch('/cgi-bin/frpc.cgi?action=quick_status',{cache:'no-store'})
    .then(function(r){return r.text();})
    .then(function(t){
      t=(t||'').trim();
      if(t.indexOf('运行中')>=0){el.textContent=window.frpcT?window.frpcT('frpc 运行中'):'frpc Running'; el.className='header-status status-ok';}
      else{el.textContent=window.frpcT?window.frpcT('frpc 已停止'):'frpc Stopped'; el.className='header-status status-bad';}
    })
    .catch(function(){el.textContent=window.frpcT?window.frpcT('frpc 已停止'):'frpc Stopped'; el.className='header-status status-bad';});
})();
</script>
HTML
  RETURN_URL=""
  RETURN_TEXT=""
}

page_top_noauth() {
  TITLE="$1"
  print_header
  cat <<HTML
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>$TITLE</title>
<style>
:root{color-scheme:light dark;--bg:#f5f7fb;--card:#fff;--text:#172033;--muted:#657083;--line:#dce3ee;--primary:#2563eb;--bad:#dc2626}
@media (prefers-color-scheme:dark){:root{--bg:#111827;--card:#1f2937;--text:#f3f4f6;--muted:#aeb6c2;--line:#374151;--primary:#60a5fa}}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{max-width:440px;margin:0 auto;padding:24px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;margin-top:12vh;box-shadow:0 8px 26px rgba(15,23,42,.06)}h1{font-size:24px;margin:0 0 8px}.sub{color:var(--muted);font-size:13px;margin-bottom:14px}label{display:block;font-weight:650;margin:12px 0 6px}input,select{width:100%;border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--card);color:var(--text);font-size:15px}.btn{appearance:none;border:0;border-radius:12px;padding:12px 14px;text-decoration:none;background:var(--primary);color:white;font-weight:700;display:inline-block;cursor:pointer;width:100%;margin-top:14px}.msg{border-left:4px solid var(--bad);padding:10px 12px;background:rgba(220,38,38,.12);border-radius:10px;margin:12px 0}.ok{border-left-color:#16a34a;background:rgba(22,163,74,.12)}.langbar{display:flex;gap:6px;align-items:center;justify-content:flex-end;margin-bottom:10px}.lang-toggle{appearance:none;border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:10px;padding:7px 12px;font-size:12px;font-weight:700;cursor:pointer}</style>
</head><body><div class="wrap"><div class="card"><div class="langbar"><button type="button" id="langToggle" class="lang-toggle" aria-label="Toggle language">中文</button></div><h1>frpc web 控制台</h1>

<script>
(function(){
  var dict={
    'frpc 控制台':'frpc Web Console',
    'frpc web 控制台':'frpc Web Console',
    'frpc 登录':'frpc Login',
    'frpc 日志':'frpc Logs',
    'frpc 配置':'frpc Configuration',
    '基础设置':'Basic Settings',
    '代理管理':'Proxy Manager',
    '新增代理':'Add Proxy',
    '账号设置':'Account Settings',
    '更新 frpc':'Update frpc',
    '更新 frpc 二进制':'Update frpc Binary',
    'frpc 说明':'frpc Guide',
    '最小内存运行':'Low Memory Mode',
    '返回':'Back',
    '返回账号设置':'Back to Account Settings',
    'frpc 检测中...':'Checking frpc...',
    'frpc 运行中':'frpc Running',
    'frpc 已停止':'frpc Stopped',
    '启动':'Start',
    '停止':'Stop',
    '恢复网页':'Restore Web UI',
    '配置与维护':'Configuration and Maintenance',
    '配置文件':'Configuration File',
    '日志':'Logs',
    '退出登录':'Log Out',
    '赞赏码':'Donation QR Code',
    '长按或截图保存后识别也可以。':'You can also long-press or take a screenshot, then scan it later.',
    '感谢支持！':'Thank you for your support!',
    '恢复后再次打开默认地址：':'After restoring, open the default address again:',
    '模块会退出最小内存模式，并重新拉起 web 控制台。':'The module will exit low memory mode and start the web console again.',
    '需要恢复 web 常驻时：打开 Magisk / KernelSU / APatch 的模块页面，点击本模块的“操作 / Action”按钮。':'To restore resident web mode: open this module page in Magisk / KernelSU / APatch, then tap this module’s “Action” button.',
    '进入最小内存模式后，web 控制台会关闭，无法直接访问。':'After entering low memory mode, the web console is stopped and cannot be accessed directly.',
    '最小内存模式提示':'Low Memory Mode Tip',
    '返回首页点击“启动”；需要排错时查看“日志”。':'Return to the home page and tap “Start”; check “Logs” when troubleshooting.',
    '在“代理管理”添加代理。':'Add proxies in “Proxy Manager”.',
    '在“基础设置”填写服务器信息。':'Fill in server information in “Basic Settings”.',
    '配置保存在 /data/adb/frpc/frpc.toml，升级模块不会覆盖。':'The configuration is stored at /data/adb/frpc/frpc.toml, and module updates will not overwrite it.',
    '支持最小内存运行，稳定后可关闭 web 常驻，减少后台占用。':'Supports low memory mode; after the setup is stable, you can stop the resident web service to reduce background usage.',
    '轻量 web 控制台，支持启动、停止、日志、配置和代理管理。':'Lightweight web console for start, stop, logs, configuration, and proxy management.',
    '如需只允许本机访问，请在 /data/adb/frpc/web_bind 中写入 127.0.0.1，然后重启模块服务。':'To allow only local access, write 127.0.0.1 into /data/adb/frpc/web_bind, then restart the module service.',
    '网页端口默认为 62930；如需修改端口，请编辑 /data/adb/frpc/web_port。':'The default web port is 62930; to change it, edit /data/adb/frpc/web_port.',
    '提示':'Tips',
    '高级配置文件路径':'Advanced Configuration File Path',
    '默认访问地址':'Default Access Address',
    '如需高级手动调整，可在“配置文件”页面直接编辑':'If you need advanced manual adjustments, you can directly edit',
    '如果希望长期稳定运行但尽量减少内存占用，可以在确认配置正常后使用“最小内存运行”。':'If you want long-term stable operation while reducing memory usage as much as possible, use “Low Memory Mode” after confirming that the configuration works normally.',
    '完成配置后返回首页，点击“启动”运行 frpc；如果需要排错，可到“日志”页面查看运行日志。':'After finishing the configuration, return to the home page and click “Start” to run frpc; if you need troubleshooting, open “Logs” to view runtime logs.',
    '进入“代理管理”添加你的代理项目，按需填写代理名称、类型、本地 IP、本地端口、远端端口或绑定域名。':'Open “Proxy Manager” to add your proxy items, and fill in the proxy name, type, local IP, local port, remote port, or custom domain as needed.',
    '进入“基础设置”填写 serverAddr、serverPort、user、dnsServer、log.level 等常用参数。':'Go to “Basic Settings” and fill in common parameters such as serverAddr, serverPort, user, dnsServer, and log.level.',
    '局域网设备访问':'Access from another device on the LAN at',
    '打开网页后台：本机访问':'Open the web panel: access locally at',
    '先安装模块，然后进入“更新 frpc”下载官方 frpc 二进制。':'First install the module, then open “Update frpc” to download the official frpc binary.',
    '网页支持中英文切换，并可按需设置登录账号密码。':'The web panel supports Chinese/English switching and lets you set a login account and password when needed.',
    '配置文件保存在用户目录，升级模块不会覆盖现有配置。':'The configuration file is stored in the user directory, so updating the module will not overwrite your existing configuration.',
    '提供最小内存运行模式；进入后只保留 frpc 与轻量守护，进一步减少常驻资源占用。':'It provides a low memory mode; after entering it, only frpc and a lightweight guard remain running to further reduce resident resource usage.',
    '支持基础设置、代理管理、配置文件编辑、日志查看、账号设置和一键更新。':'It supports basic settings, proxy management, configuration editing, log viewing, account settings, and one-click updates.',
    '界面轻量，打开首页时异步检测运行状态，不拖慢页面加载。':'The interface is lightweight, and the home page checks runtime status asynchronously so page loading stays fast.',
    '使用方法':'How to Use',
    '项目优势':'Project Advantages',
    '保存':'Save',
    '保存基础设置':'Save Basic Settings',
    '添加代理':'Add Proxy',
    '删除':'Delete',
    '清除当前日志':'Clear Current Log',
    '查看 update.log':'View update.log',
    '开始更新':'Start Update',
    '用户名':'Username',
    '密码':'Password',
    '登录':'Log In',
    '当前密码':'Current Password',
    '新用户名':'New Username',
    '新密码':'New Password',
    '再次输入新密码':'Confirm New Password',
    '再次输入密码':'Confirm Password',
    '保存账号设置':'Save Account Settings',
    '修改网页登录账号':'Change Web Login Account',
    '首次设置网页登录账号':'Set Web Login Account',
    '服务器地址 serverAddr':'Server Address serverAddr',
    '服务器端口 serverPort':'Server Port serverPort',
    '用户 user':'User user',
    'DNS 服务器 dnsServer':'DNS Server dnsServer',
    '日志等级 log.level':'Log Level log.level',
    '日志保存天数 log.maxDays':'Log Retention Days log.maxDays',
    '开机延迟启动，单位秒':'Boot Start Delay, seconds',
    '代理类型':'Proxy Type',
    '代理名称':'Proxy Name',
    '本地 IP':'Local IP',
    '本地端口':'Local Port',
    '远端端口':'Remote Port',
    '绑定域名':'Custom Domain',
    '运行中的代理':'Running Proxies',
    '当前没有代理。':'No proxies yet.',
    '类型':'Type',
    '本地':'Local',
    '远端端口':'Remote Port',
    '绑定域名':'Custom Domain',
    '说明':'Guide',
    '精简 web 页面版本说明':'Compact Web UI Notes',
    '语言':'Language',
    '当前 web 后台未设置用户名和密码，默认免登录。建议进入':'No web username or password is set, so login is skipped by default. Please open',
    '后先设置用户名和密码。':'to set a username and password first.',
    '配置文件：/data/adb/frpc/frpc.toml':'Configuration file: /data/adb/frpc/frpc.toml',
    '适合高级手动编辑。':'For advanced manual editing.',
    '这里替代原来的 config.sh。保存后会保留现有代理。':'This replaces the old config.sh. Existing proxies are kept after saving.',
    '留空则不写入 user。':'Leave blank to omit user.',
    '留空则不写入 dnsServer。':'Leave blank to omit dnsServer.',
    '留空则不启用 token。':'Leave blank to disable token.',
    '修改后会退出登录，需要用新账号重新进入。':'After saving, you will be logged out and must sign in again with the new account.',
    '当前 web 后台默认免密码进入。请先设置用户名和密码，保存后会退出并要求重新登录。':'The web panel currently allows password-free access. Set a username and password first; after saving, you will be logged out and asked to log in.',
    '只能使用字母、数字、点、下划线、横线。':'Use only letters, numbers, dots, underscores, and hyphens.',
    '不填则只修改用户名。':'Leave blank to change only the username.',
    '点击后会运行 update_frpc.sh，从 frp 官方开源发布地址下载 frpc。下载失败时模块不会坏，可以查看 update.log。':'This runs update_frpc.sh and downloads frpc from the official open-source frp release. If the download fails, the module is not damaged; check update.log.',
    '已进入最小内存运行模式。':'Low memory mode is enabled.',
    '该模式只保留':'This mode keeps only',
    '和轻量守护脚本，关闭':'and the lightweight guard script, and stops',
    '，减少常驻内存。':'to reduce resident memory.',
    '守护仍然保留：如果':'The guard remains active: if',
    '异常退出，':'exits unexpectedly,',
    '会按 5 秒轮询自动拉起。':'polls every 5 seconds and restarts it automatically.',
    '进入该模式后网页后台将无法访问；需要改配置时，在 Magisk/KernelSU/APatch 模块页点击本模块的操作按钮，会退出最小内存模式并恢复 web 控制台。':'After entering this mode, the web panel cannot be accessed. To change settings, tap this module action button in Magisk/KernelSU/APatch to exit low memory mode and restore the web console.',
    '也可以手动删除':'You can also manually delete',
    '后重启模块服务。':'and then restart the module service.',
    '当前未设置网页登录账号密码，直接进入控制台。':'No web login account is set. Entering the console directly.',
    '登录成功，正在进入控制台。':'Login successful. Entering the console.',
    '已退出。':'Logged out.',
    '账号设置已保存，请用新账号重新登录。':'Account settings saved. Please log in with the new account.'
  };
  var attrDict={
    'example.com 或 IP':'example.com or IP',
    '例如 ssh':'e.g. ssh',
    '例如 22':'e.g. 22',
    '例如 60022':'e.g. 60022',
    '例如 f50.example.com':'e.g. f50.example.com',
    '留空保持当前用户名':'Leave blank to keep current username',
    'trace/debug/info/warn/error':'trace/debug/info/warn/error'
  };
  function getLang(){
    try { return localStorage.getItem('frpc_lang') || 'en'; } catch(e) { return 'en'; }
  }
  function setStoredLang(l){
    try { localStorage.setItem('frpc_lang', l); } catch(e) {}
  }
  function revLookup(obj, value){
    var keys=Object.keys(obj);
    for(var i=0;i<keys.length;i++){ if(obj[keys[i]]===value){return keys[i];} }
    return null;
  }
  function trText(text, lang){
    var key=(text || '').trim();
    if(!key){return text;}
    if(lang==='zh'){
      var original=revLookup(dict, key);
      return original || text;
    }
    return dict[key] || text;
  }
  function trAttr(text, lang){
    var key=(text || '').trim();
    if(!key){return text;}
    if(lang==='zh'){
      var original=revLookup(attrDict, key);
      return original || text;
    }
    return attrDict[key] || text;
  }
  window.frpcT=function(text){return trText(text, getLang());};
  window.frpcApplyLang=function(root){
    var lang=getLang();
    var base=root || document.body;
    document.documentElement.lang=(lang==='zh')?'zh-CN':'en';
    var btn=document.getElementById('langToggle');
    if(btn){btn.textContent=(lang==='zh')?'English':'中文';}
    document.title=trText(document.title, lang);
    if(!base){return;}
    var walker=document.createTreeWalker(base, NodeFilter.SHOW_TEXT, {
      acceptNode:function(node){
        var p=node.parentNode;
        if(!p){return NodeFilter.FILTER_REJECT;}
        var tag=p.nodeName;
        if(tag==='SCRIPT'||tag==='STYLE'||tag==='TEXTAREA'||tag==='PRE'||tag==='CODE'){
          return NodeFilter.FILTER_REJECT;
        }
        return node.nodeValue.trim()?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT;
      }
    });
    var nodes=[], n;
    while((n=walker.nextNode())){nodes.push(n);}
    nodes.forEach(function(node){
      var raw=node.nodeValue;
      var key=raw.trim();
      var start=raw.indexOf(key);
      var lead=start>0?raw.slice(0,start):'';
      var tail=start>=0?raw.slice(start+key.length):'';
      node.nodeValue=lead+trText(raw, lang)+tail;
    });
    if(base.querySelectorAll){
      var fields=base.querySelectorAll('input[placeholder],textarea[placeholder]');
      for(var i=0;i<fields.length;i++){
        fields[i].setAttribute('placeholder', trAttr(fields[i].getAttribute('placeholder'), lang));
      }
    }
  };
  window.frpcSetLang=function(lang){
    lang=(lang==='zh')?'zh':'en';
    setStoredLang(lang);
    window.frpcApplyLang(document.body);
  };
  document.addEventListener('DOMContentLoaded', function(){
    var btn=document.getElementById('langToggle');
    if(btn){btn.onclick=function(){window.frpcSetLang(getLang()==='zh'?'en':'zh');};}
    window.frpcApplyLang(document.body);
  });
})();
</script>
HTML
}

page_bottom() {
  echo "</div></body></html>"
}

show_login() {
  MSG="$1"
  OK="$2"
  if ! auth_configured; then
    print_header_cookie "$COOKIE_NAME=deleted; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
    cat <<HTML
<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=/cgi-bin/frpc.cgi"></head><body>当前未设置网页登录账号密码，直接进入控制台。</body></html>
HTML
    return
  fi
  page_top_noauth "frpc 登录"
  if [ -n "$MSG" ]; then
    if [ "$OK" = "1" ]; then
      printf '<div class="msg ok">%s</div>\n' "$(printf '%s' "$MSG" | html_escape)"
    else
      printf '<div class="msg">%s</div>\n' "$(printf '%s' "$MSG" | html_escape)"
    fi
  fi
  cat <<HTML
<form method="post" action="/cgi-bin/frpc.cgi?action=login">
  <label>用户名</label>
  <input name="username" autocomplete="username">
  <label>密码</label>
  <input name="password" type="password" autocomplete="current-password" value="">
  <button class="btn" type="submit">登录</button>
</form>
HTML
  page_bottom
}

login_post() {
  if ! auth_configured; then
    print_header_cookie "$COOKIE_NAME=deleted; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
    cat <<HTML
<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=/cgi-bin/frpc.cgi"></head><body>当前未设置网页登录账号密码，直接进入控制台。</body></html>
HTML
    return
  fi
  USER_IN="$(get_param username)"
  PASS_IN="$(get_param password)"
  if verify_password "$USER_IN" "$PASS_IN"; then
    TOKEN="$(create_session "$USER_IN")"
    print_header_cookie "$COOKIE_NAME=$TOKEN; Path=/; Max-Age=$SESSION_TTL; HttpOnly; SameSite=Lax"
    cat <<HTML
<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=/cgi-bin/frpc.cgi"></head><body>登录成功，正在进入控制台。</body></html>
HTML
    return
  fi
  show_login "用户名或密码错误，请重新输入。" "0"
}

logout_page() {
  TOKEN="$(get_cookie_token)"
  if valid_token "$TOKEN"; then
    rm -f "$SESSION_DIR/$TOKEN" 2>/dev/null
  fi
  print_header_cookie "$COOKIE_NAME=deleted; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
  cat <<HTML
<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=/cgi-bin/frpc.cgi"></head><body>已退出。</body></html>
HTML
}

show_status() {
  # 首页不直接显示运行中的代理；运行中的代理放到代理管理页面异步加载。
  MSG="$1"
  page_top "frpc 控制台"
  [ -n "$MSG" ] && echo "<div class=\"card msg\">$(printf '%s' "$MSG" | html_escape)</div>"
  if ! auth_configured; then
    echo '<div class="card msg">当前 web 后台未设置用户名和密码，默认免登录。建议进入 <a href="/cgi-bin/frpc.cgi?action=account">账号设置</a> 后先设置用户名和密码。</div>'
  fi
  cat <<HTML
<div class="card">
  <div class="btns">
    <a class="btn ok" href="/cgi-bin/frpc.cgi?action=start">启动</a>
    <a class="btn bad" href="/cgi-bin/frpc.cgi?action=stop">停止</a>
    <a class="btn warn" href="/cgi-bin/frpc.cgi?action=low_memory">最小内存运行</a>
    $(if [ -f "$LOW_MEM_FILE" ]; then echo '<a class="btn secondary" href="/cgi-bin/frpc.cgi?action=normal_memory">恢复网页</a>'; fi)
  </div>
</div>
<div class="card">
  <h3>配置与维护</h3>
  <div class="btns">
    <a class="btn secondary" href="/cgi-bin/frpc.cgi?action=basic">基础设置</a>
    <a class="btn secondary" href="/cgi-bin/frpc.cgi?action=proxies">代理管理</a>
    <a class="btn secondary" href="/cgi-bin/frpc.cgi?action=config">配置文件</a>
    <a class="btn secondary" href="/cgi-bin/frpc.cgi?action=logs">日志</a>
    <a class="btn secondary" href="/cgi-bin/frpc.cgi?action=update">更新 frpc</a>
    <a class="btn secondary" href="/cgi-bin/frpc.cgi?action=account">账号设置</a>
    <a class="btn secondary" href="/cgi-bin/frpc.cgi?action=about">说明</a>
    $(if auth_configured; then echo '<a class="btn secondary" href="/cgi-bin/frpc.cgi?action=logout">退出登录</a>'; fi)
  </div>
</div>
HTML
  page_bottom
}

show_logs() {
  MSG="$1"
  WHICH="$(get_param which)"
  case "$WHICH" in
    frpc) FILE="$LOG_FILE"; NAME="frpc.log" ;;
    update) FILE="$UPDATE_LOG"; NAME="update.log" ;;
    web) FILE="$WEB_LOG"; NAME="web.log" ;;
    *) FILE="$SERVICE_LOG"; NAME="service.log" ;;
  esac
  page_top "frpc 日志"
  cat <<HTML
<div class="card">
  <div class="btns">
    <a class="btn secondary" href="/cgi-bin/frpc.cgi?action=logs&which=service">service.log</a>
    <a class="btn secondary" href="/cgi-bin/frpc.cgi?action=logs&which=frpc">frpc.log</a>
    <a class="btn secondary" href="/cgi-bin/frpc.cgi?action=logs&which=update">update.log</a>
    <a class="btn secondary" href="/cgi-bin/frpc.cgi?action=logs&which=web">web.log</a>
    <a class="btn bad" href="/cgi-bin/frpc.cgi?action=clear_log&which=$WHICH">清除当前日志</a>

  </div>
  <h3>$NAME</h3>
HTML
  [ -n "$MSG" ] && echo "<div class=\"msg\">$(printf '%s' "$MSG" | html_escape)</div>"
  if [ -f "$FILE" ]; then
    echo "<pre>"
    tail -n 220 "$FILE" 2>/dev/null | html_escape
    echo "</pre>"
  else
    echo "<p>日志文件不存在：$(printf '%s' "$FILE" | html_escape)</p>"
  fi
  echo "</div>"
  page_bottom
}

clear_log() {
  WHICH="$(get_param which)"
  case "$WHICH" in
    frpc) FILE="$LOG_FILE"; NAME="frpc.log" ;;
    update) FILE="$UPDATE_LOG"; NAME="update.log" ;;
    web) FILE="$WEB_LOG"; NAME="web.log" ;;
    *) FILE="$SERVICE_LOG"; NAME="service.log" ;;
  esac
  : > "$FILE" 2>/dev/null
  show_logs "已清除 $NAME"
}

save_config() {
  ENC="$(get_post_value config)"
  if [ -z "$ENC" ]; then
    show_status "保存失败：没有收到配置内容。"
    return
  fi
  DECODED="$(urldecode "$ENC")"
  printf '%s\n' "$DECODED" > "$CONFIG"
  chmod 644 "$CONFIG" 2>/dev/null
  show_status "配置文件已保存。"
}

show_config() {
  page_top "frpc 配置"
  echo "<div class=\"card\"><h3>配置文件：/data/adb/frpc/frpc.toml</h3><p class=\"sub\">适合高级手动编辑。</p>"
  echo "<form method=\"post\" action=\"/cgi-bin/frpc.cgi?action=save_config\">"
  echo "<textarea name=\"config\">"
  if [ -f "$CONFIG" ]; then
    cat "$CONFIG" 2>/dev/null | html_escape
  fi
  echo "</textarea>"
  echo "<div class=\"btns\"><button class=\"btn ok\" type=\"submit\">保存</button></div>"
  echo "</form></div>"
  page_bottom
}


show_basic() {
  OLD_ADDR="$(get_server_addr)"
  OLD_PORT="$(get_server_port)"
  OLD_USER="$(get_user)"
  OLD_DNS="$(get_dns_server)"
  OLD_TOKEN="$(get_token)"
  OLD_LEVEL="$(get_log_level)"
  OLD_DAYS="$(get_log_max_days)"
  OLD_DELAY="$(get_start_delay)"
  [ -z "$OLD_USER" ] && OLD_USER="user"
  [ -z "$OLD_DNS" ] && OLD_DNS="223.5.5.5"
  [ -z "$OLD_LEVEL" ] && OLD_LEVEL="info"
  [ -z "$OLD_DAYS" ] && OLD_DAYS="7"
  page_top "基础设置"
  cat <<HTML
<div class="card">
  <h3>基础设置</h3>
  <p class="sub">这里替代原来的 config.sh。保存后会保留现有代理。</p>
  <form method="post" action="/cgi-bin/frpc.cgi?action=save_basic">
    <div class="form-row"><label>服务器地址 serverAddr</label><input name="server_addr" value="$(printf '%s' "$OLD_ADDR" | html_escape)" placeholder="example.com 或 IP"></div>
    <div class="form-row"><label>服务器端口 serverPort</label><input name="server_port" value="$(printf '%s' "$OLD_PORT" | html_escape)" inputmode="numeric"></div>
    <div class="form-row"><label>用户 user</label><input name="user_name" value="$(printf '%s' "$OLD_USER" | html_escape)"><div class="small">留空则不写入 user。</div></div>
    <div class="form-row"><label>DNS 服务器 dnsServer</label><input name="dns_server" value="$(printf '%s' "$OLD_DNS" | html_escape)"><div class="small">留空则不写入 dnsServer。</div></div>
    <div class="form-row"><label>Token</label><input name="token" value="$(printf '%s' "$OLD_TOKEN" | html_escape)"><div class="small">留空则不启用 token。</div></div>
    <div class="form-row"><label>日志等级 log.level</label><input name="log_level" value="$(printf '%s' "$OLD_LEVEL" | html_escape)" placeholder="trace/debug/info/warn/error"></div>
    <div class="form-row"><label>日志保存天数 log.maxDays</label><input name="log_days" value="$(printf '%s' "$OLD_DAYS" | html_escape)" inputmode="numeric"></div>
    <div class="form-row"><label>开机延迟启动，单位秒</label><input name="start_delay" value="$(printf '%s' "$OLD_DELAY" | html_escape)" inputmode="numeric"></div>
    <div class="btns"><button class="btn ok" type="submit">保存基础设置</button></div>
  </form>
</div>
HTML
  page_bottom
}

save_basic() {
  SERVER_ADDR="$(get_param server_addr)"
  SERVER_PORT="$(get_param server_port)"
  USER_NAME="$(get_param user_name)"
  DNS_SERVER="$(get_param dns_server)"
  TOKEN="$(get_param token)"
  LOG_LEVEL="$(get_param log_level)"
  LOG_DAYS="$(get_param log_days)"
  START_DELAY="$(get_param start_delay)"
  [ -z "$LOG_LEVEL" ] && LOG_LEVEL="info"
  [ -z "$LOG_DAYS" ] && LOG_DAYS="7"
  [ -z "$START_DELAY" ] && START_DELAY="10"
  case "$LOG_LEVEL" in trace|debug|info|warn|error) ;; *) show_status "保存失败：日志等级只能是 trace/debug/info/warn/error。"; return ;; esac
  [ -n "$SERVER_ADDR" ] || { show_status "保存失败：serverAddr 不能为空。"; return; }
  [ -z "$SERVER_PORT" ] || valid_port "$SERVER_PORT" || { show_status "保存失败：serverPort 必须是 1-65535 的数字。"; return; }
  is_number "$LOG_DAYS" || { show_status "保存失败：日志保存天数必须是数字。"; return; }
  is_number "$START_DELAY" || { show_status "保存失败：开机延迟必须是数字。"; return; }
  preserve_proxies
  E_ADDR="$(toml_escape "$SERVER_ADDR")"
  E_USER="$(toml_escape "$USER_NAME")"
  E_DNS="$(toml_escape "$DNS_SERVER")"
  E_TOKEN="$(toml_escape "$TOKEN")"
  cat > "$CONFIG" <<EOF_CFG
serverAddr = "$E_ADDR"
EOF_CFG
  [ -n "$SERVER_PORT" ] && echo "serverPort = $SERVER_PORT" >> "$CONFIG"
  [ -n "$USER_NAME" ] && echo "user = \"$E_USER\"" >> "$CONFIG"
  [ -n "$DNS_SERVER" ] && echo "dnsServer = \"$E_DNS\"" >> "$CONFIG"
  cat >> "$CONFIG" <<EOF_CFG

log.to = "$LOG_FILE"
log.level = "$LOG_LEVEL"
log.maxDays = $LOG_DAYS

EOF_CFG
  if [ -n "$TOKEN" ]; then
    cat >> "$CONFIG" <<EOF_CFG
auth.method = "token"
auth.token = "$E_TOKEN"

EOF_CFG
  fi
  append_preserved_proxies
  chmod 644 "$CONFIG" 2>/dev/null
  echo "$START_DELAY" > "$DATA_DIR/start_delay" 2>/dev/null
  chmod 644 "$DATA_DIR/start_delay" 2>/dev/null
  show_status "基础设置已保存。"
}

show_proxies() {
  page_top "代理管理"
  cat <<HTML
<div id="runningProxies"></div>
<script>
(function(){
  var box=document.getElementById('runningProxies');
  if(!box){return;}
  fetch('/cgi-bin/frpc.cgi?action=running_proxies',{cache:'no-store'})
    .then(function(r){return r.text();})
    .then(function(t){
      t=(t||'').trim();
      if(t){box.innerHTML=t; if(window.frpcApplyLang){window.frpcApplyLang(box);}}
    })
    .catch(function(){});
})();
</script>
<div class="card">
  <h3>新增代理</h3>
  <form method="post" action="/cgi-bin/frpc.cgi?action=add_proxy">
    <div class="form-row"><label>代理类型</label><select id="proxy_type" name="proxy_type" onchange="syncProxyFields()" style="width:100%;border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--card);color:var(--text);font-size:15px"><option value="tcpudp">tcp + udp</option><option value="tcp">tcp</option><option value="udp">udp</option><option value="http">http</option><option value="https">https</option></select></div>
    <div class="form-row"><label>代理名称</label><input name="proxy_name" placeholder="例如 ssh"></div>
    <div class="form-row"><label>本地 IP</label><input name="local_ip" value="127.0.0.1"></div>
    <div class="form-row"><label>本地端口</label><input name="local_port" inputmode="numeric" placeholder="例如 22"></div>
    <div class="form-row" id="remote_port_row"><label>远端端口</label><input id="remote_port" name="remote_port" inputmode="numeric" placeholder="例如 60022"></div>
    <div class="form-row" id="custom_domain_row" style="display:none"><label>绑定域名</label><input id="custom_domain" name="custom_domain" placeholder="例如 f50.example.com"></div>
    <div class="btns"><button class="btn ok" type="submit">添加代理</button></div>
    <script>
      function syncProxyFields(){
        var t=document.getElementById('proxy_type').value;
        var needDomain=(t==='http'||t==='https');
        document.getElementById('custom_domain_row').style.display=needDomain?'block':'none';
        document.getElementById('remote_port_row').style.display=needDomain?'none':'block';
      }
      syncProxyFields();
    </script>
  </form>
</div>
HTML
  page_bottom
}

add_proxy() {
  TYPE="$(get_param proxy_type)"
  NAME="$(get_param proxy_name)"
  LOCAL_IP="$(get_param local_ip)"
  LOCAL_PORT="$(get_param local_port)"
  REMOTE_PORT="$(get_param remote_port)"
  DOMAIN="$(get_param custom_domain)"
  [ -z "$LOCAL_IP" ] && LOCAL_IP="127.0.0.1"
  case "$TYPE" in tcpudp|tcp|udp|http|https) ;; *) TYPE="tcpudp" ;; esac
  [ -n "$NAME" ] || { show_status "添加失败：代理名称不能为空。"; return; }
  valid_port "$LOCAL_PORT" || { show_status "添加失败：本地端口必须是 1-65535 的数字。"; return; }
  if [ "$TYPE" = "http" ] || [ "$TYPE" = "https" ]; then
    [ -n "$DOMAIN" ] || { show_status "添加失败：http/https 必须填写绑定域名。"; return; }
  else
    valid_port "$REMOTE_PORT" || { show_status "添加失败：远端端口必须是 1-65535 的数字。"; return; }
  fi
  [ -f "$CONFIG" ] || cp -f "$DEFAULT_CONFIG" "$CONFIG" 2>/dev/null
  E_NAME="$(toml_escape "$NAME")"
  E_LOCAL="$(toml_escape "$LOCAL_IP")"
  E_DOMAIN="$(toml_escape "$DOMAIN")"
  echo >> "$CONFIG"
  if [ "$TYPE" = "tcpudp" ]; then
    cat >> "$CONFIG" <<EOF_PROXY
[[proxies]]
name = "${E_NAME}-tcp"
type = "tcp"
localIP = "$E_LOCAL"
localPort = $LOCAL_PORT
remotePort = $REMOTE_PORT

[[proxies]]
name = "${E_NAME}-udp"
type = "udp"
localIP = "$E_LOCAL"
localPort = $LOCAL_PORT
remotePort = $REMOTE_PORT
EOF_PROXY
  elif [ "$TYPE" = "http" ] || [ "$TYPE" = "https" ]; then
    cat >> "$CONFIG" <<EOF_PROXY
[[proxies]]
name = "${E_NAME}-${TYPE}"
type = "$TYPE"
localIP = "$E_LOCAL"
localPort = $LOCAL_PORT
customDomains = ["$E_DOMAIN"]
EOF_PROXY
  else
    cat >> "$CONFIG" <<EOF_PROXY
[[proxies]]
name = "${E_NAME}-${TYPE}"
type = "$TYPE"
localIP = "$E_LOCAL"
localPort = $LOCAL_PORT
remotePort = $REMOTE_PORT
EOF_PROXY
  fi
  chmod 644 "$CONFIG" 2>/dev/null
  show_status "代理已添加。"
}

delete_proxy() {
  IDX="$(get_param proxy_index)"
  COUNT="$(get_proxy_count)"
  is_number "$IDX" || { show_status "删除失败：请输入数字序号。"; return; }
  [ "$IDX" -ge 1 ] 2>/dev/null || { show_status "删除失败：序号不合法。"; return; }
  [ "$IDX" -le "$COUNT" ] 2>/dev/null || { show_status "删除失败：代理序号不存在。"; return; }
  TMP="$DATA_DIR/.frpc_config.tmp"
  awk -v del="$IDX" 'BEGIN { idx=0; skip=0 } /^\[\[proxies\]\]/ { idx++; if (idx == del) { skip=1; next } else { skip=0 } } { if (!skip) print }' "$CONFIG" > "$TMP"
  cat "$TMP" > "$CONFIG"
  rm -f "$TMP" 2>/dev/null
  chmod 644 "$CONFIG" 2>/dev/null
  show_status "代理已删除。"
}

show_update() {
  page_top "更新 frpc"
  cat <<HTML
<div class="card">
  <h3>更新 frpc 二进制</h3>
  <p class="sub">点击后会运行 update_frpc.sh，从 frp 官方开源发布地址下载 frpc。下载失败时模块不会坏，可以在本页查看 update.log。</p>
  <div class="btns">
    <button id="runUpdateBtn" class="btn ok" type="button" onclick="startFrpcUpdate()">开始更新</button>
    <button class="btn secondary" type="button" onclick="refreshUpdateLog()">查看 update.log</button>
  </div>
  <div id="updateMsg" class="msg" style="display:none;margin-top:12px"></div>
</div>

<div class="card">
  <h3>update.log</h3>
  <pre id="updateLogBox">Loading update.log...</pre>
</div>

<script>
(function(){
  var timer=null;

  function box(){
    return document.getElementById('updateLogBox');
  }

  function btn(){
    return document.getElementById('runUpdateBtn');
  }

  function msg(){
    return document.getElementById('updateMsg');
  }

  function setMsg(text){
    var m=msg();
    if(!m){return;}
    m.style.display='block';
    m.textContent=text;
  }

  window.refreshUpdateLog=function(){
    var b=box();
    if(!b){return;}
    fetch('/cgi-bin/frpc.cgi?action=update_log_text',{cache:'no-store'})
      .then(function(r){return r.text();})
      .then(function(t){
        t=(t||'').trim();
        b.textContent=t || 'update.log is empty.';
        b.scrollTop=b.scrollHeight;
      })
      .catch(function(){
        b.textContent='Failed to load update.log.';
      });
  };

  function refreshStatus(){
    fetch('/cgi-bin/frpc.cgi?action=update_status_text',{cache:'no-store'})
      .then(function(r){return r.text();})
      .then(function(t){
        t=(t||'').trim();
        if(t && t !== 'running'){
          if(timer){
            clearInterval(timer);
            timer=null;
          }

          var button=btn();
          if(button){
            button.disabled=false;
            button.textContent='开始更新';
          }

          if(t === 'latest'){
            setMsg('frpc 已是最新版，无需更新。');
          } else if(t === 'updated'){
            setMsg('frpc 更新完成。');
          } else if(t === 'failed'){
            setMsg('frpc 更新失败，请查看 update.log。');
          } else {
            setMsg('frpc 更新流程已结束。');
          }

          refreshUpdateLog();
        }
      })
      .catch(function(){});
  }

  window.startFrpcUpdate=function(){
    var button=btn();
    if(button){
      button.disabled=true;
      button.textContent='更新中...';
    }

    setMsg('frpc 更新已开始，下面会自动刷新 update.log。');
    refreshUpdateLog();

    if(timer){
      clearInterval(timer);
    }

    timer=setInterval(function(){
      refreshUpdateLog();
      refreshStatus();
    },1500);

    fetch('/cgi-bin/frpc.cgi?action=run_update_async',{cache:'no-store'})
      .then(function(r){return r.text();})
      .then(function(t){
        t=(t||'').trim();
        if(t){
          setMsg(t);
        }
        refreshUpdateLog();
      })
      .catch(function(){
        setMsg('frpc 更新启动失败。');
        if(timer){
          clearInterval(timer);
          timer=null;
        }
        if(button){
          button.disabled=false;
          button.textContent='开始更新';
        }
      });
  };

  refreshUpdateLog();
})();
</script>
HTML
  page_bottom
}

update_pid_running() {
  UPDATE_PID_FILE="$DATA_DIR/update.pid"
  [ -f "$UPDATE_PID_FILE" ] || return 1
  PID="$(cat "$UPDATE_PID_FILE" 2>/dev/null | head -n 1)"
  [ -n "$PID" ] || return 1
  [ -d "/proc/$PID" ] || return 1
  return 0
}

text_header() {
  echo "Content-Type: text/plain; charset=UTF-8"
  echo "Cache-Control: no-store"
  echo ""
}

update_log_text() {
  text_header
  if [ -f "$UPDATE_LOG" ]; then
    tail -n 220 "$UPDATE_LOG" 2>/dev/null
  fi
}

update_status_text() {
  text_header
  STATUS="$(cat "$DATA_DIR/update.status" 2>/dev/null | head -n 1)"

  if update_pid_running; then
    echo "running"
    return
  fi

  if [ "$STATUS" = "running" ]; then
    echo "idle"
  elif [ -n "$STATUS" ]; then
    echo "$STATUS"
  else
    echo "idle"
  fi
}

run_update_async() {
  text_header

  if [ ! -f "$UPDATE_SCRIPT" ]; then
    echo "更新失败：找不到 $UPDATE_SCRIPT"
    return
  fi

  if update_pid_running; then
    echo "frpc 更新正在运行，请等待完成。"
    return
  fi

  : > "$UPDATE_LOG" 2>/dev/null
  echo "running" > "$DATA_DIR/update.status" 2>/dev/null

  nohup sh "$UPDATE_SCRIPT" --auto >/dev/null 2>&1 &
  PID="$!"
  echo "$PID" > "$DATA_DIR/update.pid" 2>/dev/null

  echo "frpc 更新已开始。"
}

run_update() {
  run_update_async
}

show_account() {
  page_top "账号设置"
  if auth_configured; then
    USER_NOW="$(get_auth_user)"
    cat <<HTML
<div class="card">
  <h3>修改网页登录账号</h3>
  <p class="sub">修改后会退出登录，需要用新账号重新进入。</p>
  <form method="post" action="/cgi-bin/frpc.cgi?action=save_account">
    <div class="form-row"><label>当前密码</label><input name="old_password" type="password" autocomplete="current-password"></div>
    <div class="form-row"><label>新用户名</label><input name="new_username" placeholder="留空保持当前用户名" autocomplete="username"><div class="small">当前用户名：$(printf '%s' "$USER_NOW" | html_escape)。只能使用字母、数字、点、下划线、横线。</div></div>
    <div class="form-row"><label>新密码</label><input name="new_password" type="password" autocomplete="new-password"><div class="small">不填则只修改用户名。</div></div>
    <div class="form-row"><label>再次输入新密码</label><input name="new_password2" type="password" autocomplete="new-password"></div>
    <div class="btns"><button class="btn ok" type="submit">保存账号设置</button></div>
  </form>
</div>
HTML
  else
    cat <<HTML
<div class="card">
  <h3>首次设置网页登录账号</h3>
  <p class="sub">当前 web 后台默认免密码进入。请先设置用户名和密码，保存后会退出并要求重新登录。</p>
  <form method="post" action="/cgi-bin/frpc.cgi?action=save_account">
    <div class="form-row"><label>用户名</label><input name="new_username" autocomplete="username"><div class="small">只能使用字母、数字、点、下划线、横线。</div></div>
    <div class="form-row"><label>密码</label><input name="new_password" type="password" autocomplete="new-password"></div>
    <div class="form-row"><label>再次输入密码</label><input name="new_password2" type="password" autocomplete="new-password"></div>
    <div class="btns"><button class="btn ok" type="submit">保存账号设置</button></div>
  </form>
</div>
HTML
  fi
  page_bottom
}

save_account() {
  OLD_PASS="$(get_param old_password)"
  NEW_USER="$(get_param new_username)"
  NEW_PASS="$(get_param new_password)"
  NEW_PASS2="$(get_param new_password2)"
  if auth_configured; then
    OLD_USER="$(get_auth_user)"
    if ! verify_password "$OLD_USER" "$OLD_PASS"; then
      RETURN_URL="/cgi-bin/frpc.cgi?action=account"; RETURN_TEXT="返回账号设置"
      page_top "账号设置"
      echo '<div class="card msg">当前密码错误，账号设置没有修改。</div><div class="card"></div>'
      page_bottom
      return
    fi
    [ -z "$NEW_USER" ] && NEW_USER="$OLD_USER"
    if [ -n "$NEW_PASS" ]; then
      if [ "$NEW_PASS" != "$NEW_PASS2" ]; then
        RETURN_URL="/cgi-bin/frpc.cgi?action=account"; RETURN_TEXT="返回账号设置"
        page_top "账号设置"
        echo '<div class="card msg">两次输入的新密码不一致。</div><div class="card"></div>'
        page_bottom
        return
      fi
      SAVE_PASS="$NEW_PASS"
    else
      SAVE_PASS="$OLD_PASS"
    fi
  else
    if [ -z "$NEW_USER" ]; then
      RETURN_URL="/cgi-bin/frpc.cgi?action=account"; RETURN_TEXT="返回账号设置"
      page_top "账号设置"
      echo '<div class="card msg">首次设置必须填写用户名。</div><div class="card"></div>'
      page_bottom
      return
    fi
    if [ -z "$NEW_PASS" ]; then
      RETURN_URL="/cgi-bin/frpc.cgi?action=account"; RETURN_TEXT="返回账号设置"
      page_top "账号设置"
      echo '<div class="card msg">首次设置必须填写密码。</div><div class="card"></div>'
      page_bottom
      return
    fi
    if [ "$NEW_PASS" != "$NEW_PASS2" ]; then
      RETURN_URL="/cgi-bin/frpc.cgi?action=account"; RETURN_TEXT="返回账号设置"
      page_top "账号设置"
      echo '<div class="card msg">两次输入的密码不一致。</div><div class="card"></div>'
      page_bottom
      return
    fi
    SAVE_PASS="$NEW_PASS"
  fi
  if ! valid_username "$NEW_USER"; then
    RETURN_URL="/cgi-bin/frpc.cgi?action=account"; RETURN_TEXT="返回账号设置"
    page_top "账号设置"
    echo '<div class="card msg">用户名不合法。只能使用字母、数字、点、下划线、横线。</div><div class="card"></div>'
    page_bottom
    return
  fi
  if write_auth "$NEW_USER" "$SAVE_PASS"; then
    clear_sessions
    print_header_cookie "$COOKIE_NAME=deleted; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
    cat <<HTML
<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="2; url=/cgi-bin/frpc.cgi"></head><body>账号设置已保存，请用新账号重新登录。</body></html>
HTML
  else
    page_top "账号设置"
    echo '<div class="card msg">账号设置保存失败。</div>'
    page_bottom
  fi
}




show_about() {
  page_top "frpc 说明"
  cat <<HTML
<div class="card">
  <h3>项目优势</h3>
  <ul class="info-list">
    <li>轻量 web 控制台，支持启动、停止、日志、配置和代理管理。</li>
    <li>支持最小内存运行，稳定后可关闭 web 常驻，减少后台占用。</li>
  </ul>
</div>
<div class="card">
  <h3>使用方法</h3>
  <ul class="info-list">
    <li>在“基础设置”填写服务器信息。</li>
    <li>在“代理管理”添加代理。</li>
    <li>返回首页点击“启动”；需要排错时查看“日志”。</li>
  </ul>
</div>
<div class="card">
  <h3>最小内存模式提示</h3>
  <ul class="info-list">
    <li>进入最小内存模式后，web 控制台会关闭，无法直接访问。</li>
    <li>需要恢复 web 常驻时：打开 Magisk / KernelSU / APatch 的模块页面，点击本模块的“操作 / Action”按钮。</li>
    <li>模块会退出最小内存模式，并重新拉起 web 控制台。</li>
    <li>恢复后再次打开默认地址：<code>http://127.0.0.1:62930</code></li>
  </ul>
</div>
HTML
  page_bottom
}

init_auth
# Read POST body once in the main shell process. Command substitution runs in a subshell,
# so reading stdin inside get_param repeatedly would lose the body after the first field.
if is_number "${CONTENT_LENGTH:-0}" && [ "${CONTENT_LENGTH:-0}" -gt 0 ]; then
  read_body
fi
ACTION_RAW="$(get_query_value action)"
ACTION="$(urldecode "$ACTION_RAW")"

case "$ACTION" in
  login) login_post; exit 0 ;;
  logout) logout_page; exit 0 ;;
esac

if ! is_authed; then
  show_login "" "0"
  exit 0
fi

case "$ACTION" in
  quick_status) quick_status; exit 0 ;;
  update_log_text) update_log_text; exit 0 ;;
  update_status_text) update_status_text; exit 0 ;;
  run_update_async) run_update_async; exit 0 ;;
  running_proxies) running_proxies; exit 0 ;;
  start)
    rm -f "$LOW_MEM_FILE" 2>/dev/null
    rm -f "$CONTROL_FILE" 2>/dev/null
    MSG="$(start_frpc)"
    update_module_prop
    show_status "$MSG"
    ;;
  stop)
    rm -f "$LOW_MEM_FILE" 2>/dev/null
    echo "1" > "$CONTROL_FILE"
    chmod 644 "$CONTROL_FILE" 2>/dev/null
    MSG="$(stop_frpc)"
    update_module_prop
    show_status "$MSG"
    ;;
  restart)
    rm -f "$LOW_MEM_FILE" 2>/dev/null
    MSG="$(restart_frpc)"
    update_module_prop
    show_status "$MSG"
    ;;
  toggle)
    rm -f "$LOW_MEM_FILE" 2>/dev/null
    if [ -f "$CONTROL_FILE" ]; then
      rm -f "$CONTROL_FILE" 2>/dev/null
      MSG="$(start_frpc)"
    else
      PID="$(get_pid)"
      if [ -n "$PID" ]; then
        echo "1" > "$CONTROL_FILE"
        chmod 644 "$CONTROL_FILE" 2>/dev/null
        MSG="$(stop_frpc)"
      else
        rm -f "$CONTROL_FILE" 2>/dev/null
        MSG="$(start_frpc)"
      fi
    fi
    update_module_prop
    show_status "$MSG"
    ;;
  low_memory) enable_low_memory ;;
  normal_memory) disable_low_memory ;;
  logs) show_logs ;;
  clear_log) clear_log ;;
  basic) show_basic ;;
  save_basic) save_basic ;;
  proxies) show_proxies ;;
  add_proxy) add_proxy ;;
  delete_proxy) delete_proxy ;;
  config) show_config ;;
  save_config) save_config ;;
  update) show_update ;;
  run_update) run_update ;;
  account) show_account ;;
  save_account) save_account ;;
about) show_about ;;
  *) show_status "" ;;
esac