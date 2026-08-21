#!/bin/bash
#
# Build the whole package set, in dependency order, inside the current system.
# Intended to run in the image built from Containerfile.
#
#   opentelemetry-cpp-haproxy  ->  opentelemetry-c-wrapper  ->  haproxy-otel
#
# Each package is installed after it is built, because the next one build-
# requires it.  Set NO_INSTALL=1 to build without installing (only useful for
# the first package on its own).
#
# Output lands in ${TOPDIR}/RPMS and ${TOPDIR}/SRPMS.
#
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"
# shellcheck disable=SC1091
. ./versions.env

TOPDIR="${TOPDIR:-$REPO_ROOT/rpmbuild}"
ONLY="${1:-all}"

mkdir -p "$TOPDIR"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
cp -f SOURCES/* "$TOPDIR/SOURCES/" 2>/dev/null || true
cp -f SPECS/*.spec "$TOPDIR/SPECS/"

rpmbuild_opts=(
    --define "_topdir $TOPDIR"
    --define "dist .${DIST_TAG}"
)
# Pass through e.g. RPM_WITH="--without grpc"
if [ -n "${RPM_WITH:-}" ]; then
    # shellcheck disable=SC2206
    rpmbuild_opts+=(${RPM_WITH})
fi

build_one() { # spec-basename
    local spec="$1"
    echo
    echo "################################################################"
    echo "### building $spec"
    echo "################################################################"
    rpmbuild "${rpmbuild_opts[@]}" -ba "$TOPDIR/SPECS/$spec"

    if [ "${NO_INSTALL:-0}" != "1" ]; then
        # Install what was just produced so the next spec can build against it.
        # --nodeps is deliberate: the private OTel sonames are filtered out of
        # the generated requires (see the specs), so there is nothing to resolve
        # and nothing to pull in.
        find "$TOPDIR/RPMS" -name '*.rpm' ! -name '*debuginfo*' ! -name '*debugsource*' \
            -newer "$TOPDIR/SPECS/$spec" -print0 \
            | xargs -0 --no-run-if-empty rpm -Uvh --force --nodeps
    fi
}

case "$ONLY" in
    otelcpp)  build_one opentelemetry-cpp-haproxy.spec ;;
    wrapper)  build_one opentelemetry-c-wrapper.spec ;;
    haproxy)  build_one haproxy-otel.spec ;;
    all)
        build_one opentelemetry-cpp-haproxy.spec
        build_one opentelemetry-c-wrapper.spec
        build_one haproxy-otel.spec
        ;;
    *)
        echo "usage: $0 [all|otelcpp|wrapper|haproxy]" >&2
        exit 2
        ;;
esac

echo
echo "==> built packages"
find "$TOPDIR/RPMS" "$TOPDIR/SRPMS" -name '*.rpm' -printf '%p\t%s bytes\n' | sort
