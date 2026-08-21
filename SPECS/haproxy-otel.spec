#
# haproxy-otel -- HAProxy with the HAProxy OpenTelemetry filter compiled in.
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
# Upstream's README claims 3.2 onward, but the code disagrees -- see
# docs/versioning.md for the compile matrix this was measured from.
#
# %%{version} is consequently the lowest HAProxy series that can host the
# filter.  It is a single knob: when Rocky rebases haproxy to 3.4 or later,
# set it to the distribution's version and the package becomes an exact
# feature-for-feature replacement.  The %%prep guard below fails the build
# loudly rather than silently producing a haproxy without the filter.
#

%global _hardened_build 1

%global otel_prefix        /opt/haproxy-otel
%global otel_libdir        %{otel_prefix}/%{_lib}
%global otel_filter_version 2.2.0
%global otel_wrapper_version 3.3.0

# Lowest HAProxy the filter compiles against.  Checked in %%prep.
%global haproxy_min_version 3.4

%global haproxy_user    haproxy
%global haproxy_group   %{haproxy_user}
%global haproxy_homedir %{_localstatedir}/lib/haproxy
%global haproxy_confdir %{_sysconfdir}/haproxy
%global haproxy_datadir %{_datadir}/haproxy

# The haproxy binary carries a RUNPATH into the private OTel prefix.  That is
# deliberate -- the OTel stack is intentionally not on the dynamic linker's
# search path so it cannot shadow a system opentelemetry-cpp -- so the generic
# rpath check must not veto it.
%global __brp_check_rpaths %{nil}

# Same reasoning as the OTel packages: do not turn the private sonames into
# unresolvable dependencies.
%global __requires_exclude ^lib(opentelemetry|ryml|c4core|protobuf|grpc|gpr|absl|upb|utf8_|address_sorting|re2|cares)

Name:           haproxy-otel
Version:        3.4.3
Release:        1%{?dist}
Summary:        HAProxy reverse proxy with the OpenTelemetry filter built in

License:        GPL-2.0-or-later AND LGPL-2.1-or-later
URL:            https://www.haproxy.org
Source0:        %{url}/download/%(b=%{version}; echo ${b%.*})/src/haproxy-%{version}.tar.gz
Source1:        https://github.com/haproxytech/haproxy-opentelemetry/archive/refs/tags/v%{otel_filter_version}.tar.gz#/haproxy-opentelemetry-%{otel_filter_version}.tar.gz

# Distribution integration files, taken from the Rocky/RHEL 10 haproxy package
# so that this build drops into an existing deployment unchanged.
Source10:       haproxy.service
Source11:       haproxy.cfg
Source12:       haproxy.logrotate
Source13:       haproxy.sysconfig
Source14:       haproxy.sysusers
Source15:       haproxy-otel.cfg.example
Source16:       otel.yml.example
Source17:       README.rpm.md

BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  lua-devel
BuildRequires:  pcre2-devel
BuildRequires:  openssl-devel
BuildRequires:  systemd-devel
BuildRequires:  systemd-rpm-macros
BuildRequires:  libxcrypt-devel
BuildRequires:  zlib-devel
BuildRequires:  pkgconfig
BuildRequires:  opentelemetry-c-wrapper-devel = %{otel_wrapper_version}

Requires:       opentelemetry-c-wrapper%{?_isa} = %{otel_wrapper_version}
Requires(pre):  shadow-utils
Recommends:     logrotate
%{?systemd_requires}
%{?sysusers_requires_compat}

# Drop-in replacement for the distribution package.  Anything that depends on
# "haproxy" is satisfied by this build; the two cannot be installed together
# because they own the same paths.
Provides:       haproxy = %{version}-%{release}
Provides:       haproxy%{?_isa} = %{version}-%{release}
Conflicts:      haproxy

# The filter itself has no separate artifact -- it is inside the binary --
# but the version is worth advertising so it can be depended on and queried.
Provides:       haproxy-opentelemetry = %{otel_filter_version}

%description
HAProxy is a TCP/HTTP reverse proxy which is particularly suited for high
availability environments.

