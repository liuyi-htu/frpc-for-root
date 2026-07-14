#!/system/bin/sh

ui_print() {
  echo "$1"
}

ui_print "*******************************"
ui_print " frpc web Only"
ui_print "*******************************"

[ -z "$MODPATH" ] && MODPATH="/data/adb/modules_update/frpc"
DATADIR="/data/adb/frpc"
CONFIG_DATA="$DATADIR/frpc.toml"
mkdir -p "$DATADIR" "$DATADIR/downloads" "$DATADIR/web_sessions"
chmod 755 "$DATADIR" "$DATADIR/downloads" 2>/dev/null
chmod 700 "$DATADIR/web_sessions" 2>/dev/null

# web-only config: keep user config in /data/adb/frpc so module upgrade will not overwrite it.
if [ ! -f "$CONFIG_DATA" ]; then
  if [ -f "/data/adb/modules/frpc/frpc.toml" ]; then
    cp -f "/data/adb/modules/frpc/frpc.toml" "$CONFIG_DATA" 2>/dev/null
  elif [ -f "$MODPATH/frpc.toml" ]; then
    cp -f "$MODPATH/frpc.toml" "$CONFIG_DATA" 2>/dev/null
  fi
  chmod 644 "$CONFIG_DATA" 2>/dev/null
fi

# Update old defaults from earlier web UI versions.
if [ -f "$CONFIG_DATA" ] && grep -q '^user[[:space:]]*=[[:space:]]*"F50"' "$CONFIG_DATA" 2>/dev/null; then
  sed -i 's/^user[[:space:]]*=[[:space:]]*"F50"/user = "user"/' "$CONFIG_DATA" 2>/dev/null
fi

# Do not pre-fill the server port on fresh/default configs.
if [ -f "$CONFIG_DATA" ] && grep -q '^serverAddr[[:space:]]*=[[:space:]]*""' "$CONFIG_DATA" 2>/dev/null && grep -q '^serverPort[[:space:]]*=[[:space:]]*7000' "$CONFIG_DATA" 2>/dev/null; then
  sed -i '/^serverPort[[:space:]]*=[[:space:]]*7000/d' "$CONFIG_DATA" 2>/dev/null
fi
if [ ! -f "$DATADIR/start_delay" ] || [ "$(cat "$DATADIR/start_delay" 2>/dev/null | head -n 1)" = "30" ]; then
  echo "10" > "$DATADIR/start_delay"
fi
chmod 644 "$DATADIR/start_delay" 2>/dev/null
echo "1" > "$DATADIR/.defaults_v312_done" 2>/dev/null
chmod 644 "$DATADIR/.defaults_v312_done" 2>/dev/null

# Default web UI port/bind/auth. Do not overwrite user changes on upgrade.
if [ ! -f "$DATADIR/web_port" ] || [ "$(cat "$DATADIR/web_port" 2>/dev/null | head -n 1)" = "62919" ]; then
  echo "62930" > "$DATADIR/web_port"
fi
chmod 644 "$DATADIR/web_port" 2>/dev/null
[ -f "$DATADIR/web_bind" ] || echo "0.0.0.0" > "$DATADIR/web_bind"
chmod 644 "$DATADIR/web_bind" 2>/dev/null

if [ -f "$DATADIR/web_auth.conf" ]; then
  AUTH_USER_OLD="$(sed -n '1p' "$DATADIR/web_auth.conf" 2>/dev/null | head -n 1)"
  AUTH_SECRET_OLD="$(sed -n '2p' "$DATADIR/web_auth.conf" 2>/dev/null | head -n 1)"
  if [ "$AUTH_USER_OLD" = "admin" ]; then
    if command -v sha256sum >/dev/null 2>&1; then
      HASH="$(printf '%s' admin | sha256sum 2>/dev/null | awk '{print $1}')"
    elif command -v toybox >/dev/null 2>&1; then
      HASH="$(printf '%s' admin | toybox sha256sum 2>/dev/null | awk '{print $1}')"
    else
      HASH=""
    fi
    if [ "$AUTH_SECRET_OLD" = "P:admin" ] || { [ -n "$HASH" ] && [ "$AUTH_SECRET_OLD" = "H:$HASH" ]; }; then
      rm -f "$DATADIR/web_auth.conf" 2>/dev/null
    fi
  fi
fi

# Use bundled Asia/Shanghai zoneinfo for frpc logs. TZ=CST-8 may be ignored by Go on Android and fall back to UTC.
TZ_FILE="$MODPATH/zoneinfo/Asia/Shanghai"
if [ -f "$TZ_FILE" ]; then
  echo "$TZ_FILE" > "$DATADIR/timezone" 2>/dev/null
  ui_print "Timezone: Asia/Shanghai"
else
  echo "Asia/Shanghai" > "$DATADIR/timezone" 2>/dev/null
  ui_print "Timezone: Asia/Shanghai fallback"
fi
chmod 644 "$DATADIR/timezone" 2>/dev/null

chmod 755 "$MODPATH/service.sh" 2>/dev/null
chmod 755 "$MODPATH/update_frpc.sh" 2>/dev/null
chmod 755 "$MODPATH/uninstall.sh" 2>/dev/null
chmod 755 "$MODPATH/action.sh" 2>/dev/null
chmod 755 "$MODPATH/webui.sh" 2>/dev/null
[ -f "$MODPATH/frpc" ] && chmod 755 "$MODPATH/frpc"
chmod 644 "$MODPATH/module.prop" 2>/dev/null
chmod 644 "$MODPATH/frpc.toml" 2>/dev/null

ui_print "Installing/updating frpc..."
if [ -f "$MODPATH/update_frpc.sh" ] && sh "$MODPATH/update_frpc.sh" --auto >> "$DATADIR/update.log" 2>&1; then
  ui_print "frpc ready."
else
  ui_print "frpc update failed. Use web UI update page after reboot."
fi

ui_print "web UI after reboot: http://127.0.0.1:62930"
ui_print "web login: no default username/password"
ui_print "Open web UI first, then set account in Account Settings."
ui_print "Config file: /data/adb/frpc/frpc.toml"
