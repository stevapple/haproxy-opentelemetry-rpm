#
# opentelemetry-c-wrapper -- the C API over the OpenTelemetry C++ SDK that the
#                            HAProxy OTel filter links against.
#
# The wrapper version is not a free choice: haproxy-opentelemetry 2.2.0 names
# 3.3.0 explicitly, and 3.3.0 in turn only builds against the patched, ABI v2
# opentelemetry-cpp 1.28.0 shipped by opentelemetry-cpp-haproxy.  The three
# versions move together; see docs/versioning.md.
#

%global otel_prefix     /opt/haproxy-otel
%global otel_libdir     %{otel_prefix}/%{_lib}
%global otel_includedir %{otel_prefix}/include

# Same rationale as in opentelemetry-cpp-haproxy.spec: the private prefix is
# outside the dynamic linker's search path and is reached through RPATH.
%global __provides_exclude_from ^%{otel_libdir}/.*\\.so.*$
%global __requires_exclude ^lib(opentelemetry|ryml|c4core|protobuf|grpc|gpr|absl|upb|utf8_|address_sorting|re2|cares)

Name:           opentelemetry-c-wrapper
Version:        3.3.0
Release:        1%{?dist}
Summary:        C wrapper for the OpenTelemetry C++ SDK, as used by HAProxy

License:        Apache-2.0
URL:            https://github.com/haproxytech/opentelemetry-c-wrapper
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz#/%{name}-%{version}.tar.gz

BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  make
BuildRequires:  autoconf
BuildRequires:  automake
BuildRequires:  libtool
# configure.ac fails explicitly without AX_CHECK_COMPILE_FLAG / AX_CXX_COMPILE_STDCXX.
BuildRequires:  autoconf-archive
BuildRequires:  pkgconfig
BuildRequires:  opentelemetry-cpp-haproxy-devel = 1.28.0

Requires:       opentelemetry-cpp-haproxy%{?_isa} = 1.28.0

%description
A pure C API on top of the OpenTelemetry C++ client, developed by HAProxy
Technologies for the HAProxy OpenTelemetry filter.  It covers the three OTel
signals -- traces, metrics and logs -- and is configured through a single YAML
file.

This build links the private, ABI v2 OpenTelemetry C++ SDK from
opentelemetry-cpp-haproxy and is installed alongside it under %{otel_prefix}.

%package devel
Summary:        Development files for %{name}
Requires:       %{name}%{?_isa} = %{version}-%{release}
Requires:       opentelemetry-cpp-haproxy-devel = 1.28.0

%description devel
Headers and pkg-config file for the OpenTelemetry C wrapper library.  Required
to build HAProxy with the OpenTelemetry filter.

%prep
%autosetup -n %{name}-%{version}

%build
./scripts/bootstrap

# --libdir must be given explicitly: autotools would otherwise default to
# ${exec_prefix}/lib even on a lib64 platform, and the wrapper's own .pc file
# bakes ${libdir} into the RPATH it hands to consumers.
#
# --with-opentelemetry points at the private prefix; the macro appends the
# platform libdir when it looks for the SDK's pkgconfig directory.
%configure \
    --prefix=%{otel_prefix} \
    --libdir=%{otel_libdir} \
    --includedir=%{otel_includedir} \
    --with-opentelemetry=%{otel_prefix} \
    --with-rapidyaml=%{otel_prefix} \
    --disable-static \
    --disable-silent-rules

%make_build

%install
%make_install

find %{buildroot}%{otel_prefix} -name '*.la' -delete

# doc_DATA lands in <prefix>/share/doc; %%doc/%%license below ship these from
# the source tree instead, so drop the duplicate copy.
rm -rf %{buildroot}%{otel_prefix}/share/doc

%check
# The wrapper's own test suite needs a live collector, so it is not run here.
# What is checked is that the artefacts the next package build-requires are
# actually present and internally consistent -- a wrapper that configured
# against the wrong SDK, or installed into the wrong libdir, fails here rather
# than at the haproxy link step.
test -e %{buildroot}%{otel_libdir}/lib%{name}.so
test -e %{buildroot}%{otel_libdir}/pkgconfig/%{name}.pc

# The .pc must advertise this version and point back into the private prefix;
# haproxy's Makefile.mk resolves the addon purely through pkg-config.
PKG_CONFIG_PATH=%{buildroot}%{otel_libdir}/pkgconfig \
    pkg-config --exists --print-errors %{name}
test "$(PKG_CONFIG_PATH=%{buildroot}%{otel_libdir}/pkgconfig \
    pkg-config --modversion %{name})" = "%{version}"
PKG_CONFIG_PATH=%{buildroot}%{otel_libdir}/pkgconfig \
    pkg-config --libs %{name} | grep -q -- '-L%{otel_libdir}'

# Every dependency must resolve through RUNPATH alone, with no help from
# LD_LIBRARY_PATH -- that is what makes the private prefix work at runtime.
! ldd %{buildroot}%{otel_libdir}/lib%{name}.so | grep 'not found'

%files
%license LICENSE COPYING
%doc README.md ChangeLog AUTHORS
%dir %{otel_prefix}
%dir %{otel_libdir}
%{otel_libdir}/lib%{name}.so.*

%files devel
%doc README-configuration INSTALL
%dir %{otel_includedir}
%{otel_includedir}/%{name}/
%{otel_libdir}/lib%{name}.so
%{otel_libdir}/pkgconfig/%{name}.pc

%changelog
* Fri Aug 21 2026 stevapple <stevapple2013@gmail.com> - 3.3.0-1
- Initial packaging, pinned to the version haproxy-opentelemetry 2.2.0 requires
