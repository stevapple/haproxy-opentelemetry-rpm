#
# haproxy-otel -- HAProxy with the HAProxy OpenTelemetry filter compiled in.
#
# FORKED FROM FEDORA
# ------------------
# This is a fork of the Fedora haproxy package, kept as close to it as possible
# so that it inherits Fedora's build flags, file layout, scriptlets and future
# fixes with a minimal, reviewable diff.
#
#   upstream: https://src.fedoraproject.org/rpms/haproxy
#   branch:   rawhide
#   commit:   11852b3685f34562a7302bfa46baa4df66c29967 ("Upgrade to 3.4.3")
#
# The entire delta against that spec is marked with "OTel delta:" comments.
# When rebasing onto a newer Fedora haproxy, re-apply only those hunks.
#
# WHY THIS REBUILDS HAPROXY
# -------------------------
# The OTel filter is not a loadable module.  HAProxy has no runtime plugin
# interface, and haproxy-opentelemetry is an "addon": its Makefile.mk appends
# its objects to HAProxy's own OPTIONS_OBJS and is pulled in through HAProxy's
# EXTRA_MAKE hook.  The filter therefore only exists as part of the haproxy
# binary, and shipping it means shipping a haproxy build.
#
# WHY THE VERSION DOES NOT MATCH ROCKY 10
# ---------------------------------------
# Rocky/RHEL 10.x ships haproxy 3.0.5 and has not rebased it since 10.0.  The
# filter cannot be built against it:
#
#   * src/parser.c references ARGC_OTEL, which HAProxy only added in 3.4
#     (include/haproxy/arg-t.h); 3.0, 3.2 and 3.3 all fail to compile.
#   * The EXTRA_MAKE hook the addon plugs into landed in HAProxy 3.4.0 as well;
#     3.0-3.3 have no way to include an out-of-tree Makefile.mk.
#
# Tracking Fedora also settles the version question on its own: Fedora is at
# 3.4.3, which is both the lowest series that can host the filter and what
# RHEL 11 ships.  The %%prep guard below fails the build loudly rather than
# silently producing a haproxy without the filter.
#

%global _hardened_build 1

# OTel delta: the private OTel stack, and the addon version compiled in.
%global otel_prefix          /opt/haproxy-otel
%global otel_libdir          %{otel_prefix}/%{_lib}
%global otel_filter_version  2.2.0
%global otel_wrapper_version 3.3.0

# OTel delta: the haproxy binary carries a RUNPATH into the private OTel
# prefix.  That is deliberate -- the OTel stack is intentionally not on the
# dynamic linker's search path so it cannot shadow a system opentelemetry-cpp
# -- so the generic rpath check must not veto it.
%global __brp_check_rpaths %{nil}

# OTel delta: do not turn the private sonames into unresolvable dependencies.
%global __requires_exclude ^lib(opentelemetry|ryml|c4core|protobuf|grpc|gpr|absl|upb|utf8_|address_sorting|re2|cares)

Summary:        Reliable, high-performance TCP/HTTP load-balancing reverse proxy
Name:           haproxy-otel
Version:        3.4.3
Release:        1%{?dist}
License:        GPL-2.0-or-later AND LGPL-2.1-or-later
URL:            https://www.haproxy.org/
Source0:        https://www.haproxy.org/download/%(b=%{version}; echo ${b%.*})/src/haproxy-%{version}.tar.gz
Source1:        haproxy.service
Source2:        haproxy.cfg
Source3:        haproxy.logrotate
Source4:        haproxy.sysconfig
Source5:        haproxy.sysusersd
Source6:        https://salsa.debian.org/haproxy-team/haproxy/-/raw/c30a7411203b8c4234698e47325d2543359f9d66/debian/halog.1
# OTel delta: the addon source tree and its reference configuration.
Source10:       https://github.com/haproxytech/haproxy-opentelemetry/archive/refs/tags/v%{otel_filter_version}.tar.gz#/haproxy-opentelemetry-%{otel_filter_version}.tar.gz
Source11:       haproxy-otel.cfg.example
Source12:       otel.yml.example
Source13:       README.rpm.md
BuildRequires:  %{__cc}
BuildRequires:  libxcrypt-devel
BuildRequires:  lua-devel
BuildRequires:  make
BuildRequires:  openssl-devel >= 3.5.2
BuildRequires:  pcre2-devel
BuildRequires:  systemd-devel
BuildRequires:  systemd-rpm-macros
# OTel delta: the addon links the wrapper and finds it through pkg-config.
BuildRequires:  pkgconfig
BuildRequires:  opentelemetry-c-wrapper-devel = %{otel_wrapper_version}
Requires(pre):  shadow-utils
Recommends:     logrotate
# OTel delta: the private OTel stack is a hard runtime dependency.
Requires:       opentelemetry-c-wrapper%{?_isa} = %{otel_wrapper_version}
%{?systemd_requires}
%{?sysusers_requires_compat}

