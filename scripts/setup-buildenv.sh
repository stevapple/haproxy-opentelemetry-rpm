#!/bin/bash
#
# Configure a UBI 10 container as a build host for the haproxy-otel package set.
#
# Shared by Containerfile, the GitHub Actions workflow and the Woodpecker
# pipeline so the three cannot drift apart.
#
# UBI's repositories are a subset of RHEL's and lack several -devel packages
# this build needs (lua-devel, autoconf-archive, ...).  Rocky 10's
# AppStream/CRB and EPEL are layered on for those.  Rocky 10 is an ABI-identical
# RHEL 10 rebuild, so build-requires resolved from it produce the same binaries,
# and Rocky is where these RPMs are meant to be installed anyway.
#
set -euo pipefail

ROCKY_RELEASE="${ROCKY_RELEASE:-10}"

echo "==> enabling Rocky ${ROCKY_RELEASE} and EPEL repositories"

dnf -y install dnf-plugins-core findutils

rpm --import "https://dl.rockylinux.org/pub/rocky/RPM-GPG-KEY-Rocky-${ROCKY_RELEASE}"

cat > /etc/yum.repos.d/rocky.repo <<EOF
[rocky-baseos]
name=Rocky Linux ${ROCKY_RELEASE} - BaseOS
mirrorlist=https://mirrors.rockylinux.org/mirrorlist?arch=\$basearch&repo=BaseOS-${ROCKY_RELEASE}
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-Rocky-${ROCKY_RELEASE}
enabled=1

[rocky-appstream]
name=Rocky Linux ${ROCKY_RELEASE} - AppStream
mirrorlist=https://mirrors.rockylinux.org/mirrorlist?arch=\$basearch&repo=AppStream-${ROCKY_RELEASE}
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-Rocky-${ROCKY_RELEASE}
enabled=1

[rocky-crb]
name=Rocky Linux ${ROCKY_RELEASE} - CRB
mirrorlist=https://mirrors.rockylinux.org/mirrorlist?arch=\$basearch&repo=CRB-${ROCKY_RELEASE}
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-Rocky-${ROCKY_RELEASE}
enabled=1
EOF

# EPEL is optional: only autoconf-archive tends to come from it, and some
# mirrors of CRB carry that too.
dnf -y install "https://dl.fedoraproject.org/pub/epel/epel-release-latest-${ROCKY_RELEASE}.noarch.rpm" || \
    echo "    (EPEL unavailable, continuing)"

echo "==> installing toolchain and RPM machinery"
dnf -y install \
    gcc gcc-c++ make cmake git patch which tar \
    rpm-build rpmdevtools \
    autoconf automake libtool autoconf-archive \
    pkgconf-pkg-config zstd \
    systemd-rpm-macros

echo "==> installing build requirements"
dnf -y install \
    openssl-devel libcurl-devel zlib-devel \
    lua-devel pcre2-devel systemd-devel libxcrypt-devel

dnf -y clean all

echo "==> build environment ready"
cmake --version | head -1
gcc --version | head -1
rpmbuild --version
