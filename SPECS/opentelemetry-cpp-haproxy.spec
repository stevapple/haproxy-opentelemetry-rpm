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

# Vendored rapidyaml tag; see %%prep and docs/versioning.md.
%global ryml_tag        v0.10.0

%global otel_prefix     /opt/haproxy-otel
%global otel_libdir     %{otel_prefix}/%{_lib}
%global otel_includedir %{otel_prefix}/include

# Build the OTLP/gRPC exporter.  Turning this off drops the vendored gRPC tree
# -- by far the longest part of the build -- at the cost of losing the OTLP/gRPC
# transport.  OTLP/HTTP and OTLP/file keep working either way.  protobuf and
# Abseil are built regardless, because OTLP/HTTP needs opentelemetry-proto.
#
# find_package() stays disabled for every vendored dependency in both cases, so
# a package installed on the build host can never be substituted for a pin.
%bcond_without grpc

# The libraries carry a RUNPATH into the private prefix.  That is the whole
# point of the design -- the OTel stack is deliberately kept off the dynamic
# linker's search path so it cannot shadow a system opentelemetry-cpp, and an
# ld.so.conf.d drop-in would defeat that -- so the generic rpath check, which
# rejects any RPATH outside the standard library directories, must not veto it.
%global __brp_check_rpaths %{nil}

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
Provides:       bundled(rapidyaml) = 0.10.0
# protobuf and Abseil are bundled regardless of the grpc bcond: the OTLP/HTTP
# exporter needs opentelemetry-proto, which needs protobuf, which needs Abseil.
# Only gRPC itself is optional.
Provides:       bundled(protobuf) = 35.1
Provides:       bundled(abseil-cpp) = 20250512.1
%if %{with grpc}
Provides:       bundled(grpc) = 1.82.1
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
# Upstream applies the patch series with `git apply` from a git checkout; the
# vendored tree has its VCS metadata stripped, so %%autosetup's patch(1) is used
# instead.  All six were verified to apply cleanly to a pristine v1.28.0 tree.
%autosetup -p1 -n opentelemetry-cpp-monorepo-%{version}

# The vendored rapidyaml is 0.10.0, not the v0.15.2 this release's
# third_party_release names -- opentelemetry-c-wrapper 3.3.0 only compiles
# against the pre-0.11 ryml callback API, and opentelemetry-cpp supports both
# through RYML_VERSION_MINOR guards.  The compile guards read ryml's own
# headers and are therefore already correct; this keeps the version CMake
# reports for the dependency honest as well, since the file is parsed with an
# unconditional set() that a -D on the command line cannot override.
sed -i 's/^ryml=.*/ryml=%{ryml_tag}/' third_party_release
grep -q '^ryml=%{ryml_tag}$' third_party_release

%build
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
# That last point is not theoretical.  nlohmann_json was missing from the
# disable list at first, and because CMake searches CMAKE_INSTALL_PREFIX,
# find_package() picked up the copy an *earlier build of this very package* had
# left in %%{otel_prefix}.  The vendored one was then never built or installed,
# so the resulting -devel package shipped SDK headers (the Zipkin and
# Elasticsearch exporters) that #include <nlohmann/json.hpp> without shipping
# that header -- and whether it happened at all depended on what was installed
# on the build host.  Every vendored dependency must be listed here.
#
# Each vendored dependency is mapped with an explicit FETCHCONTENT_SOURCE_DIR_*
# rather than by letting FetchContent guess <binary dir>/_deps/<name>-src:
#
#   * %%cmake builds out of tree, so the default base dir is not where the
#     vendored sources are; and
#   * the directory names upstream's monorepo script uses do not all match the
#     names the dependencies declare.  protobuf 35.1 declares Abseil as "absl"
#     and so looks for "absl-src", while the monorepo script checks it out as
#     "abseil-cpp-src".  Relying on the convention fails the configure step with
#     "Cannot find abseil-cpp dependency that's needed to build protobuf".
#
# FETCHCONTENT_FULLY_DISCONNECTED stays on as a guard: any dependency not
# mapped above fails the build instead of silently reaching for the network,
# which is what keeps this an offline build.
#
%cmake \
    -DCMAKE_INSTALL_PREFIX=%{otel_prefix} \
    -DCMAKE_INSTALL_LIBDIR=%{_lib} \
    -DCMAKE_INSTALL_INCLUDEDIR=include \
    -DCMAKE_INSTALL_RPATH=%{otel_libdir} \
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
    -DCMAKE_CXX_STANDARD=17 \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DFETCHCONTENT_FULLY_DISCONNECTED=ON \
    -DFETCHCONTENT_SOURCE_DIR_ABSL="$PWD/build/_deps/abseil-cpp-src" \
    -DFETCHCONTENT_SOURCE_DIR_PROTOBUF="$PWD/build/_deps/protobuf-src" \
    -DFETCHCONTENT_SOURCE_DIR_RYML="$PWD/build/_deps/ryml-src" \
    -DFETCHCONTENT_SOURCE_DIR_CURL="$PWD/build/_deps/curl-src" \
    -DFETCHCONTENT_SOURCE_DIR_NLOHMANN_JSON="$PWD/third_party/nlohmann-json" \
    -DFETCHCONTENT_SOURCE_DIR_OPENTELEMETRY-PROTO="$PWD/third_party/opentelemetry-proto" \
