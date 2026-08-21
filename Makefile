# Convenience wrapper around scripts/.  Everything here is a thin front end --
# CI calls the same scripts directly.

SHELL   := /bin/bash
TOPDIR  ?= $(CURDIR)/rpmbuild
SPECS   := $(wildcard SPECS/*.spec)

include versions.env
export

.PHONY: all help lint sources vendor rpms clean distclean image shell smoke

help:
	@echo "Targets:"
	@echo "  lint       parse every spec and report unexpanded macros"
	@echo "  vendor     assemble the pinned opentelemetry-cpp source tree"
	@echo "  sources    download upstream release tarballs into SOURCES/"
	@echo "  rpms       build all three packages (needs a prepared build host)"
	@echo "  smoke      verify an installed haproxy-otel carries the filter"
	@echo "  image      build the UBI-based builder container"
	@echo "  shell      drop into the builder container"
	@echo "  clean      remove build trees, keep downloaded sources"
	@echo "  distclean  also remove downloaded and vendored sources"
	@echo
	@echo "Pinned: haproxy $(HAPROXY_VERSION), filter $(OTEL_FILTER_VERSION),"
	@echo "        wrapper $(OTEL_WRAPPER_VERSION), otel-cpp $(OTELCPP_VERSION)"

all: rpms

# Parse each spec with the target dist macro set.  Catches syntax errors,
# unbalanced conditionals and typos in macro names without needing sources.
#
# Macros supplied by redhat-rpm-config and systemd-rpm-macros stay unexpanded
# when this runs off-target (on a plain Fedora/Debian rpm, or in a container
# without those packages).  They are not errors, so they are reported
# separately from genuinely unknown ones.
DISTRO_MACROS := build_ldflags|build_cflags|build_cxxflags|_unitdir|_sysusersdir|_tmpfilesdir|_docdir

lint:
	@rc=0; \
	for s in $(SPECS); do \
	    printf '==> %s\n' "$$s"; \
	    out=$$(mktemp); err=$$(mktemp); \
	    if ! rpmspec --define "dist .$(DIST_TAG)" -P "$$s" > "$$out" 2> "$$err"; then \
	        sed 's/^/    /' "$$err"; rc=1; rm -f "$$out" "$$err"; continue; \
	    fi; \
	    unexpanded=$$(grep -oE '%\{[A-Za-z_][A-Za-z0-9_]*\}' "$$out" | sort -u); \
	    unknown=$$(printf '%s\n' "$$unexpanded" | grep -vE '^%\{($(DISTRO_MACROS))\}$$' | grep . || true); \
	    if [ -n "$$unknown" ]; then \
	        echo "    ERROR: unknown macros left unexpanded:"; \
	        printf '%s\n' "$$unknown" | sed 's/^/      /'; rc=1; \
	    elif [ -n "$$unexpanded" ]; then \
	        echo "    note: distro-provided macros unexpanded off-target (expected):"; \
	        printf '%s\n' "$$unexpanded" | tr '\n' ' ' | sed 's/^/      /'; echo; \
	    fi; \
	    printf '    ok (%s lines)\n' "$$(wc -l < "$$out")"; \
	    rm -f "$$out" "$$err"; \
	done; \
	exit $$rc

vendor:
	./scripts/vendor-otelcpp.sh

sources:
	./scripts/fetch-sources.sh

rpms: vendor sources
	./scripts/build-all.sh all

smoke:
	./scripts/smoke-test.sh

image:
	podman build -t haproxy-otel-builder -f Containerfile .

shell: image
	podman run --rm -it -v "$(CURDIR):/build:z" haproxy-otel-builder /bin/bash

clean:
	rm -rf $(TOPDIR)/BUILD $(TOPDIR)/BUILDROOT $(TOPDIR)/RPMS $(TOPDIR)/SRPMS

distclean: clean
	rm -rf $(TOPDIR)
	rm -f SOURCES/*.tar.gz SOURCES/*.tar.zst
