#
# opentelemetry-cpp-haproxy -- OpenTelemetry C++ SDK, patched for the HAProxy
#                              OTel filter stack.
#
# This is deliberately NOT a general-purpose opentelemetry-cpp package:
#
#   * it carries the six patches that opentelemetry-c-wrapper requires
#     (MaybeSpawnBackgroundThread() / SetBackgroundWaitFor() on the exporters),
#   * it is built with ABI version 2 (-DWITH_ABI_VERSION_2=ON), which is
#     source- and binary-incompatible with the default ABI version 1, and
#   * it bundles the exact third-party revisions the upstream build pins.
#
# Because of that it installs into a private prefix (%%{otel_prefix}) and must
# never be mistaken for, or used in place of, a system opentelemetry-cpp.
#
# See docs/versioning.md for where every pin below comes from.
#

%global otel_prefix     /opt/haproxy-otel
%global otel_libdir     %{otel_prefix}/%{_lib}
%global otel_includedir %{otel_prefix}/include

# Build the OTLP/gRPC exporter.  Turning this off drops the vendored gRPC,
# protobuf and Abseil trees and cuts the build time by roughly an order of
# magnitude, at the cost of losing the OTLP/gRPC transport.  OTLP/HTTP and
# OTLP/file keep working either way.
%bcond_without grpc

# The private libraries live outside the dynamic linker's search path and are
# reached through RPATH.  Keep them out of the global soname namespace, and do
# not let RPM turn them into unresolvable dependencies of their consumers.
%global __provides_exclude_from ^%{otel_libdir}/.*\\.so.*$
%global __requires_exclude ^lib(opentelemetry|ryml|c4core|protobuf|grpc|gpr|absl|upb|utf8_|address_sorting|re2|cares)

# Everything here is bundled on purpose; the debuginfo extractor should not
# trip over the vendored trees' own build ids.
%global _debugsource_packages 1

Name:           opentelemetry-cpp-haproxy
Version:        1.28.0
Release:        1%{?dist}
Summary:        OpenTelemetry C++ SDK (ABI v2, patched) for the HAProxy OTel filter

License:        Apache-2.0
URL:            https://github.com/open-telemetry/opentelemetry-cpp

# Source0 is NOT the plain upstream tarball.  gRPC and rapidyaml pull their own
# git submodules, which GitHub's generated tarballs do not contain, so the
# vendored tree is assembled by scripts/vendor-otelcpp.sh -- a transcription of
# upstream's own scripts/build/opentelemetry-cpp-monorepo.sh.
#
#   ./scripts/vendor-otelcpp.sh
#
Source0:        opentelemetry-cpp-monorepo-%{version}.tar.zst

# Patches, verbatim from opentelemetry-c-wrapper-3.3.0/scripts/build/.
# They must be applied in order and only ever to opentelemetry-cpp 1.28.0.
Patch0001:      0001-opentelemetry-cpp-1.28.0.patch
Patch0002:      0002-opentelemetry-cpp-1.28.0.patch
Patch0003:      0003-opentelemetry-cpp-1.28.0.patch
Patch0004:      0004-opentelemetry-cpp-1.28.0.patch
Patch0005:      0005-opentelemetry-cpp-1.28.0.patch
Patch0006:      0006-opentelemetry-cpp-1.28.0.patch

BuildRequires:  gcc-c++
BuildRequires:  cmake >= 3.14
BuildRequires:  make
BuildRequires:  pkgconfig
BuildRequires:  patch
BuildRequires:  zstd
# OpenSSL, curl and zlib are taken from the distribution, exactly as upstream's
# build-bundle.sh does (its aws-lc and curl steps are commented out).
BuildRequires:  openssl-devel
BuildRequires:  libcurl-devel
BuildRequires:  zlib-devel

# The SDK is only ever consumed through the wrapper, which lives in the same
# private prefix.  Nothing here is a system library.
Provides:       bundled(opentelemetry-cpp) = %{version}
Provides:       bundled(opentelemetry-proto) = 1.10.0
Provides:       bundled(nlohmann-json) = 3.12.0
Provides:       bundled(rapidyaml) = 0.15.2
%if %{with grpc}
Provides:       bundled(grpc) = 1.82.1
Provides:       bundled(protobuf) = 35.1
Provides:       bundled(abseil-cpp) = 20250512.1
%endif

%description
The OpenTelemetry C++ SDK built for the HAProxy OpenTelemetry filter.

This build differs from a stock opentelemetry-cpp in three ways that make it
unsuitable as a system library, and it is therefore installed privately under
%{otel_prefix}:

  * it applies the patch set shipped with opentelemetry-c-wrapper 3.3.0, which
    adds MaybeSpawnBackgroundThread() and SetBackgroundWaitFor() to the OTLP
    exporters so that thread and connection setup does not happen lazily on the
    first export;
  * it selects OpenTelemetry ABI version 2; and
  * it vendors the third-party revisions the wrapper was validated against.

%package devel
Summary:        Development files for %{name}
Requires:       %{name}%{?_isa} = %{version}-%{release}

%description devel
Headers, pkg-config files and CMake package files for the private
OpenTelemetry C++ SDK used by the HAProxy OpenTelemetry filter.

%prep
%setup -q -n opentelemetry-cpp-monorepo-%{version}

# Upstream applies these with `git apply` from a git checkout; the vendored
# tree has its VCS metadata stripped, so plain patch(1) is used instead.  Both
# were verified to apply cleanly to a pristine v1.28.0 tree.
%patch -P 1 -p1
%patch -P 2 -p1
%patch -P 3 -p1
%patch -P 4 -p1
%patch -P 5 -p1
%patch -P 6 -p1

