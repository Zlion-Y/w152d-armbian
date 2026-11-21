#!/bin/busybox sh
# Read-only diagnostics, rendered to atomic static files. No incoming data runs commands.
BB=${BB:-/bin/busybox}
STATUS_DIR=${STATUS_DIR:-/run}
PORT=${PORT:-18080}
WEBROOT=$STATUS_DIR/w152d-http
$BB mkdir -p "$WEBROOT"

write_status() {
    {
        echo 'pid1_command='
        $BB tr '\000' ' ' < /proc/1/cmdline
        echo
        echo 'kernel='
        $BB cat /proc/version
        echo 'uptime='
        $BB cat /proc/uptime
        echo 'mounts='
        $BB cat /proc/mounts
        echo 'interfaces='
        $BB ip -4 addr
        echo 'memory='
        $BB head -5 /proc/meminfo
        for log in /run/w152d-boot.log /run/w152d-sshd.log; do
            if [ -f "$log" ]; then
                echo "log=$log"
                $BB tail -20 "$log"
            fi
        done
    } > "$STATUS_DIR/w152d-status.txt.new"
    $BB mv "$STATUS_DIR/w152d-status.txt.new" "$STATUS_DIR/w152d-status.txt"
    $BB cp "$STATUS_DIR/w152d-status.txt" "$WEBROOT/status.txt.new"
    $BB mv "$WEBROOT/status.txt.new" "$WEBROOT/status.txt"
    {
        printf '%s\n' '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="5"><title>W152D 系统状态</title>'
        printf '%s\n' '<style>body{font:16px system-ui,sans-serif;margin:32px auto;padding:0 20px;max-width:1000px;color:#183047;background:#f4f7fa}h1{font-size:28px}pre{font:14px ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px;border:1px solid #dbe2e9;border-radius:8px}a{color:#0756b8}</style>'
        printf '%s\n' '<h1>W152D 系统状态</h1><p>服务正常运行 · 每 5 秒刷新 · <a href="/status.txt">纯文本诊断</a></p><pre>'
        $BB sed 's/&/\&amp;/g;s/</\&lt;/g;s/>/\&gt;/g' "$STATUS_DIR/w152d-status.txt"
        printf '%s\n' '</pre></html>'
    } > "$WEBROOT/index.html.new"
    $BB mv "$WEBROOT/index.html.new" "$WEBROOT/index.html"
}

HTTPD_BB=
for candidate in /usr/local/libexec/w152d/busybox "$BB"; do
    if [ -x "$candidate" ] && "$candidate" --list | $BB grep -qx httpd; then
        HTTPD_BB=$candidate
        break
    fi
done

write_status
if [ -n "$HTTPD_BB" ]; then
    "$HTTPD_BB" httpd -f -p "0.0.0.0:$PORT" -h "$WEBROOT" -c /dev/null &
    http_pid=$!
    echo "$http_pid" > "$STATUS_DIR/w152d-httpd.pid"
    trap 'kill "$http_pid" 2>/dev/null; exit 0' TERM INT HUP
    while kill -0 "$http_pid" 2>/dev/null; do
        $BB sleep 2
        write_status
    done
    wait "$http_pid"
fi
