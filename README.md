# sprov — Storage Provisioning Executor

`sprov` reads a YAML file describing a storage topology and provisions it
against live block devices in the correct order. It handles the full stack:
partition tables, RAID, LUKS encryption, LVM, and filesystems — all driven
from a single declarative spec.

## Installation

```sh
make install          # installs to /usr/bin/sprov by default
make install PREFIX=/usr/local
make install DESTDIR=/tmp/staging PREFIX=/usr
```

Build-time dependencies: Python 3, make.  
Runtime dependencies: `parted`, `mdadm`, `cryptsetup`, LVM tools (`pvcreate`,
`vgcreate`, `lvcreate`), `mkfs.*`, `mount`.

## Quick Start

```sh
# Dry-run — shows every command that would execute, touches nothing
sprov --dry-run /etc/sprov/install.yaml

# Live run
sprov /etc/sprov/install.yaml

# Generate a portable shell script instead
sprov --script /etc/sprov/install.yaml > install.sh
```

## How It Works

`sprov` parses the YAML spec into a directed acyclic graph (DAG) of storage
nodes. Each node declares its `parents`, which establishes the dependency
order. The executor performs a topological sort and runs nodes in sequence.

Mountpoints are rooted beneath `control.path`. With `control.path: /target`,
a filesystem mounted at `/boot` lands at `/target/boot`.

On failure, `sprov` attempts reverse cleanup: unmount filesystems, close LUKS
devices, deactivate LVM, stop RAID arrays — so re-running is safe without
manual intervention.

## Spec Format

The spec is a YAML file with two top-level keys:

```yaml
vars:
  hostname: "myhost"      # optional — available as {{hostname}} in fields

storage:
  - type: control
    path: /target         # all mountpoints are prefixed with this
  - ...
```

### Node Types

| Type | Description |
|---|---|
| `control` | Sets the mount prefix (`path`) |
| `hardware` | Physical disk — creates partition table, optional erase |
| `partition` | Partition on a `hardware` node |
| `raid1` | Software RAID-1 array (`mdadm`) |
| `lvm-pv` | LVM physical volume |
| `lvm-vg` | LVM volume group |
| `lvm-lv` | LVM logical volume |
| `dm-crypt-luks` | LUKS-encrypted block device |
| `filesystem` | Formats and mounts a block device |

Every node except `control` and `hardware` must declare `parents` (a string
or list of node `id` values).

### Hardware Node

```yaml
- type: hardware
  id: hw-sda
  path: /dev/sda
  overwrite: "yes"      # recreate partition table
  erase: "1G"           # zero first 1 GiB (or "all" for full wipe)
  align: 8              # partition alignment in MiB
  label: gpt
```

### Partition Node

```yaml
- type: partition
  id: part-boot
  parents: hw-sda
  label: boot
  begin: "2048s"        # optional start sector
  size: "4G"            # or "{max}" to fill remaining space
  uuid: "..."
  flags: [boot, esp]
```

### Filesystem Node

```yaml
- type: filesystem
  id: fs-root
  parents: crypt-root
  fstype: ext4
  label: "{{hostname}}-root"
  mountpoint: /
  mkfs_options: []
```

### LUKS Node

```yaml
- type: dm-crypt-luks
  id: crypt-root
  parents: lvm-lv-c_root
  key:
    slot: 3
    passphrase: "secret"
```

## CLI Reference

```
sprov [OPTIONS] SPEC
```

| Option | Description |
|---|---|
| `-n`, `--dry-run` | Log every command without executing it |
| `-v` / `-vv` / `-vvv` | Increase verbosity (normal → verbose → debug) |
| `-q` | Decrease verbosity (down to silent — warnings and errors only) |
| `--script` | Emit a busybox/dash-compatible POSIX shell script to stdout and exit |
| `--no-cleanup-first` | Skip the pre-flight `umount -R` of `control.path` |
| `--version` | Print version and exit |

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Spec validation error (bad YAML, unknown type, cycle, missing field) |
| 2 | Execution error; cleanup attempted |
| 64 | CLI usage error (missing argument, unreadable file) |

## Shell Script Mode

`--script` emits a POSIX shell script targeting dash/busybox. The script uses
`set -eu`, runs the same commands as the live executor in topological order,
and passes secrets via heredocs so they do not appear in `ps` output.

```sh
sprov --script /etc/sprov/install.yaml > /tmp/install.sh
sh -n /tmp/install.sh   # syntax check without executing
```

## Man Page

A man page is installed at `share/man/man8/sprov.8`. After installation:

```sh
man sprov
```

The source is at `doc/sprov.8.in`.

## License

GPL-2.0-or-later. See [COPYING](COPYING).