%build
mkdir -p build
cd build

# The flags below are a transcription of upstream's
# opentelemetry-cpp-1.28.0-install.sh, with three deliberate deviations:
#
#   * distribution build flags replace the plain -O2, so the result carries the
#     same hardening as the rest of the OS;
#   * the install prefix is the private one; and
#   * find_package() is disabled for the vendored dependencies (upstream does
#     the same via the .monorepo marker in common.sh) so that a package
#     installed on the build host cannot hijack the build.
#
cmake \
    -DCMAKE_INSTALL_PREFIX=%{otel_prefix} \
    -DCMAKE_INSTALL_LIBDIR=%{_lib} \
    -DCMAKE_INSTALL_INCLUDEDIR=include \
    -DCMAKE_INSTALL_RPATH=%{otel_libdir} \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="%{build_cflags}" \
    -DCMAKE_CXX_FLAGS="%{build_cxxflags}" \
    -DCMAKE_EXE_LINKER_FLAGS="%{build_ldflags}" \
    -DCMAKE_SHARED_LINKER_FLAGS="%{build_ldflags}" \
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
    -DCMAKE_CXX_STANDARD=17 \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DCMAKE_VERBOSE_MAKEFILE:BOOL=ON \
    -DFETCHCONTENT_FULLY_DISCONNECTED=ON \
    -DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF \
    -DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF \
    -DCMAKE_DISABLE_FIND_PACKAGE_ryml=ON \
%if %{with grpc}
    -DCMAKE_DISABLE_FIND_PACKAGE_gRPC=ON \
    -DCMAKE_DISABLE_FIND_PACKAGE_Protobuf=ON \
    -DCMAKE_DISABLE_FIND_PACKAGE_absl=ON \
%endif
    -DBUILD_PACKAGE=ON \
    -DCURL_LIBRARY=%{_libdir}/libcurl.so \
    -DZLIB_LIBRARY=%{_libdir}/libz.so \
    -DZLIB_INCLUDE_DIR=%{_includedir} \
    -DWITH_ABI_VERSION_1=OFF \
    -DWITH_ABI_VERSION_2=ON \
    -DWITH_CONFIGURATION=ON \
    -DOPENTELEMETRY_INSTALL=ON \
    -DWITH_NO_DEPRECATED_CODE=ON \
    -DWITH_OTLP_GRPC=%{?with_grpc:ON}%{!?with_grpc:OFF} \
    -DWITH_OTLP_HTTP=ON \
    -DWITH_OTLP_FILE=ON \
    -DWITH_OTLP_HTTP_COMPRESSION=ON \
    -DWITH_ZIPKIN=ON \
    -DWITH_ELASTICSEARCH=ON \
    -DOTELCPP_VERSIONED_LIBS=ON \
    -DWITH_ASYNC_EXPORT_PREVIEW=ON \
    -DWITH_THREAD_INSTRUMENTATION_PREVIEW=ON \
    -DWITH_METRICS_EXEMPLAR_PREVIEW=ON \
    -DWITH_OPENTRACING=OFF \
    -DWITH_BENCHMARK=OFF \
    -DWITH_EXAMPLES=OFF \
    -DWITH_FUNC_TESTS=OFF \
    -DBUILD_TESTING=OFF \
    -DBUILD_SHARED_LIBS=ON \
    ..

%make_build

%install
cd build
%make_install

# rapidyaml and c4core install into <prefix>/lib even where the platform libdir
# is lib64; upstream's install script works around the same bug.  Fold them
# back into the real libdir and fix the paths recorded in the CMake package
# files.
if [ "%{_lib}" != "lib" ] && [ -d %{buildroot}%{otel_prefix}/lib ]; then
    mkdir -p %{buildroot}%{otel_libdir}/cmake %{buildroot}%{otel_libdir}/pkgconfig
    for f in %{buildroot}%{otel_prefix}/lib/cmake/*/*; do
        [ -e "$f" ] || continue
        sed -i 's#/lib/#/%{_lib}/#g' "$f"
    done
    for d in %{buildroot}%{otel_prefix}/lib/cmake/*; do
        [ -e "$d" ] || continue
        cp -a "$d" %{buildroot}%{otel_libdir}/cmake/
    done
    for f in %{buildroot}%{otel_prefix}/lib/pkgconfig/*; do
        [ -e "$f" ] || continue
        cp -a "$f" %{buildroot}%{otel_libdir}/pkgconfig/
    done
    find %{buildroot}%{otel_prefix}/lib -maxdepth 1 \( -name '*.so*' -o -name '*.a' \) \
        -exec cp -a {} %{buildroot}%{otel_libdir}/ \;
    rm -rf %{buildroot}%{otel_prefix}/lib
fi

# Static archives are never shipped: the wrapper links the shared libraries.
find %{buildroot}%{otel_prefix} -name '*.a' -delete

# The private prefix is not on the linker's search path, so no ldconfig cache
# entry is wanted; drop any leftover libtool archives too.
find %{buildroot}%{otel_prefix} -name '*.la' -delete

%files
%license LICENSE
%dir %{otel_prefix}
%dir %{otel_libdir}
%{otel_libdir}/*.so.*

%files devel
%doc README.md CHANGELOG.md
%dir %{otel_includedir}
%{otel_includedir}/*
%{otel_libdir}/*.so
%{otel_libdir}/cmake/
%{otel_libdir}/pkgconfig/

%changelog
* Fri Aug 21 2026 stevapple <stevapple2013@gmail.com> - 1.28.0-1
- Initial packaging of the patched, ABI v2 OpenTelemetry C++ SDK
- Pins and CMake options transcribed from opentelemetry-c-wrapper 3.3.0
