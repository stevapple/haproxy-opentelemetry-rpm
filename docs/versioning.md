# Version pins and where they come from

Every version in `versions.env` is transcribed from an upstream source of
truth. This file records which, and the evidence behind the two pins that are
*not* simply "the latest release".

## The chain

```
haproxy-otel  ──requires──▶  haproxy-opentelemetry 2.2.0   (filter, compiled into haproxy)
                                      │
                                      └──requires──▶  opentelemetry-c-wrapper 3.3.0
                                                              │
                                                              └──requires──▶  opentelemetry-cpp 1.28.0
                                                                              + 6 patches, ABI v2
```

Nothing in this chain is independently upgradable:

| Component | Pin | Source of truth |
|---|---|---|
| HAProxy OTel filter | `2.2.0` | latest tag of `haproxytech/haproxy-opentelemetry` |
| OpenTelemetry C wrapper | `3.3.0` | filter `README.md`, "Dependencies" — names 3.3.0 explicitly |
| OpenTelemetry C++ SDK | `1.28.0` | wrapper `scripts/build/opentelemetry-cpp-1.28.0-install.sh` |
| HAProxy | `3.4.3` | lowest series that compiles — see below |

### Why opentelemetry-cpp cannot float

The wrapper ships six patches named `*-opentelemetry-cpp-1.28.0.patch`. They
are not cosmetic: they add `MaybeSpawnBackgroundThread()` and
`SetBackgroundWaitFor()` to the OTLP exporters, which the wrapper calls. The
wrapper's own README says it plainly:

> The version of the OTel C++ SDK used is set to 1.28.0 because the
> `*-opentelemetry-cpp-1.28.0.patch` set in `scripts/build/` is prepared for
> exactly that SDK release. […] Another SDK release cannot be used without
> porting the patch set.

The SDK must additionally be built with `-DWITH_ABI_VERSION_2=ON`; the wrapper
verifies this at configure time and refuses an ABI v1 build.

All six patches were verified to apply cleanly with `patch -p1` against a
pristine `v1.28.0` tree.

> **Note on the filter README.** It says the wrapper "wraps the OpenTelemetry
> C++ SDK version 1.26.0 or newer", and its sample `-vv` output shows
> `C++ version 1.26.0`. That is the wrapper's *minimum* (`pkg-config
> --atleast-version=1.26.0`), not what wrapper 3.3.0 is built against. The
> build scripts pin 1.28.0, and that is what this packaging uses.

### Vendored third-party pins

Taken verbatim from the wrapper's
`scripts/build/opentelemetry-cpp-monorepo.sh`, which is upstream's own recipe
for an offline build:

| Dependency | Tag |
|---|---|
| abseil-cpp | `20250512.1` |
| protobuf | `v35.1` |
| grpc | `v1.82.1` (with submodules) |
| rapidyaml | `v0.10.0` (with recursive submodules) — **not** the monorepo's `v0.15.2`, see below |
| curl | `curl-8_21_0` |
| zlib | `v1.3.2` |
| nlohmann/json | `v3.12.0` |
| opentelemetry-proto | `v1.10.0` |
| ms-gsl | `v4.2.1` |
| prometheus-cpp | `v1.3.0` |
| opentracing-cpp | `v1.6.0` |
| googletest | `v1.17.0` |
| benchmark | `v1.9.4` |

All 13, plus the four primary components, were confirmed to exist upstream,
and the whole chain has since been built from them.

> The wrapper also carries per-library `*-install.sh` scripts with *older*
> pins (abseil `20250127.1`, protobuf `29.5`, grpc `1.70.2`, ryml `0.10.0`,
> curl `8_19_0`). Those belong to the piecemeal `build.sh` path. The monorepo
> pins are otherwise the ones that matter here, because they are the set
> prepared for an offline build — which is what an RPM build must be.
>
> **Except for rapidyaml.** The two disagree and the monorepo one does not
> build: see below.

### rapidyaml must be 0.10.0, not the monorepo's 0.15.2

Building the wrapper against the monorepo's `v0.15.2` fails:

```
yaml.cpp:324:27: error: 'struct c4::yml::Callbacks' has no member named 'm_error'
```

rapidyaml 0.11 split `Callbacks`' single `m_error` into `m_error_basic`,
`m_error_parse` and `m_error_visit`, with different signatures.
opentelemetry-c-wrapper 3.3.0's `src/yaml.cpp` is written against the pre-0.11
API, which is exactly what its own `rapidyaml-0.10.0-src-install.sh` pins.

opentelemetry-cpp 1.28.0 supports both APIs behind `RYML_VERSION_MINOR` guards
(`sdk/src/configuration/ryml_document.cc`), so **0.10.0 is the only version
that satisfies both sides**, and it is what this packaging vendors.

opentelemetry-cpp names its own ryml tag in `third_party_release`, parsed by
`CMakeLists.txt` with an unconditional `set()` that `-D` cannot override, so
`%prep` rewrites that one line to match what is actually vendored.

### Every vendored dependency must be in the find_package disable list

`CMAKE_DISABLE_FIND_PACKAGE_<name>=ON` is not optional hygiene here. CMake
searches `CMAKE_INSTALL_PREFIX`, so with `nlohmann_json` missing from the list,
`find_package()` resolved it against the copy a *previous build of this very
package* had installed into `/opt/haproxy-otel`. The vendored source was then
never built or installed, and the `-devel` package shipped SDK headers (Zipkin,
Elasticsearch) that `#include <nlohmann/json.hpp>` without shipping that header.