%if %{with grpc}
    -DFETCHCONTENT_SOURCE_DIR_GRPC="$PWD/build/_deps/grpc-src" \
%endif
    -DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF \
    -DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF \
    -DCMAKE_DISABLE_FIND_PACKAGE_ryml=ON \
    -DCMAKE_DISABLE_FIND_PACKAGE_gRPC=ON \
    -DCMAKE_DISABLE_FIND_PACKAGE_Protobuf=ON \
    -DCMAKE_DISABLE_FIND_PACKAGE_absl=ON \
    -DCMAKE_DISABLE_FIND_PACKAGE_nlohmann_json=ON \
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
    -DBUILD_SHARED_LIBS=ON

%cmake_build

%install
%cmake_install

# Several of the vendored dependencies install into <prefix>/lib even where the
# platform libdir is lib64 -- rapidyaml and c4core always, gRPC and protobuf
# when they are built.  Upstream's install script works around the same bug.
# Fold whatever landed there into the real libdir, and fix the paths recorded
# in the CMake package and pkg-config files.
#
# Only regular files are rewritten: gRPC installs a cmake/grpc/modules/
# directory, and sed(1) fails on a directory rather than skipping it.
if [ "%{_lib}" != "lib" ] && [ -d %{buildroot}%{otel_prefix}/lib ]; then
    find %{buildroot}%{otel_prefix}/lib -type f \( -name '*.cmake' -o -name '*.pc' \) \
        -exec sed -i 's#/lib/#/%{_lib}/#g' {} +
    mkdir -p %{buildroot}%{otel_libdir}
    cp -a %{buildroot}%{otel_prefix}/lib/. %{buildroot}%{otel_libdir}/
    rm -rf %{buildroot}%{otel_prefix}/lib
fi

# Static archives are never shipped: the wrapper links the shared libraries.
find %{buildroot}%{otel_prefix} -name '*.a' -delete

# Some dependency versions put their CMake package and pkg-config files under
# share/ rather than the libdir (rapidyaml does so from 0.11 on; 0.10 does
# not).  Fold anything that lands there into the libdir so the packaged layout
# is the same either way, and so %%files does not have to know which happened.
if [ -d %{buildroot}%{otel_prefix}/share ]; then
    for sub in cmake pkgconfig; do
        if [ -d %{buildroot}%{otel_prefix}/share/$sub ]; then
            mkdir -p %{buildroot}%{otel_libdir}/$sub
            cp -a %{buildroot}%{otel_prefix}/share/$sub/. \
                  %{buildroot}%{otel_libdir}/$sub/
        fi
    done
    rm -rf %{buildroot}%{otel_prefix}/share
fi

# protobuf installs protoc and its upb code generators into the prefix.  They
# are build-time tools -- everything that needed them ran during %%build, and
# the only consumer of this stack (the C wrapper) resolves it through
# pkg-config, not through protobuf's CMake targets -- so they are not shipped.
rm -rf %{buildroot}%{otel_prefix}/bin

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
