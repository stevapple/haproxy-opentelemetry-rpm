# haproxy-opentelemetry-rpm

RPM packaging of the [HAProxy OpenTelemetry filter][filter] for
Rocky Linux / RHEL 10 (`el10`), built on UBI 10.

## Read this first: the filter is not a module

HAProxy has no runtime plugin interface. `haproxy-opentelemetry` is an
*addon* — its `Makefile.mk` appends object files to HAProxy's own
`OPTIONS_OBJS` and is pulled in through HAProxy's `EXTRA_MAKE` hook. **The
filter only exists as part of the `haproxy` binary.** Packaging it therefore
means packaging a HAProxy build, which is what `haproxy-otel` is: a drop-in
replacement for the distribution's `haproxy` package, same feature set, plus
the filter.

## Read this second: the version cannot match Rocky 10

The brief was to match the HAProxy version in the OS repository. **That is not
achievable, and the reason is in the filter's source, not in this packaging.**

Rocky/RHEL 10.x ships **haproxy 3.0.5** and has not rebased it since 10.0. The
filter needs **3.4** or newer:

* `src/parser.c` uses `ARGC_OTEL`, an enumerator HAProxy added in 3.4.
  On 3.0/3.2/3.3 the build fails outright.
* The `EXTRA_MAKE` hook the addon plugs into also landed in 3.4.0. Earlier
  releases cannot include an out-of-tree `Makefile.mk` at all.

Measured by compiling the filter's 13 sources against each release's headers:

| HAProxy | 3.0 (Rocky 10) | 3.2 | 3.3 | 3.4 |
|---|---|---|---|---|
| filter sources compiling | 11/13 | 12/13 | 12/13 | **13/13** |

(Upstream's README says "3.2 onward"; the code disagrees. Full evidence and
method: [`docs/versioning.md`](docs/versioning.md).)

So `haproxy-otel` is built on **HAProxy 3.4.3**, and rather than hand-rolling
that, the spec is a **fork of the Fedora `haproxy` package** — which is already
at exactly 3.4.3-1, and is also what RHEL 11 ships. Forking means the package
inherits Fedora's build flags, file layout, scriptlets and future fixes; the
entire delta is marked with `OTel delta:` comments, so rebasing onto a newer
Fedora haproxy is a matter of re-applying those hunks.

    upstream: https://src.fedoraproject.org/rpms/haproxy (rawhide, 11852b3)

That also corrected two stale build flags an earlier hand-written version of
this spec carried over from the RHEL 10 package: `USE_SLZ=1` (default-on since
3.4) and `USE_SYSTEMD=1` (gone — HAProxy has implemented `sd_notify` natively
since 3.1).

The version is one knob (`HAPROXY_VERSION` in `versions.env`). The spec checks
the two real requirements in `%prep` rather than comparing version strings, so
**when Rocky rebases haproxy to 3.4+, matching it exactly is a one-line
change** — and setting it back to 3.0.5 fails the build loudly instead of
quietly shipping a haproxy with no filter in it.

## What gets built

Three packages, in dependency order:

| Package | Version | Forked from | Contents |
|---|---|---|---|
| `opentelemetry-cpp-haproxy` | 1.28.0 | — (Fedora has no such package) | OpenTelemetry C++ SDK, patched, ABI v2, private prefix |
| `opentelemetry-c-wrapper` | 3.3.0 | — | HAProxy's C API over that SDK |
| `haproxy-otel` | 3.4.3 | Fedora `haproxy` (rawhide) | HAProxy with the OTel filter 2.2.0 compiled in |

Fedora packages neither `opentelemetry-cpp` nor the HAProxy C wrapper (checked
against the Fedora package index), so those two specs have no upstream to fork;
they follow Fedora conventions instead — `%cmake`/`%cmake_build`/`%cmake_install`,
`%autosetup`, `%bcond`, and `Provides: bundled(...)` for every vendored tree.

The SDK and wrapper install under `/opt/haproxy-otel` and are reached through
RUNPATH. That is deliberate: this SDK build carries upstream's mandatory patch
set and uses **ABI version 2**, so it is not interchangeable with a system
`opentelemetry-cpp` and must not be able to shadow one, or be shadowed by one.

`haproxy-otel` `Provides: haproxy` and `Conflicts: haproxy`:

```sh
dnf swap haproxy haproxy-otel
```

## Building

```sh
make image                       # UBI 10 builder container
make shell                       # drop into it, then:
  ./scripts/vendor-otelcpp.sh    # assemble pinned opentelemetry-cpp tree
  ./scripts/fetch-sources.sh     # upstream release tarballs
  ./scripts/build-all.sh all     # build + install the three packages
  ./scripts/smoke-test.sh        # verify the filter is really in the binary
```

Or in one step on a prepared host: `make rpms`.

Two things worth knowing before you start:

* **`scripts/vendor-otelcpp.sh` needs network and takes a while.**
  opentelemetry-cpp resolves its dependencies through CMake `FetchContent`,
  which downloads at configure time — impossible inside an RPM build. gRPC and
  rapidyaml also carry git submodules that GitHub's release tarballs omit. The
  script is a transcription of upstream's own `opentelemetry-cpp-monorepo.sh`
  and produces one tarball the spec can consume offline. CI caches it on the
  hash of `versions.env`.
