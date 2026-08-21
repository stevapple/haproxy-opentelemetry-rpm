#!/bin/bash
#
# Post-install verification: prove the shipped binary really carries a working
# OTel filter, and that the example configuration parses.
#
# Run against installed RPMs (in a container, after `rpm -Uvh` of the built
# packages).  The spec's own %check covers the buildroot binary; this covers the
# installed one, including that RUNPATH resolves without LD_LIBRARY_PATH.
#
set -euo pipefail

fail=0
note() { printf '  %-58s %s\n' "$1" "$2"; }
check() { # description command...
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then note "$desc" "OK"; else note "$desc" "FAIL"; fail=1; fi
}

echo "==> haproxy -vv"
haproxy -vv | sed 's/^/    /'
echo

echo "==> checks"

# The filter is compiled in.
check "OpenTelemetry support reported" \
    bash -c "haproxy -vv | grep -qi 'Built with OpenTelemetry support'"
check "[OTEL] filter registered" \
    bash -c "haproxy -vv | grep -q '\[OTEL\] opentelemetry'"

# The dummy wrapper reports "C++ version none" and emits no telemetry; a real
# build must never report it.
if haproxy -vv 2>/dev/null | grep -qi 'C++ version none'; then
    note "linked against real wrapper (not dummy)" "FAIL"
    fail=1
else
    note "linked against real wrapper (not dummy)" "OK"
fi

# RUNPATH must resolve on its own -- no LD_LIBRARY_PATH, no ldconfig entry.
if ldd "$(command -v haproxy)" 2>/dev/null | grep -q 'not found'; then
    note "all shared libraries resolve via RUNPATH" "FAIL"
    ldd "$(command -v haproxy)" | grep 'not found' | sed 's/^/      /'
    fail=1
else
    note "all shared libraries resolve via RUNPATH" "OK"
fi

# The example configuration must actually parse. Build a throwaway config that
# wires the shipped otel.cfg into a frontend, which is what a user would do.
workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

sed 's#/etc/haproxy/otel.yml#'"$workdir"'/otel.yml#' \
    /etc/haproxy/otel.cfg.example > "$workdir/otel.cfg"
cp /etc/haproxy/otel.yml.example "$workdir/otel.yml"

cat > "$workdir/haproxy.cfg" <<EOF
global
    daemon

defaults
    mode http
    timeout connect 5s
    timeout client  30s
    timeout server  30s

frontend smoke-fe
    bind 127.0.0.1:18080
    filter opentelemetry id otel config $workdir/otel.cfg
    default_backend smoke-be

backend smoke-be
    server s1 127.0.0.1:18081
EOF

if haproxy -c -f "$workdir/haproxy.cfg" >"$workdir/parse.log" 2>&1; then
    note "shipped example configuration parses" "OK"
else
    note "shipped example configuration parses" "FAIL"
    sed 's/^/      /' "$workdir/parse.log"
    fail=1
fi

echo
if [ "$fail" -eq 0 ]; then
    echo "==> all checks passed"
else
    echo "==> FAILURES above" >&2
fi
exit "$fail"