# OTel delta: drop-in replacement for the distribution package.  Anything that
# depends on "haproxy" is satisfied by this build; the two cannot be installed
# together because they own the same paths.
Provides:       haproxy = %{version}-%{release}
Provides:       haproxy%{?_isa} = %{version}-%{release}
Conflicts:      haproxy
# The filter has no separate artefact -- it is inside the binary -- but the
# version is worth advertising so it can be depended on and queried.
Provides:       haproxy-opentelemetry = %{otel_filter_version}

%description
HAProxy is a TCP/HTTP reverse proxy which is particularly suited for high
availability environments. Indeed, it can:
 - route HTTP requests depending on statically assigned cookies
 - spread load among several servers while assuring server persistence
   through the use of HTTP cookies
 - switch to backup servers in the event a main one fails
 - accept connections to special ports dedicated to service monitoring
 - stop accepting connections without breaking existing ones
 - add, modify, and delete HTTP headers in both directions
 - block requests matching particular patterns
 - report detailed status to authenticated users from a URI intercepted
   from the application

This build additionally contains the HAProxy OpenTelemetry filter
(version %{otel_filter_version}), which emits traces, metrics and logs to any
OpenTelemetry-compatible backend over OTLP. The filter is compiled into the
haproxy binary because HAProxy has no runtime module interface; enabling it is
a matter of adding a "filter opentelemetry" line to a proxy section.

Confirm the filter is present with:

    haproxy -vv | grep -i opentelemetry

This package replaces the haproxy package shipped with the distribution. See
%{_docdir}/%{name}/README.rpm.md for the details.

%prep
# OTel delta: -a 10 unpacks the addon inside the HAProxy tree, where the
# EXTRA_MAKE hook expects to find it.
%autosetup -p1 -n haproxy-%{version} -a 10
mv haproxy-opentelemetry-%{otel_filter_version} haproxy-opentelemetry

# OTel delta: fail loudly rather than quietly building a haproxy with no filter
# in it.  These are the actual compile-time requirements rather than a version
# string comparison, so they keep working if the version scheme ever changes.
if ! grep -q 'EXTRA_MAKE' Makefile; then
    echo "ERROR: HAProxy %{version} has no EXTRA_MAKE hook (needs >= 3.4)." >&2
    exit 1
fi
if ! grep -q 'ARGC_OTEL' include/haproxy/arg-t.h; then
    echo "ERROR: HAProxy %{version} lacks ARGC_OTEL; the OTel filter needs >= 3.4." >&2
    exit 1
fi

cp -p %{SOURCE11} haproxy-otel.cfg.example
cp -p %{SOURCE12} otel.yml.example
cp -p %{SOURCE13} README.rpm.md

%build
# OTel delta: the addon resolves the wrapper purely through pkg-config, which
# also supplies the RUNPATH into the private prefix (see the wrapper's .pc).
export PKG_CONFIG_PATH=%{otel_libdir}/pkgconfig

%make_build \
  TARGET="linux-glibc" \
  EXTRAVERSION="-%{release}" \
  EXTRA_MAKE="haproxy-opentelemetry" \
  USE_PCRE2=1 \
  USE_OPENSSL=1 \
  USE_QUIC=1 \
  USE_LUA=1 \
  USE_PROMEX=1 \
  CC=%{__cc} \
  CFLAGS="%{build_cflags}" \
  LDFLAGS="%{build_ldflags}" \
  OPT_CFLAGS="" ARCH_FLAGS="" \
  EXTRA="admin/halog/halog admin/iprange/iprange admin/iprange/ip6range"

%install
# OTel delta: the addon's Makefile.mk is re-included here too, so the same
# PKG_CONFIG_PATH and EXTRA_MAKE are needed or make aborts on a missing wrapper.
export PKG_CONFIG_PATH=%{otel_libdir}/pkgconfig

make install-{bin,man} DESTDIR=%{buildroot} PREFIX=%{_prefix} SBINDIR=%{_sbindir} \
  EXTRA_MAKE="haproxy-opentelemetry" \
  EXTRA="admin/halog/halog admin/iprange/iprange admin/iprange/ip6range"