This build additionally contains the HAProxy OpenTelemetry filter
(version %{otel_filter_version}), which emits traces, metrics and logs to any
OpenTelemetry-compatible backend over OTLP.  The filter is compiled into the
haproxy binary because HAProxy has no runtime module interface; enabling it is
a matter of adding a "filter opentelemetry" line to a proxy section.

Confirm the filter is present with:

    haproxy -vv | grep -i opentelemetry

Note that this package replaces the haproxy package shipped with the
distribution and is built from a newer HAProxy release, because the filter
does not compile against the 3.0.x series the OS ships.  See
%{_docdir}/%{name}/README.rpm.md for the details.

%prep
# -a 1 unpacks the filter addon inside the HAProxy tree, where EXTRA_MAKE
# expects to find it.
%setup -q -a 1 -n haproxy-%{version}
mv haproxy-opentelemetry-%{otel_filter_version} haproxy-opentelemetry

# Fail loudly rather than quietly building a haproxy with no filter in it.
# Both of these are the actual compile-time requirements, not a version string
# comparison, so they keep working if the version scheme ever changes.
if ! grep -q 'EXTRA_MAKE' Makefile; then
    echo "ERROR: HAProxy %{version} has no EXTRA_MAKE hook (needs >= %{haproxy_min_version})." >&2
    exit 1
fi
if ! grep -q 'ARGC_OTEL' include/haproxy/arg-t.h; then
    echo "ERROR: HAProxy %{version} lacks ARGC_OTEL; the OTel filter needs >= %{haproxy_min_version}." >&2
    exit 1
fi

cp -p %{SOURCE17} README.rpm.md
cp -p %{SOURCE15} haproxy-otel.cfg.example
cp -p %{SOURCE16} otel.yml.example

%build
# The addon resolves the wrapper through pkg-config, which also supplies the
# RUNPATH into the private prefix (see opentelemetry-c-wrapper.pc).
export PKG_CONFIG_PATH=%{otel_libdir}/pkgconfig

# The USE_* set is kept identical to the Rocky/RHEL 10 haproxy package so that
# a swap does not silently change which features are available; EXTRA_MAKE is
# the only functional addition.
%make_build \
    CPU="generic" \
    TARGET="linux-glibc" \
    EXTRA_MAKE="haproxy-opentelemetry" \
    USE_OPENSSL=1 \
    USE_PCRE2=1 \
    USE_SLZ=1 \
    USE_LUA=1 \
    USE_CRYPT_H=1 \
    USE_SYSTEMD=1 \
    USE_LINUX_TPROXY=1 \
    USE_GETADDRINFO=1 \
    USE_PROMEX=1 \
    DEFINE=-DMAX_SESS_STKCTR=12 \
    ADDINC="%{build_cflags}" \
    ADDLIB="%{build_ldflags}"

%make_build admin/halog/halog ADDINC="%{build_cflags}" ADDLIB="%{build_ldflags}"
%make_build -C admin/iprange OPTIMIZE="%{build_cflags}" LDFLAGS="%{build_ldflags}"

%install
# The same PKG_CONFIG_PATH and EXTRA_MAKE as %%build: the addon's Makefile.mk is
# re-included here, and without them it would abort on a missing wrapper.
# Explicit install-bin/install-man targets (rather than %%make_install, which
# would also run the composite "install" target) match the distribution spec.
export PKG_CONFIG_PATH=%{otel_libdir}/pkgconfig

make install-bin DESTDIR=%{buildroot} PREFIX=%{_prefix} SBINDIR=%{_sbindir} \
    TARGET="linux-glibc" EXTRA_MAKE="haproxy-opentelemetry"
make install-man DESTDIR=%{buildroot} PREFIX=%{_prefix} \
    EXTRA_MAKE="haproxy-opentelemetry"

install -p -D -m 0644 %{SOURCE10} %{buildroot}%{_unitdir}/haproxy.service
install -p -D -m 0644 %{SOURCE11} %{buildroot}%{haproxy_confdir}/haproxy.cfg
install -p -D -m 0644 %{SOURCE12} %{buildroot}%{_sysconfdir}/logrotate.d/haproxy
install -p -D -m 0644 %{SOURCE13} %{buildroot}%{_sysconfdir}/sysconfig/haproxy
install -p -D -m 0644 %{SOURCE14} %{buildroot}%{_sysusersdir}/haproxy.conf

