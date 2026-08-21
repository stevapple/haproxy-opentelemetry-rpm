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

So `haproxy-otel` is built on **HAProxy 3.4.3** — the lowest series that works,
and the version RHEL 11 ships, so it is a release with a distribution track
record rather than an arbitrary tarball. Everything else is kept faithful to
Rocky 10: the same `USE_*` feature flags as the distro package, the same paths,
unit file, sysusers, tmpfiles, logrotate and sysconfig.

The version is one knob (`HAPROXY_VERSION` in `versions.env`). The spec checks
the two real requirements in `%prep` rather than comparing version strings, so
**when Rocky rebases haproxy to 3.4+, matching it exactly is a one-line
change** — and setting it back to 3.0.5 fails the build loudly instead of
quietly shipping a haproxy with no filter in it.

## What gets built

Three packages, in dependency order:

| Package | Version | Contents |
|---|---|---|
| `opentelemetry-cpp-haproxy` | 1.28.0 | OpenTelemetry C++ SDK, patched, ABI v2, private prefix |
| `opentelemetry-c-wrapper` | 3.3.0 | HAProxy's C API over that SDK |
| `haproxy-otel` | 3.4.3 | HAProxy with the OTel filter 2.2.0 compiled in |

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

What has been checked directly, and what has not:

**Verified by running it**

* **A complete HAProxy 3.4 build with the filter integrated through
  `EXTRA_MAKE` links successfully** — the whole mechanism this packaging rests
  on, exercised end to end.
* The resulting binary reports the filter, and all three of the spec's
  `%check` assertions match its real output:

  ```
  Built with OpenTelemetry support (filter version 2.2.0, C++ version none, C Wrapper version 3.3.0-0).
  Available filters :
  	[OTEL] opentelemetry
  ```

  (`C++ version none` because that build deliberately used upstream's `dummy/`
  stand-in — which is exactly the case the `%check` guard is written to reject,
  so the guard is confirmed to fire.)
* **The shipped example instrumentation config parses**
  (`haproxy -c` exit 0), with a negative control confirming the filter's parser
  really reads it: injecting a bogus keyword produces
  `'this-keyword-does-not-exist' : unknown keyword` and exit 1.
* The HAProxy compile matrix above — all 13 filter sources against four HAProxy
  releases, real compiler runs.
* All six opentelemetry-cpp patches apply cleanly to a pristine `v1.28.0` tree
  with `patch -p1`.
* All 17 pinned upstream tags exist.
* Rocky/RHEL 10 ships haproxy 3.0.5 — from the CentOS Stream 10 `c10s` spec and
  its changelog (release 8, August 2026, CVE backports only).
* Every spec parses under `rpmspec` with `dist=.el10`; all shell scripts pass
  `bash -n`; both CI files parse as YAML.

**Not verified here.** The environment had no access to Red Hat or Rocky package
repositories or container registries, so no `rpmbuild` was run and the
OpenTelemetry C++ SDK was not compiled. Specifically still unproven:

* the SDK build itself (CMake options, the offline vendored-tree layout) and
  the wrapper build against it;
* the generated RPM dependency graph, including whether the provides/requires
  filters for the private sonames are drawn tightly enough;
* `scripts/smoke-test.sh` against installed RPMs.

These need a first CI run on a host with normal network access. The HAProxy
half of the chain — the part specific to this filter, and the part the whole
version question turns on — is the half that has been proven.

[filter]: https://github.com/haproxytech/haproxy-opentelemetry
