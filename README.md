# storage-provisioning-executor

```id="v7m3l2"
You are to implement a production-quality storage provisioning executor for Linux (Debian-based rescue/installer environment).

The solution must include:
1. A Python implementation (primary executor)
2. A BusyBox-compatible shell script generator (secondary output mode)
3. A complete build system (Makefile)
4. Debian packaging (producing both .deb and .udeb packages)
5. License: GPL-2.0-or-later

────────────────────────────────────────────────────────────
1. HIGH-LEVEL GOAL
────────────────────────────────────────────────────────────

Given a YAML specification describing a storage topology as a directed acyclic graph (DAG), the program must:

1. Parse and normalize the YAML
2. Build a dependency graph using `parents`
3. Perform topological sorting
4. Execute storage operations in correct order

End state:
- Filesystems are mounted at mountpoints
- Each mountpoint is prefixed with `control.path`

Example:
  control.path = "/target"
  mountpoint = "/srv"
  → actual mountpoint = "/target/srv"

────────────────────────────────────────────────────────────
2. EXAMPLE INPUT YAML
────────────────────────────────────────────────────────────

The implementation MUST support at least the following structure:

---
vars:
  hostname: "foo"
storage:
  - type: "control"
    path: "/target"

  - type: "hardware"
    id: "hw-sda"
    path: "/dev/sda"
    overwrite: "yes"
    align: 8
    label: "gpt"

  - type: "partition"
    parents: "hw-sda"
    id: "part-EFI"
    label: "EFI"
    begin: "2048s"
    size: "4G"
    uuid: "xyz"
    flags:
      - boot
      - esp

  - type: "partition"
    parents: "hw-sda"
    id: "part-boot"
    label: "boot"
    size: "4G"
    uuid: "xzy"

  - type: "partition"
    parents: "hw-sda"
    id: "part-lvm-pv"
    label: "lvm-pv"
    size: "25G"

  - type: "lvm-pv"
    id: "lvm-pv"
    parents: "part-lvm-pv"

  - type: "lvm-vg"
    id: "lvm-vg-host"
    parents: ["lvm-pv"]

  - type: "lvm-lv"
    id: "lvm-lv-c_root"
    name: "c_root"
    parents: "lvm-vg-host"
    size: "8G"

  - type: "dm-crypt-luks"
    id: "crypt-root"
    parents: "lvm-lv-c_root"
    key:
      slot: 3
      passphrase: "1234"

  - type: "filesystem"
    id: "fs-root"
    fstype: "ext4"
    label: "{{hostname}}-root"
    parents: "crypt-root"
    mountpoint: "/"
    mkfs_options: []

  - type: "filesystem"
    id: "fs-boot"
    fstype: "ext4"
    label: "{{hostname}}-boot"
    parents: "part-boot"
    mountpoint: "/boot"
    mkfs_options: []

  - type: "filesystem"
    id: "fs-efi"
    fstype: "fat32"
    label: "{{hostname}}-EFI"
    parents: "part-EFI"
    mountpoint: "/boot/efi"
    mkfs_options: []

  - type: "hardware"
    id: "hw-ssd1"
    overwrite: "yes"
    erase: "all"
    path: "/dev/disk/by-id/nvme_Vendor_device_Serial1"
    align: 8
    label: "gpt"

  - type: "partition"
    parents: "hw-ssd1"
    id: "part-ssd1"
    begin: "2048s"
    size: "{max}"
    uuid: "xyz"

  - type: "hardware"
    id: "hw-ssd2"
    overwrite: "yes"
    erase: "1G"
    path: "/dev/disk/by-id/nvme_Vendor_device_Serial2"
    align: 8
    label: "gpt"

  - type: "partition"
    parents: "hw-ssd2"
    id: "part-ssd2"
    begin: "2048s"
    size: "{max}"
    uuid: "xyz"

  - type: "raid1"
    id: "nvme-softraid"
    parents: ["part-ssd1", "part-ssd2"]
    name: "md128"

  - type: "filesystem"
    id: "xfs-softraid"
    parents: "nvme-softraid"
    fstype: "xfs"
    label: "ssdraid"
    mountpoint: "/srv"
    mkfs_options: []

────────────────────────────────────────────────────────────
3. EXECUTION ENVIRONMENT
────────────────────────────────────────────────────────────

- Debian-based rescue or installer system
- Operates directly on real block devices
- Uses system tools via subprocess:

  parted (for partitioning; REQUIRED)
  mdadm
  cryptsetup
  LVM tools (pvcreate, vgcreate, lvcreate)
  mkfs.*
  mount / umount

- Capture stdout, stderr, exit codes
- Fail fast on error with cleanup

────────────────────────────────────────────────────────────
4. FAILURE HANDLING / CLEANUP
────────────────────────────────────────────────────────────

On failure:

1. Abort execution immediately
2. Cleanup in reverse order:
   - unmount filesystems
   - close dm-crypt
   - deactivate LVM
   - stop RAID

System must be re-runnable without manual intervention.

────────────────────────────────────────────────────────────
5. DESTRUCTIVE BEHAVIOR
────────────────────────────────────────────────────────────

Always recreate from scratch.

Hardware options:
- overwrite: "yes" → recreate partition table
- erase: "all" → zero entire device
- erase: "1G" → zero first 1 GiB

────────────────────────────────────────────────────────────
6. DATA MODEL
────────────────────────────────────────────────────────────

- parents may be string or list → normalize to list
- size: "{max}" = all remaining space respecting alignment

────────────────────────────────────────────────────────────
7. PYTHON IMPLEMENTATION
────────────────────────────────────────────────────────────

Requirements:
- Python 3
- Pylint-clean
- Typed
- Modular class-based design

Structure:

storage/
  base.py
  hardware.py
  partition.py
  raid.py
  crypt.py
  lvm.py
  filesystem.py
  executor.py
  system.py
  scriptgen.py
  main.py

Each node:
- validate()
- execute()

Executor:
- builds DAG
- topological sort
- executes nodes

Use a SystemCommand abstraction:
- wraps subprocess
- captures stdout/stderr
- supports dry-run

────────────────────────────────────────────────────────────
8. MODES
────────────────────────────────────────────────────────────

- normal execution
- dry-run (no changes)
- verbosity levels: silent, normal, verbose, debug

Debug must include commands, outputs, and decisions.

────────────────────────────────────────────────────────────
9. SHELL SCRIPT GENERATION
────────────────────────────────────────────────────────────

Add mode to emit BusyBox-compatible shell script:

- POSIX shell only (dash / BusyBox)
- sequential execution
- minimal error handling (set -e)
- no DAG logic required
- include explanatory comments

Script must use:
- parted for partitioning
- same commands as Python executor

────────────────────────────────────────────────────────────
10. MAKEFILE
────────────────────────────────────────────────────────────

Provide:
- all
- clean
- install
- uninstall

Must support DESTDIR.

────────────────────────────────────────────────────────────
11. DEBIAN PACKAGING
────────────────────────────────────────────────────────────

Provide debian/ directory with:

- control (must use debhelper-compat (= 13))
- rules
- changelog
- copyright
- install
- dirs

Requirements:

- Use debhelper-compat level 13 (no debian/compat file)
- Build both:
  - .deb package
  - .udeb package

- .udeb must be suitable for installer use (minimal dependencies)

────────────────────────────────────────────────────────────
12. LICENSE
────────────────────────────────────────────────────────────

GPL-2.0-or-later.
Include license file and headers.

────────────────────────────────────────────────────────────
13. OUTPUT REQUIREMENT
────────────────────────────────────────────────────────────

Return a complete working project:

- Python implementation
- Shell script generator
- Makefile
- Debian packaging
- No placeholders
- No pseudo-code

Code must be directly usable.

END OF SPEC
```
