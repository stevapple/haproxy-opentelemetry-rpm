# haproxy-otel

HAProxy with the [HAProxy OpenTelemetry filter][filter] compiled in.

## Why this replaces the distribution `haproxy`

HAProxy has no runtime module interface. `haproxy-opentelemetry` is an *addon*:
its `Makefile.mk` appends its object files to HAProxy's own `OPTIONS_OBJS` and
is pulled into the build through HAProxy's `EXTRA_MAKE` hook. The filter only
exists as part of the `haproxy` binary, so shipping the filter means shipping a
HAProxy build.

This package therefore `Provides: haproxy` and `Conflicts: haproxy`. Swap with:

```sh
dnf swap haproxy haproxy-otel
```

The `USE_*` feature set is identical to the distribution's haproxy package, so
nothing else about the proxy changes.

## Why the version is not the one Rocky 10 ships

Rocky/RHEL 10.x ships **haproxy 3.0.5** and has not rebased it since 10.0. The
filter cannot be built against it, for two independent reasons:

* `src/parser.c` references `ARGC_OTEL`, an enumerator HAProxy only added in
  **3.4** (`include/haproxy/arg-t.h`). HAProxy 3.0, 3.2 and 3.3 fail to compile.
* The `EXTRA_MAKE` hook the addon plugs into also landed in **3.4.0**. Earlier
  releases have no mechanism to include an out-of-tree `Makefile.mk` at all.

Upstream's README states "3.2 onward", but the code disagrees. This package is
consequently built on the lowest HAProxy series that can actually host the
filter. If Rocky rebases haproxy to 3.4 or later, the package version can be
set to match the distribution exactly.

## Getting started

1. Point the SDK at your collector:

   ```sh
   cp /etc/haproxy/otel.yml.example  /etc/haproxy/otel.yml
   cp /etc/haproxy/otel.cfg.example  /etc/haproxy/otel.cfg
   ```

   Edit `otel.yml` — set the OTLP endpoints and `service.name`.

2. Reference the filter from a proxy section in `/etc/haproxy/haproxy.cfg`:

   ```
   frontend my-frontend
       mode http
       bind *:80
       filter opentelemetry id otel config /etc/haproxy/otel.cfg
       default_backend my-backend
   ```

   The `id` must match the section name in `otel.cfg`.

3. Check the configuration and restart:

   ```sh
   haproxy -c -f /etc/haproxy/haproxy.cfg
   systemctl restart haproxy
   ```

## Verifying the filter is present

```sh
haproxy -vv | grep -i opentelemetry
```

A working build reports something like:

```
Built with OpenTelemetry support (filter version 2.2.0, C++ version 1.28.0, C Wrapper version 3.3.0-1006).
	[OTEL] opentelemetry
```

If it reports `C++ version none`, the binary was linked against the upstream
*dummy* wrapper and produces no telemetry. That is a build error; this package
fails its `%check` if it happens, so a released RPM should never show it.

## Runtime control

The filter registers CLI commands on the HAProxy admin socket — enable and
disable it, change the rate limit, switch error handling, flush pending
telemetry and inspect status — without restarting the proxy:

```sh
echo "otel status" | socat stdio /var/lib/haproxy/stats
```

## Delivery is best-effort

The OpenTelemetry specification does not mandate reliable delivery. Data may be
dropped through sampling, queue limits, network failures or backend
unavailability. Do not rely on this data where completeness matters, such as
billing or auditing.

## The private OpenTelemetry stack

The filter links `opentelemetry-c-wrapper`, which in turn links a build of the
OpenTelemetry C++ SDK that is **not** interchangeable with a system one: it
carries upstream's required patch set and uses ABI version 2. Both live under
`/opt/haproxy-otel` and are reached through RUNPATH, precisely so they cannot
shadow or be shadowed by a distribution `opentelemetry-cpp`.

[filter]: https://github.com/haproxytech/haproxy-opentelemetry
