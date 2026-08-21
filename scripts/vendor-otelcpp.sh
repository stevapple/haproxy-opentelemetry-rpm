#!/bin/bash
#
# Assemble the vendored opentelemetry-cpp source tarball consumed by
# SPECS/opentelemetry-cpp-haproxy.spec.
#
# WHY THIS EXISTS
# ---------------
# opentelemetry-cpp resolves its third-party dependencies through CMake's
# FetchContent, which downloads at configure time.  RPM builds have no network,
# so the sources have to be in the SRPM.  A plain GitHub release tarball is not
# enough either: gRPC and rapidyaml carry their own git submodules, which
# GitHub's generated archives omit.
#
# This script is a transcription of upstream's
#   opentelemetry-c-wrapper-3.3.0/scripts/build/opentelemetry-cpp-monorepo.sh
# with two deliberate differences:
#
#   * VCS metadata is stripped afterwards, since the spec applies the patch set
#     with patch(1) rather than `git apply`.  That removes roughly two thirds of
#     the uncompressed size.
#   * The output is a tarball rather than a working tree.
#
# The pins below MUST stay in sync with versions.env and with upstream's
# monorepo script.  See docs/versioning.md.
#
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"
# shellcheck disable=SC1091
. ./versions.env

for tool in git zstd tar; do
    command -v "$tool" >/dev/null || { echo "ERROR: $tool is required but not installed" >&2; exit 1; }
done

WORK="${WORK:-$(mktemp -d)}"
OUT="${OUT:-$REPO_ROOT/SOURCES}"
TREE="opentelemetry-cpp-monorepo-${OTELCPP_VERSION}"
TARBALL="$OUT/${TREE}.tar.zst"

if [ -f "$TARBALL" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "==> $TARBALL already present (FORCE=1 to rebuild)"
    exit 0
fi

# repo <tab> tag <tab> destination <tab> submodule-depth (0 none, 1 shallow, 2 recursive)
#
# Destinations mirror what opentelemetry-cpp's CMake expects: submodules under
# third_party/, FetchContent dependencies under build/_deps/<name>-src (the
# default FETCHCONTENT_BASE_DIR layout, which the spec pairs with
# -DFETCHCONTENT_FULLY_DISCONNECTED=ON).
read -r -d '' DEPS <<EOF || true
open-telemetry/opentelemetry-proto	${OTEL_PROTO_TAG}	third_party/opentelemetry-proto	0
nlohmann/json	${NLOHMANN_JSON_TAG}	third_party/nlohmann-json	0
microsoft/GSL	${MS_GSL_TAG}	third_party/ms-gsl	0
jupp0r/prometheus-cpp	${PROMETHEUS_CPP_TAG}	third_party/prometheus-cpp	0
opentracing/opentracing-cpp	${OPENTRACING_CPP_TAG}	third_party/opentracing-cpp	0
google/googletest	${GOOGLETEST_TAG}	third_party/googletest	0
google/benchmark	${BENCHMARK_TAG}	third_party/benchmark	0
abseil/abseil-cpp	${ABSEIL_TAG}	build/_deps/abseil-cpp-src	0
protocolbuffers/protobuf	${PROTOBUF_TAG}	build/_deps/protobuf-src	0
grpc/grpc	${GRPC_TAG}	build/_deps/grpc-src	1
biojppm/rapidyaml	${RYML_TAG}	build/_deps/ryml-src	2
madler/zlib	${ZLIB_TAG}	build/_deps/zlib-src	0
curl/curl	${CURL_TAG}	build/_deps/curl-src	0
EOF

echo "==> assembling $TREE in $WORK"
rm -rf "${WORK:?}/$TREE"
mkdir -p "$WORK"
cd "$WORK"

clone() { # repo tag dest submodules
    local repo="$1" tag="$2" dest="$3" sub="$4"
    echo "    -> $repo @ $tag"
    git -c advice.detachedHead=false clone --quiet --single-branch --depth 1 \
        --branch "$tag" "https://github.com/${repo}.git" "$dest"
    case "$sub" in
        1) git -C "$dest" submodule --quiet update --init --depth 1 ;;
        2) git -C "$dest" submodule --quiet update --init --recursive --depth 1 ;;
    esac
}

clone open-telemetry/opentelemetry-cpp "v${OTELCPP_VERSION}" "$TREE" 0

while IFS=$'\t' read -r repo tag dest sub; do
    [ -n "${repo:-}" ] || continue
    mkdir -p "$TREE/$(dirname "$dest")"
    clone "$repo" "$tag" "$TREE/$dest" "$sub"
done <<< "$DEPS"

echo "==> stripping VCS metadata"
find "$TREE" -name '.git' -prune -exec rm -rf {} + 2>/dev/null || true
find "$TREE" -maxdepth 3 -name '.gitmodules' -delete 2>/dev/null || true

# Record what went in, so a built RPM can be traced back to exact revisions.
{
    echo "# Assembled by scripts/vendor-otelcpp.sh"
    echo "opentelemetry-cpp	v${OTELCPP_VERSION}"
    while IFS=$'\t' read -r repo tag _ _; do
        [ -n "${repo:-}" ] && printf '%s\t%s\n' "$repo" "$tag"
    done <<< "$DEPS"
} > "$TREE/.vendored-pins"

echo "==> packing $TARBALL"
mkdir -p "$OUT"
tar --sort=name --owner=0 --group=0 --numeric-owner \
    --mtime="@0" \
    -I 'zstd -12 -T0' -cf "$TARBALL" "$TREE"

echo "==> done: $(du -h "$TARBALL" | cut -f1)  $TARBALL"
sha256sum "$TARBALL"