install -D -p -m 0644 %{SOURCE1} %{buildroot}%{_unitdir}/haproxy.service
install -D -p -m 0644 %{SOURCE2} %{buildroot}%{_sysconfdir}/haproxy/haproxy.cfg
install -D -p -m 0644 %{SOURCE3} %{buildroot}%{_sysconfdir}/logrotate.d/haproxy
install -D -p -m 0644 %{SOURCE4} %{buildroot}%{_sysconfdir}/sysconfig/haproxy
install -D -p -m 0644 %{SOURCE5} %{buildroot}%{_sysusersdir}/haproxy.conf
install -p -D -m 0644 %{SOURCE6} %{buildroot}%{_mandir}/man1/halog.1
mkdir -p %{buildroot}{%{_sysconfdir}/haproxy/conf.d,%{_localstatedir}/lib/haproxy}/

# OTel delta: reference OTel configuration.  Not wired up by default -- the
# filter is inert until a proxy section names it -- so shipping these cannot
# change behaviour.
install -D -p -m 0644 haproxy-otel.cfg.example %{buildroot}%{_sysconfdir}/haproxy/otel.cfg.example
install -D -p -m 0644 otel.yml.example         %{buildroot}%{_sysconfdir}/haproxy/otel.yml.example

# Convert from ISO-8859-1 to UTF-8
iconv -f ISO-8859-1 -t UTF-8 -o doc/internals/connection-scale.txt{.utf8,}
touch -c -r doc/internals/connection-scale.txt{,.utf8}
mv -f doc/internals/connection-scale.txt{.utf8,}

# Prepare doc/ and examples/ for %%doc inclusion
mv -f doc/{gpl,lgpl}.txt .
rm -f doc/{gpl,lgpl}.txt doc/haproxy.1 examples/haproxy.init

%check
# OTel delta: the point of the whole package -- prove the filter really is in
# the binary.  Without this an upstream change to the addon's Makefile.mk could
# silently produce a plain haproxy that still passes every other check.
LD_LIBRARY_PATH=%{otel_libdir} %{buildroot}%{_sbindir}/haproxy -vv > haproxy-vv.txt 2>&1
cat haproxy-vv.txt
grep -qi 'Built with OpenTelemetry support' haproxy-vv.txt
grep -q '\[OTEL\] opentelemetry' haproxy-vv.txt
# A build linked against the upstream dummy wrapper reports "C++ version none"
# and produces no telemetry; that must never ship.
if grep -qi 'C++ version none' haproxy-vv.txt; then
    echo "ERROR: haproxy was linked against the dummy OTel wrapper." >&2
    exit 1
fi

%pre
%sysusers_create_compat %{SOURCE5}

%post
%systemd_post haproxy.service

%preun
%systemd_preun haproxy.service

%postun
%systemd_postun_with_restart haproxy.service

%files
%license LICENSE gpl.txt lgpl.txt
%doc CHANGELOG README.md doc/* examples/
# OTel delta: addon documentation and the packaging rationale.
%doc README.rpm.md
%doc haproxy-opentelemetry/README.md
%doc haproxy-opentelemetry/README-configuration
%doc haproxy-opentelemetry/README-conf
%dir %{_sysconfdir}/haproxy/
%config(noreplace) %{_sysconfdir}/haproxy/haproxy.cfg
%dir %{_sysconfdir}/haproxy/conf.d/
%dir %{_sysconfdir}/logrotate.d/
%config(noreplace) %{_sysconfdir}/logrotate.d/haproxy
%config(noreplace) %{_sysconfdir}/sysconfig/haproxy
# OTel delta: examples, deliberately not %%config -- they are templates.
%{_sysconfdir}/haproxy/otel.cfg.example
%{_sysconfdir}/haproxy/otel.yml.example
%{_bindir}/halog
%{_bindir}/iprange
%{_bindir}/ip6range
%{_sbindir}/haproxy
%{_unitdir}/haproxy.service
%{_sysusersdir}/haproxy.conf
%{_mandir}/man1/halog.1*
%{_mandir}/man1/haproxy.1*
%dir %{_localstatedir}/lib/haproxy/

%changelog
* Fri Aug 21 2026 stevapple <stevapple2013@gmail.com> - 3.4.3-1
- Fork of Fedora haproxy 3.4.3-1 (rawhide, 11852b3) with the HAProxy
  OpenTelemetry filter 2.2.0 compiled in via EXTRA_MAKE
