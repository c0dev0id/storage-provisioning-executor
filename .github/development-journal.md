# Development Journal

## Software Stack

- **Language:** Python 3.11+ (uses PEP 604 unions, `from __future__ import annotations`).
- **YAML parser:** `PyYAML` (`python3-yaml`, udeb variant `python3-yaml-udeb`), `safe_load` only.
- **CLI:** `argparse` (stdlib) — no click, to keep udeb dependencies minimal.
- **Logging:** `logging` (stdlib), one `sprov` logger; verbosity mapped from `-v`/`-q`.
- **Testing:** `pytest` + `pytest-cov`; integration tests gated by `--run-integration` / `INTEGRATION=1` env.
- **Static analysis:** `pylint` (warning-clean required) + `mypy --strict`.
- **Build:** GNU Make (available on OpenBSD as `gmake`; Debian `make` is GNU).
- **Packaging:** debhelper-compat = 13 (expressed in `Build-Depends`, no `debian/compat` file), `dh-python`, native source format `3.0 (native)`.
- **CI:** GitHub Actions with 6 jobs — lint, unit matrix (3.11/3.12/3.13), scriptgen-shellcheck (dash dialect), build-packages (debian:trixie-slim container), integration (privileged debian:trixie-slim with loop devices), release (tag-triggered).
- **Runtime dependencies (targets):** parted, mdadm, cryptsetup-bin, lvm2, e2fsprogs, dosfstools, xfsprogs, util-linux, gdisk (and their `-udeb` counterparts).

## Key Decisions

1. **Generated shell matches live execution by construction.**
   Every node implements `command_lines() -> list[ShellCommand]`. `Executor` feeds each `ShellCommand.argv` to `SystemCommand.run()`; `ScriptGenerator` feeds the same list through `shlex.quote`. The two consumers share one source of truth, so a scriptgen regression implies an executor regression and vice versa — no parallel strings to keep in sync.

2. **Stable topological order.**
   Kahn's algorithm with a min-heap keyed by original YAML source index. Gives deterministic execution order → deterministic scriptgen output → golden-file test on OpenBSD catches any drift in Linux command construction.

3. **Mount reordering is a post-pass, not a DAG dependency.**
   Filesystems produce no device path, so pulling them to the tail of the executed order preserves every data dependency. Stable-sort by mountpoint segment count enforces `/` before `/boot` before `/boot/efi` without inventing artificial parents.

4. **Partition offset math in YAML source order with MiB-cursor chain.**
   Partitions are numbered per parent in source order (not topo order) because partition index = appearance order. The running cursor is a whole-MiB integer, chained through `size + size + …`; any `begin` expression that doesn't land on a MiB boundary breaks the chain, and subsequent partitions fall back to parted expression arithmetic (`begin + sizeB`).

5. **Passphrases via heredoc and stdin, never on argv.**
   `SystemCommand.run(stdin=bytes)` pipes secrets to the child process. `ScriptGenerator` emits `cmd <<'SPROV_STDIN_EOF'` with the marker quoted to disable shell expansion. Collision with the marker in the payload raises a `ValueError` at emit time.

6. **YAML 1.1 bool quirk handling.**
   `yes`/`no` are parsed by PyYAML as Python booleans unless quoted. `_as_yes_no()` accepts both and coerces to the canonical string.

7. **Re-runnability via pre-flight cleanup.**
   At the top of a normal (non-dry-run) run we call `umount -R <control.path>` with errors ignored. Disabled via `--no-cleanup-first`. Per-node tear-down is already the cleanup path on failure.

8. **Test strategy split by axis.**
   Dev on OpenBSD → unit + golden-file only (pure logic, scriptgen diff catches any command-construction regression). Integration tests run exclusively in CI inside a `debian:trixie-slim --privileged` container, against `losetup -P` loop devices over sparse files.

9. **Two Debian binary packages, one source.**
   `sprov` carries man page and full deps; `sprov-udeb` strips docs/changelog/compress via `-psprov`-scoped overrides in `debian/rules` and depends on `-udeb` counterparts for debian-installer. Both from a single `3.0 (native)` source.

10. **`partx -a -n N:N` not `partx -u` for adding new partitions in containers.**
    `partx -u` issues `BLKPG_UPD_PARTITION` for *all* existing partitions plus the new one. udevd converts each UPD event into a "change" event that temporarily removes then recreates the partition's device node while re-evaluating udev rules. Any concurrent `mkfs` or `pvcreate` on one of those partitions can therefore see `ENXIO`. `partx -a -n N:N` sends a single `BLKPG_ADD_PARTITION` for only partition N — no churn on existing nodes. This matters in Docker `--privileged` containers because the container runs its own udevd against its own devtmpfs (isolated from the host `/dev`), so all device nodes must be managed explicitly; there is no host udevd to fall back on.

11. **LVM: create inactive (`-an`), then activate, then make nodes.**
    `lvcreate` without `-an` activates the LV immediately and tries to zero the new DM device. In a privileged container this sometimes fails with "device not cleared" because the DM target appears before udev has set up the device node, leading to a zero-write on a phantom device. The fix is: `lvcreate -an` (no activation, no device access), then `lvchange -ay` (explicit activation), then `vgmknodes` (create `/dev/VG/LV` nodes). The three-step sequence is deterministic and avoids the race entirely.

12. **`gmake` on OpenBSD unlocks GNU Make idioms.**
    Suffix-rule automatic variables like `$<` and `$(wildcard)` are GNU-only under BSD make but the project is built on Debian where `/usr/bin/make` is GNU. Using `gmake` on the dev box keeps the Makefile portable without a second dialect.

## Core Features

- **Live provisioning mode:** parse spec → build DAG → topo sort → execute → reverse cleanup on failure.
- **Script generation mode (`--script`):** emit a POSIX shell script that, when run, achieves the same end state. BusyBox-compatible (dash), stdin via heredocs.
- **Dry-run mode (`--dry-run`):** log every command, never fork.
- **Variable expansion (`{{var}}`):** walks every leaf string in the parsed YAML tree before node instantiation; undefined variable → `KeyError`.
- **Node contract:** `validate()` / `execute()` / `device_path()` / `command_lines()` / `register_cleanup()`. Uniform surface across all node types keeps executor and scriptgen simple.
- **Node types:** `hardware`, `partition`, `lvm-pv`, `lvm-vg`, `lvm-lv`, `raid1`, `dm-crypt-luks`, `filesystem`, `swap`.
- **Per-node `ignore_errors`:** wraps `command_lines()` via `Node.effective_command_lines()` — the single point where the flag is applied — so live executor and script generator stay in sync (live: `check=False`; script: `|| true` suffix).
- **Man page (`sprov(8)`):** mdoc-formatted, `@VERSION@` substituted from the Debian changelog at build time.
