# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-20

### Added
- Declarative YAML storage-topology spec with `{{var}}` expansion and a single
  `control` entry defining the target mount root.
- DAG-based execution via Kahn topological sort; stable by YAML source order
  for deterministic output.
- Node types: `hardware`, `partition`, `lvm-pv`, `lvm-vg`, `lvm-lv`, `raid1`,
  `dm-crypt-luks`, `filesystem`.
- Automatic mount ordering: filesystems are pulled to the tail of the execution
  order and sorted by mountpoint depth so `/` mounts before `/boot` and
  `/boot/efi`.
- Reverse cleanup on failure: each node registers tear-down closures during
  execute; on exception the executor walks succeeded nodes in reverse and
  invokes each cleanup (umount → cryptsetup close → vgchange -an → mdadm --stop).
- Pre-flight cleanup (`--no-cleanup-first` to disable) to make a failed run
  re-runnable.
- `--dry-run` mode: commands are logged but never forked.
- `--script` mode: emits a POSIX shell script equivalent to live execution,
  verified against `sh -n` and `shellcheck -s dash` in CI.
- `sprov(8)` man page with full option reference, exit-status table, and
  supported node-type list.
- Debian source package with two binary packages: `sprov` (runtime) and
  `sprov-udeb` (debian-installer variant, docs/man stripped).
- Makefile build with `all`, `install`, `uninstall`, `clean`, `check`, `lint`
  targets; `DESTDIR`, `PREFIX`, `PYTHON`, `VERSION` configurable.
- GitHub Actions CI: pylint + mypy strict lint, pytest matrix on Python
  3.11/3.12/3.13, shellcheck under dash, debhelper-13 package build with
  `lintian --fail-on warning`, integration tests inside a privileged Debian
  container running against loopback-mounted sparse files, and tag-triggered
  GitHub release uploading the built packages.

[Unreleased]: https://github.com/c0dev0id/storage-provisioning-executor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/c0dev0id/storage-provisioning-executor/releases/tag/v0.1.0
