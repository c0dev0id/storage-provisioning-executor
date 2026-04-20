# SPDX-License-Identifier: GPL-2.0-or-later

PYTHON   ?= /usr/bin/python3
DESTDIR  ?=
PREFIX   ?= /usr
PYLIBDIR ?= $(PREFIX)/lib/python3/dist-packages
BINDIR   ?= $(PREFIX)/bin
MANDIR   ?= $(PREFIX)/share/man/man8

VERSION  ?= 0.1.0

PY_SOURCES := $(wildcard storage/*.py)
MAN_PAGE := doc/sprov.8
BINARY   := sprov

.PHONY: all clean install uninstall check lint

all: $(BINARY) $(MAN_PAGE)

$(BINARY): bin/sprov.in
	sed 's|@PYTHON@|$(PYTHON)|' $< > $@
	chmod +x $@

$(MAN_PAGE): doc/sprov.8.in
	sed 's|@VERSION@|$(VERSION)|g' $< > $@

install: all
	install -d $(DESTDIR)$(BINDIR)
	install -d $(DESTDIR)$(PYLIBDIR)/storage
	install -d $(DESTDIR)$(MANDIR)
	install -m 0755 $(BINARY) $(DESTDIR)$(BINDIR)/$(BINARY)
	install -m 0644 $(PY_SOURCES) $(DESTDIR)$(PYLIBDIR)/storage/
	install -m 0644 $(MAN_PAGE) $(DESTDIR)$(MANDIR)/sprov.8

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/$(BINARY)
	rm -rf $(DESTDIR)$(PYLIBDIR)/storage
	rm -f $(DESTDIR)$(MANDIR)/sprov.8

clean:
	rm -f $(BINARY) $(MAN_PAGE)
	rm -rf build/ dist/ .pytest_cache/ .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

check:
	$(PYTHON) -m pytest tests/

lint:
	$(PYTHON) -m pylint storage/
	$(PYTHON) -m mypy --strict storage/