install -d -m 0755 %{buildroot}%{haproxy_homedir}
install -d -m 0755 %{buildroot}%{haproxy_datadir}
install -d -m 0755 %{buildroot}%{haproxy_confdir}/conf.d

install -d -m 0755 %{buildroot}%{_bindir}
install -p -m 0755 admin/halog/halog     %{buildroot}%{_bindir}/halog
install -p -m 0755 admin/iprange/iprange %{buildroot}%{_bindir}/iprange
install -p -m 0755 admin/iprange/ip6range %{buildroot}%{_bindir}/ip6range

for httpfile in $(find ./examples/errorfiles/ -type f); do
    install -p -m 0644 "$httpfile" %{buildroot}%{haproxy_datadir}
done
rm -rf ./examples/errorfiles/
find ./examples/* -type f ! -name "*.cfg" -exec rm -f "{}" \;

mkdir -p %{buildroot}%{_tmpfilesdir}
echo "d %{haproxy_homedir} 0755 root root - -" > %{buildroot}%{_tmpfilesdir}/haproxy.conf

# Reference OTel configuration, not wired up by default: the filter is inert
# until a proxy section names it, so shipping these cannot change behaviour.
install -p -D -m 0644 haproxy-otel.cfg.example %{buildroot}%{haproxy_confdir}/otel.cfg.example
install -p -D -m 0644 otel.yml.example         %{buildroot}%{haproxy_confdir}/otel.yml.example

%check
# The point of the whole package: prove the filter really is in the binary.
# Without this an upstream change to the addon's Makefile.mk could silently
# produce a plain haproxy that still passes every other check.
LD_LIBRARY_PATH=%{otel_libdir} %{buildroot}%{_sbindir}/haproxy -vv > haproxy-vv.txt 2>&1 || :
cat haproxy-vv.txt
grep -qi 'Built with OpenTelemetry support' haproxy-vv.txt
grep -q '\[OTEL\] opentelemetry' haproxy-vv.txt
# A dummy-wrapper build reports "C++ version none"; that must never ship.
if grep -qi 'C++ version none' haproxy-vv.txt; then
    echo "ERROR: haproxy was linked against the dummy OTel wrapper." >&2
    exit 1
fi

%pre
%sysusers_create_compat %{SOURCE14}

%post
%systemd_post haproxy.service

%preun
%systemd_preun haproxy.service

%postun
%systemd_postun_with_restart haproxy.service

%files
%license LICENSE
%doc CHANGELOG README VERSION README.rpm.md
%doc doc/* examples/*
%doc haproxy-opentelemetry/README.md
%doc haproxy-opentelemetry/README-configuration
%doc haproxy-opentelemetry/README-conf
%dir %{haproxy_homedir}
%dir %{haproxy_confdir}
%dir %{haproxy_confdir}/conf.d
%dir %{haproxy_datadir}
%{haproxy_datadir}/*
%config(noreplace) %{haproxy_confdir}/haproxy.cfg
%config(noreplace) %{_sysconfdir}/logrotate.d/haproxy
%config(noreplace) %{_sysconfdir}/sysconfig/haproxy
%{haproxy_confdir}/otel.cfg.example
%{haproxy_confdir}/otel.yml.example
%{_unitdir}/haproxy.service
%{_sbindir}/haproxy
%{_bindir}/halog
%{_bindir}/iprange
%{_bindir}/ip6range
%{_mandir}/man1/*
%{_sysusersdir}/haproxy.conf
%{_tmpfilesdir}/haproxy.conf

%changelog
* Fri Aug 21 2026 stevapple <stevapple2013@gmail.com> - 3.4.3-1
- Initial packaging of HAProxy with the OpenTelemetry filter 2.2.0
- Built on HAProxy 3.4.3: the filter needs ARGC_OTEL and EXTRA_MAKE, neither
  of which exists in the 3.0.5 the OS ships
- USE_* feature set kept identical to the distribution haproxy package
