# Build image for the haproxy-otel package set.
#
# Base is Red Hat's UBI 10, so the toolchain and runtime match RHEL 10 -- and
# therefore Rocky 10 -- exactly.  The repository and package setup lives in
# scripts/setup-buildenv.sh, which the CI pipelines run too, so the container
# and CI build environments cannot drift apart.
#
#   podman build -t haproxy-otel-builder -f Containerfile .
#   podman run --rm -v "$PWD:/build:z" haproxy-otel-builder ./scripts/build-all.sh
#
ARG UBI_IMAGE=registry.access.redhat.com/ubi10/ubi:latest
FROM ${UBI_IMAGE}

ARG ROCKY_RELEASE=10
ENV ROCKY_RELEASE=${ROCKY_RELEASE}

COPY scripts/setup-buildenv.sh /tmp/setup-buildenv.sh
RUN /tmp/setup-buildenv.sh && rm -f /tmp/setup-buildenv.sh

WORKDIR /build
