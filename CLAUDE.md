# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Global rules from `~/.claude/CLAUDE.md` (changelog, development journal, git config, code style, commit/rebase workflow) also apply — do not duplicate them here.

## What this is

`sprov` is a Python CLI that reads a YAML spec describing a Linux storage topology (partitions, RAID, LUKS, LVM, filesystems, swap) and provisions it against live block devices. Target environment is a Debian-based rescue/installer (including debian-installer via a `-udeb` variant).

Two output modes share one implementation:
- **Live executor** — runs commands directly against the system.
- **`--script`** — emits a busybox/dash-compatible POSIX shell script that produces the same end state.

## Commands

Development-loop commands (Python is invoked via `python3` — respect the venv rule in the global file when installing anything):

```sh
make check                            # pytest tests/ (unit tests only by default)
make lint                             # pylint storage/ && mypy --strict storage/
make all                              # substitutes @PYTHON@/@VERSION@ into bin/sprov and doc/sprov.8
make clean

python3 -m pytest tests/unit -q                       # unit tests
python3 -m pytest tests/unit/test_executor_topo.py    # single file
python3 -m pytest tests/unit -k mount_order           # single test by expression
python3 -m pytest tests/integration --run-integration # integration; Linux + privileged + loop devices only
```

Integration tests are skipped unless `--run-integration` is passed or `INTEGRATION=1` is set. They **cannot run on the OpenBSD dev box** — they need `losetup -P`, udev, and privileged Linux. CI runs them in a `debian:trixie-slim --privileged` container; locally they only run under the same conditions.

Running the CLI without installing:

```sh
make all
PYTHONPATH="$PWD" ./sprov --dry-run tests/data/example.yaml
PYTHONPATH="$PWD" ./sprov --script  tests/data/example.yaml > /tmp/out.sh
```

## Architecture

### Node contract (`storage/base.py`)

Every storage operation is a `Node` subclass with a small uniform surface:

- `validate()` — field checks; raise `NodeValidationError`.
- `command_lines() -> list[ShellCommand]` — the canonical list of shell operations. **This is the single source of truth consumed by both the live `Executor` and the `ScriptGenerator`.** Break this invariant and generated scripts silently diverge from live runs. If a node needs runtime-derived state that the script generator can't know, override `execute()` and return `[]` from `command_lines()` (the node will simply be absent from generated scripts — do this deliberately).
- `_post_execute()` — register cleanup closures via `register_cleanup()`; the `Executor` invokes them in reverse order on failure.
- `device_path() -> str | None` — block device this node produces (consumed by children).

`ShellCommand` (dataclass) carries `argv`, optional `stdin` bytes (secrets **must** go on stdin, never argv, so they don't appear in `/proc/<pid>/cmdline`), an optional `comment`, and a `check` flag.

### Pipeline (`storage/spec.py` → `storage/executor.py`)

1. `load_spec()` — YAML → dict → variable expansion (`{{name}}` walks every leaf string) → instantiate nodes via `TYPE_REGISTRY`. Exactly one `control` entry is required and produces `Context.control_path`.
2. `Executor.prepare()`:
   - Resolve parent refs.
   - Assign per-parent partition indices in **YAML source order** (not topo order — partition index == appearance order) and compute MiB-cursor offsets.
   - Topological sort: Kahn's algorithm with a **min-heap keyed by original source index**. Order is deterministic; this is what makes the `tests/data/example.sh.golden` golden-file test meaningful.
   - Mount reordering post-pass: `FilesystemNode`s are stable-sorted to the tail by mountpoint depth so `/` mounts before `/boot` before `/boot/efi`. Filesystems produce no `device_path()`, so pulling them to the tail never breaks a data dependency.
   - Call `validate()` on every node.
3. `Executor.run()` — execute in order; on failure, invoke registered cleanup closures on succeeded nodes in reverse order and raise `NodeExecutionError`.

### Adding a new node type

1. Add a module under `storage/` implementing the `Node` contract.
2. Register in `TYPE_REGISTRY` in `storage/spec.py`.
3. Emit `ShellCommand` records from `command_lines()` — don't reach into `subprocess` yourself; the `SystemCommand` wrapper in `execute()` handles logging, dry-run, and stdin plumbing.
4. Unit test: pure-logic tests in `tests/unit/`. If it touches real devices, add an integration test in `tests/integration/` gated by the `integration` marker.
5. Regenerate the golden file if the example spec exercises the new type: `PYTHONPATH="$PWD" ./sprov --script tests/data/example.yaml > tests/data/example.sh.golden` — commit as its own change and inspect the diff.

### Non-obvious invariants (bite you if you don't know)

- **Container/udev races (see development journal for the full story):**
  - Adding a partition: use `partx -a -n N:N` (single `BLKPG_ADD_PARTITION` for the new partition only). **Never `partx -u`** — it fires `BLKPG_UPD_PARTITION` for every existing partition, which under a privileged container's own udevd re-creates each partition node and can race concurrent `mkfs`/`pvcreate` calls to `ENXIO`.
  - LVM in privileged containers: `lvcreate -an` (inactive) → `lvchange -ay` (activate) → `vgmknodes` (create device nodes). Skipping the split lets `lvcreate` try to zero a phantom DM device before udev has set the node up.
- **PyYAML 1.1 bool quirk:** `yes`/`no` unquoted parse as Python booleans. Fields like `overwrite: "yes"` are strings on purpose; helpers coerce both forms.
- **Secrets:** always via `ShellCommand.stdin` bytes. `ScriptGenerator` emits `cmd <<'SPROV_STDIN_EOF'`; a payload line equal to the marker aborts emission by design.
- **Size sentinel:** `parse_size("{max}")` returns the literal `"MAX"` (typed `Literal["MAX"]`, not an `int`). Callers must handle it before doing integer math. In partitions, `size: {max}` terminates the MiB cursor chain and any following partition in the same parent is invalid.
- **Python 3.11+** only. Code uses PEP 604 unions (`X | Y`) and relies on `from __future__ import annotations`.

## Testing conventions

- **Unit tests** are pure-logic and portable — they run on OpenBSD and in CI. They cover node validation, executor topology, mount ordering, size parsing, script generation, templating, and system-command behaviour.
- **Integration tests** exercise real Linux subsystems (loop devices, mdadm, LVM, LUKS, filesystems) via the fixtures in `tests/integration/conftest.py`. Marked `integration` and gated by `--run-integration` / `INTEGRATION=1`.
- **Golden-file test** at `tests/data/example.sh.golden` is the drift detector between YAML → generated script. It's the reason the topo sort has to be stable. Any intentional change to command construction requires regenerating and committing the golden.
- The dev flow is: write unit + golden coverage on OpenBSD; rely on CI's privileged Debian container for integration signal.

## CI (`.github/workflows/ci.yml`)

Six jobs on push/PR to main: `lint` (pylint + mypy --strict), `unit` (matrix 3.11/3.12/3.13 + coverage), `scriptgen-shellcheck` (shellcheck under dash), `build-packages` (dpkg-buildpackage in debian:trixie-slim + lintian), `integration` (privileged debian:trixie-slim consuming the built `.deb`), and `release` (tag-triggered, uploads the `.deb` and `.udeb` to a GitHub Release).

## Packaging

`debian/` produces two binaries from one native (`3.0 (native)`) source: `sprov` (full deps + man page) and `sprov-udeb` (stripped for debian-installer, depends on `-udeb` counterparts of `parted`, `mdadm`, `cryptsetup-bin`, `lvm2`, etc.). Version comes from `debian/changelog` and is substituted into `doc/sprov.8` via the Makefile.
