#!/bin/busybox sh
# Fixed, read-only HTTP response. Incoming data is discarded, never executed.
BB=${BB:-/bin/busybox}
STATUS_DIR=${STATUS_DIR:-/run}
PORT=${PORT:-18080}
PROBE_PHASE=${PROBE_PHASE:-NATIVE_RAM_INIT}
PROBE_TOKEN=${PROBE_TOKEN:-unset}
while :; do
    {
        echo "W152D_PROBE_TOKEN=$PROBE_TOKEN"
        echo "phase=$PROBE_PHASE"
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
        for log in /run/w152d-bootstrap.log /run/w152d-boot.log /run/w152d-sshd.log; do
            if [ -f "$log" ]; then
                echo "log=$log"
                $BB tail -20 "$log"
            fi
        done
    } > "$STATUS_DIR/w152d-status.txt"
    length=$($BB wc -c < "$STATUS_DIR/w152d-status.txt")
    {
        printf 'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %s\r\nConnection: close\r\n\r\n' "$length"
        $BB cat "$STATUS_DIR/w152d-status.txt"
    } | $BB nc -l -p "$PORT" -w 3 > /dev/null
    $BB sleep 1
done
