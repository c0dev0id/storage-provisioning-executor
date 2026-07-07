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

13. **No mknod fallback for partition device nodes; `partx -a` is `check=False`; CI environment must match a real Debian install.**
    The earlier `sh -c 'partx; udevadm settle; poll sysfs; mknod'` block was over-cautious in a real installer/rescue/live-boot environment, where `/dev` is `devtmpfs` and the kernel itself creates block-device nodes when `add_disk()` / `bdev_add_partition()` runs. udev then handles rules, symlinks, and permissions. `partx -a -n N:N` + `udevadm settle` is sufficient there; mknod is dead code. Removing it also collapses the emitted script from an unreadable one-liner per partition to two named commands. The `partx -a` step is emitted with `check=False` (script: `|| true`): if the kernel has already auto-rescanned the partition table — which happens on loop devices attached with `losetup -P`, and on some kernel versions after any `BLKPG_UPD` — `partx -a` returns rc=1 "error adding partition N". That is not an error; the node already exists. `udevadm settle` remains the real gate, and any downstream command that actually needs the partition device path will surface a genuine failure. **CI caveat:** in the GHA `debian:trixie-slim --privileged` container, `/dev` is Docker-managed tmpfs, not devtmpfs, and the `udev` package's daemon binary is `systemd-udevd`, not `udevd`. Without both `mount -t devtmpfs devtmpfs /dev` and starting `/lib/systemd/systemd-udevd --daemon`, partition nodes never appear and every integration test fails. This was masked for a long time because the old sh-c blob's mknod fallback was silently doing the work while `udevd --daemon` had been failing with "command not found" under `2>/dev/null || true`. Do not suppress errors in daemon-startup steps.

14. **Kernel modules aggregate before DAG, not per-node during DAG.**
    Both `control` and any node accept a `modules: [...]` list; `collect_modprobe_commands()` (in `storage/base.py`) walks context modules first, then every node's modules in DAG-execution order, deduping by first appearance. Result is emitted at the very top: as one `# === modules ===` block in `--script` mode and as `modprobe X` calls before `Executor` enters its per-node loop in live mode. Rationale: a kernel `modprobe` is a global side-effect on the running kernel, and mixing it into the middle of the DAG hides that fact from the reader of the generated script. Per-node declaration is retained for spec portability — a node's kernel-module dependency travels with the node into other spec files — but the *execution* is always "prerequisites first, work second." `modprobe` is idempotent (no-op if built-in or already loaded), so running everything up-front is safe.

## Core Features

- **Live provisioning mode:** parse spec → build DAG → topo sort → execute → reverse cleanup on failure.
- **Script generation mode (`--script`):** emit a POSIX shell script that, when run, achieves the same end state. BusyBox-compatible (dash), stdin via heredocs.
- **Dry-run mode (`--dry-run`):** log every command, never fork.
- **Variable expansion (`{{var}}`):** walks every leaf string in the parsed YAML tree before node instantiation; undefined variable → `KeyError`.
- **Node contract:** `validate()` / `execute()` / `device_path()` / `command_lines()` / `verify_command_lines()` / `register_cleanup()`. Uniform surface across all node types keeps executor and scriptgen simple. `verify_command_lines()` runs after every node has executed successfully — currently only `FilesystemNode` overrides it, with a `mountpoint -q` check per mount.
- **Node types:** `hardware`, `partition`, `lvm-pv`, `lvm-vg`, `lvm-lv`, `raid1`, `dm-crypt-luks`, `filesystem`, `swap`.
- **Per-node `ignore_errors`:** wraps `command_lines()` via `Node.effective_command_lines()` — the single point where the flag is applied — so live executor and script generator stay in sync (live: `check=False`; script: `|| true` suffix).
- **Kernel-module loading:** `modules: [...]` on `control` and/or any node; aggregated + deduped by `collect_modprobe_commands()` and emitted before any node's own commands, so both live and `--script` modes load prerequisites up-front.
- **Man page (`sprov(8)`):** mdoc-formatted, `@VERSION@` substituted from the Debian changelog at build time.