* **The SDK build is the long pole.** gRPC + protobuf + Abseil dominate it.
  Pass `RPM_WITH="--without grpc"` to drop the OTLP/gRPC exporter and those
  three trees with it; OTLP/HTTP and OTLP/file keep working.

## CI

Both pipelines drive the same `scripts/`, so they cannot diverge in what they
actually build:

* **GitHub Actions** — [`.github/workflows/build.yml`](.github/workflows/build.yml):
  lint → build in UBI 10 → smoke test → artifacts, and attaches RPMs to
  releases on `v*` tags.
* **Woodpecker** — [`.woodpecker/build.yaml`](.woodpecker/build.yaml): same
  stages, with the vendored tree in a cache volume.

Both use `registry.access.redhat.com/ubi10/ubi` as the base and run
`scripts/setup-buildenv.sh`, which layers Rocky 10 AppStream/CRB and EPEL for
the handful of `-devel` packages UBI's own repositories do not carry
(`lua-devel`, `autoconf-archive`, …). Rocky 10 is an ABI-identical RHEL 10
rebuild, so this resolves to the same binaries a RHEL build would use — and to
what the resulting RPMs will actually run against.

## Using the filter

Nothing is enabled by default; the filter is inert until a proxy section names
it. Reference configuration is installed as
`/etc/haproxy/otel.cfg.example` (what to instrument) and
`/etc/haproxy/otel.yml.example` (exporters, samplers, resources).

```
frontend my-frontend
    mode http
    bind *:80
    filter opentelemetry id otel config /etc/haproxy/otel.cfg
    default_backend my-backend
```

Confirm the filter is present:

```sh
haproxy -vv | grep -i opentelemetry
# Built with OpenTelemetry support (filter version 2.2.0, C++ version 1.28.0, ...)
#	[OTEL] opentelemetry
```

`C++ version none` means the binary was linked against upstream's `dummy/`
stand-in and emits no telemetry. Both the spec's `%check` and
`scripts/smoke-test.sh` reject that, so a released RPM cannot show it.

## Repository layout

```
versions.env                  every pin, single source of truth
SPECS/                        the three spec files
SOURCES/                      patches, distro integration files, example configs
scripts/
  setup-buildenv.sh           UBI 10 -> build host (shared by Containerfile + CI)
  vendor-otelcpp.sh           assemble the pinned, offline opentelemetry-cpp tree
  fetch-sources.sh            download upstream release tarballs
  build-all.sh                build the chain in order
  smoke-test.sh               post-install verification
docs/versioning.md            pin provenance and the HAProxy compile matrix
Containerfile                 UBI 10 builder image
```

## Verification status

**The whole chain has been built and tested** in a UBI 10 container:
`opentelemetry-cpp-haproxy` → `opentelemetry-c-wrapper` → `haproxy-otel`, from
the vendored sources, offline, producing installable RPMs.

The installed binary reports the real SDK, not the dummy stand-in:

```
HAProxy version 3.4.3-80ea565fd-1.el10 2026/07/29
Built with OpenTelemetry support (filter version 2.2.0, C++ version 1.28.0, C Wrapper version 3.3.0-1006).
	[OTEL] opentelemetry
```

`scripts/smoke-test.sh` passes against the installed packages — all five checks,
including that 118 shared libraries resolve through RUNPATH with no
`LD_LIBRARY_PATH`, and that the shipped example configuration parses.

The dependency graph came out clean: `haproxy-otel` requires only system
libraries plus `opentelemetry-c-wrapper(x86-64) = 3.3.0`, provides
`haproxy = 3.4.3-1.el10`, conflicts with `haproxy`, and no private soname
leaks into anything's `Requires`.

Building it is what found the bugs. None was visible to `rpmspec`:

| Found | Fix |
|---|---|
| protobuf 35.1 declares Abseil as `absl`, so it looks for `absl-src`; upstream's monorepo script checks it out as `abseil-cpp-src` | map every vendored dependency with an explicit `FETCHCONTENT_SOURCE_DIR_*` |
| `check-rpaths` rejected every library in the private prefix | clear `__brp_check_rpaths` in all three specs, not just one |
| protoc and the upb generators installed into the prefix, unpackaged | removed in `%install` |
| wrapper 3.3.0 does not compile against the monorepo's rapidyaml 0.15.2 | pin ryml to **0.10.0**, the only version satisfying both sides |
| `find_package` resolved nlohmann-json against a *previous build of this package*, so the header was never shipped | add it to the `CMAKE_DISABLE_FIND_PACKAGE_*` list |
| Fedora's `%files` finds halog/iprange in `%{_bindir}` only because Fedora merged `/usr/sbin` into `/usr/bin`; el10 has not | move them explicitly (`el10 delta:` in the spec) |

**Caveat — the gRPC build.** What is verified above is `--without grpc`
(OTLP/HTTP and OTLP/file). The spec still *defaults* to gRPC on, matching
upstream, and that variant adds the vendored gRPC tree; see the build notes
above for why it is much slower. If you need OTLP/gRPC, expect a long first
build.

Also still unverified: `aarch64` (only `x86_64` was built), and the CI
pipelines themselves have not run — they drive the same `scripts/` that were
used here, but on a runner rather than in this container.
