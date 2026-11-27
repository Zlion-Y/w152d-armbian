#!/usr/bin/env bash
set -euo pipefail

args=()
for a in "$@"; do
    case "$a" in
        -fmin-function-alignment=*|-fstrict-flex-arrays=*) ;;
        *) args+=("$a") ;;
    esac
done

exec "${REAL_CC:-${CROSS_COMPILE:-}gcc}" -falign-functions=4 "${args[@]}"