The configure output names the provider for each dependency, and is the quick
way to check:

```
-- nlohmann-json: 3.12.0 (find_package)      <- wrong, hijacked
-- nlohmann-json: 3.12.0 (fetch_repository)  <- right, vendored
```

## The HAProxy version conflict

**Rocky/RHEL 10.x ships haproxy 3.0.5 and the filter cannot be built against
it.**

CentOS Stream 10 (`c10s`, the branch RHEL 10.x and therefore Rocky 10.x are cut
from) has carried `Version: 3.0.5` since RHEL 10.0, with only CVE backports
since — release 8 as of August 2026, most recently for CVE-2026-55203 and
CVE-2026-55204. There has been no rebase. (For contrast, `c11s` already carries
3.4.3.)

### Evidence

Compiling all 13 of the filter's `src/*.c` against each HAProxy release's
headers:

| HAProxy | `ARGC_OTEL` | `STRM_EVT_MSG` | `EXTRA_MAKE` | Filter sources compile |
|---|---|---|---|---|
| 3.0 *(Rocky 10)* | no | no | no | **2 of 13 fail** |
| 3.2 | no | yes | no | **1 of 13 fails** |
| 3.3 | no | yes | no | fails (same as 3.2) |
| 3.4 | yes | yes | yes | **13 of 13 compile** |

Two independent blockers, either one fatal:

1. **`ARGC_OTEL`.** `src/parser.c:408` uses it. HAProxy added the enumerator to
   `include/haproxy/arg-t.h` in 3.4 (`ARGC_OTEL, /* opentelemetry scope args */`).
   On 3.0–3.3 the compiler suggests `ARGC_OT` — the old OpenTracing one.
2. **`EXTRA_MAKE`.** The addon is integrated by HAProxy's top-level Makefile
   doing `include $(addsuffix /Makefile.mk,$(EXTRA_MAKE))`. That hook first
   appears in **3.4.0**; `grep EXTRA_MAKE Makefile` returns nothing in 3.0,
   3.2 or 3.3. There is no supported way to plug an out-of-tree addon into
   those releases.

On 3.0 there is a third: `src/filter.c:1867` uses `STRM_EVT_MSG`, which arrived
in 3.2.

So the filter's own README — "It supports all HAProxy versions from 3.2 onward"
— is optimistic by two minor releases. The real floor is **3.4**.

### What this packaging does about it

`SPECS/haproxy-otel.spec` pins `Version: 3.4.3`, the lowest series that works
and also the version RHEL 11 ships, so it is a HAProxy release with a
distribution track record rather than an arbitrary upstream tarball.

The version is a single knob. The spec does **not** compare version strings; it
checks the two actual requirements in `%prep`:

```sh
grep -q 'EXTRA_MAKE' Makefile
grep -q 'ARGC_OTEL' include/haproxy/arg-t.h
```

Either one missing fails the build with an explicit message. That means:

* setting `%{version}` back to 3.0.5 fails loudly instead of quietly shipping a
  haproxy with no filter in it, and
* when Rocky rebases haproxy to 3.4 or later, changing `HAPROXY_VERSION` in
  `versions.env` and the spec is the whole migration.

`%check` closes the other half of the loop: it runs `haproxy -vv` on the built
binary and fails unless it reports `Built with OpenTelemetry support` and a real
C++ version — a build that accidentally linked the upstream `dummy/` stand-in
reports `C++ version none` and is rejected.

## Keeping the pins current

Re-check in this order; each step constrains the next.

1. New filter release → read its README "Dependencies" for the required wrapper
   version, and re-run the compile matrix for the HAProxy floor.
2. New wrapper release → read `scripts/build/opentelemetry-cpp-*-install.sh`
   for the SDK version, and take the patch set filenames as authoritative.
3. New SDK version → the patches must be re-based; the wrapper's own
   `opentelemetry-cpp-monorepo.sh` gives the matching third-party pins.

Do not bump `OTELCPP_VERSION` on its own. The patch filenames in `SOURCES/`
encode the SDK version they target, and the spec applies them unconditionally.
