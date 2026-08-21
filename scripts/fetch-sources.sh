#!/bin/bash
#
# Download the upstream release tarballs the specs need into SOURCES/.
#
# The vendored opentelemetry-cpp tree is NOT fetched here -- it is assembled by
# scripts/vendor-otelcpp.sh, because it needs git submodules that release
# tarballs do not contain.
#
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
. ./versions.env

OUT="SOURCES"
mkdir -p "$OUT"

haproxy_branch="${HAPROXY_VERSION%.*}"

fetch() { # url filename
    local url="$1" name="$2"
    if [ -s "$OUT/$name" ]; then
        echo "==> $name already present"
        return 0
    fi
    echo "==> fetching $name"
    curl -fsSL --retry 3 --retry-delay 2 -o "$OUT/$name.part" "$url"
    mv "$OUT/$name.part" "$OUT/$name"
}

fetch "https://www.haproxy.org/download/${haproxy_branch}/src/haproxy-${HAPROXY_VERSION}.tar.gz" \
      "haproxy-${HAPROXY_VERSION}.tar.gz"

fetch "https://github.com/haproxytech/haproxy-opentelemetry/archive/refs/tags/v${OTEL_FILTER_VERSION}.tar.gz" \
      "haproxy-opentelemetry-${OTEL_FILTER_VERSION}.tar.gz"

fetch "https://github.com/haproxytech/opentelemetry-c-wrapper/archive/refs/tags/v${OTEL_WRAPPER_VERSION}.tar.gz" \
      "opentelemetry-c-wrapper-${OTEL_WRAPPER_VERSION}.tar.gz"

echo
echo "==> SOURCES/"
ls -la "$OUT"
