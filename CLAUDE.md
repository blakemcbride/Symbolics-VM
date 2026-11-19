# linux-vlm

Emulator for the Symbolics Virtual Lisp Machine (VLM). It runs Open
Genera 2.0 (Genera 8.5) on x86-64 Linux. The emulator is C; Genera
itself is a proprietary world image that is **not** in this repository.

User-facing documentation, read these before changing behaviour:

- `README` — build, what is missing and where to get it, running
- `NETWORKING` — tap device, NFS/time server, firewall, troubleshooting
- `Setup.md` — defining a site and saving a configured world
- `docs/README` — reading order for the Symbolics manuals in `docs/`

## Layout

- `emulator/` — Ivory instruction emulator
- `life-support/` — host services: cold load window (`cold_load.c`,
  Xlib), X relay for Genera's main screen (`console.c`), network
  (`network-tap-linux.c`), disks, initialization
- `src/` — `main.c`, option and `.VLM` parsing (`utilities.c`), world
  loading (`world_tools.c`); builds `src/genera`
- `stub/` — `process.lisp` generates the `stub/*.c` instruction code
- `nfs2d.py` — user-space NFS v2 + RFC 868 time server (Python stdlib)
- `setup-tap.sh`, `run-genera.sh` — tap device creation, one-step start
- `dot.VLM`, `dot.run-genera.conf` — samples for the local, untracked
  `.VLM` and `run-genera.conf`

## Build

    autoreconf -fi && ./configure && make

- Needs clisp: `stub/*.c` are regenerated from `stub/process.lisp`
  during `make`, and show large diffs (gensym label renames) each time.
- `autoreconf -fi` overwrites the tracked `INSTALL`; restore it with
  `git checkout INSTALL`.
- `make distclean` removes all generated files. Subdirectory Makefiles
  and `TAGS` are intentionally untracked.
- Modern-toolchain fixes already in place, do not undo:
  - `configure.ac`: no `AC_PROG_CC_STDC`; libcrypt is checked with
    `crypt` (not `encrypt`); `-std=gnu17` because GCC 15+ defaults to
    C23, which breaks `bool` and `()` prototypes in this code.
  - `stub/process.lisp` emits `goto *(void *)reg;` (computed goto must
    be a pointer).

## Running

    ./run-genera.sh [genera options]

It creates the tap device and starts `nfs2d.py` if missing (sudo only
then), and runs `src/genera`. Things to know:

- Needs external files: a world (`Genera-8-5.vlod`), `VLM_debugger`,
  and the `sys.sct` tree, all from an Open Genera 2.0 distribution.
- Config is `.VLM` in `$HOME` or the starting directory; command-line
  options override it. `-world` is used as given, relative to the
  starting directory; there is no search path for the main world.
- Without the tap device genera exits with
  `TUNSETIFF: Operation not permitted`.
- `genera` ignores SIGTERM (it asks for confirmation on its terminal).
  In scripts use `timeout -s KILL` or `kill -9`. The clean exit is the
  Genera command `Halt Genera`.
- Only one instance can use a tap device and address at a time.
- genera changes the X modifier map of the whole display (Meta on Alt,
  Hyper on Menu, NumLock dropped) and does not restore it when killed.

## Network facts

- Default addresses: host 10.0.0.1 on `tap0`, Genera 10.0.0.2. Genera
  calls itself DIS-LOCAL-HOST and the host DIS-EMB-HOST (alias `HOST`).
- Genera answers ping about 10 seconds after start. The distribution
  world offers no network services, so it cannot be driven remotely;
  steps inside Genera must be typed by a person at its window.
- At boot Genera broadcasts a time request (UDP 255.255.255.255:37).
  If unanswered it prompts for the date, then fails with "Unable to set
  calendar clock" and leaves the network down. `nfs2d.py` answers it,
  using a second socket bound to the tap device for the broadcast.
- Genera's NFS client is version 2 over UDP only. Current kernels do
  not serve v2, hence `nfs2d.py` (portmapper, mount v1, NFS v2). It is
  read-only unless `--rw`; file handles go stale when it restarts.
- A host firewall with a default-deny input policy silently drops all
  of this while still passing pings. Check for ufw/nftables rules, not
  only firewalld.
- `HOST:` paths in Genera mean two different things: ordinary files go
  over NFS, relative to the `nfs2d.py --root` directory; world files
  (boot and `Save World`) are opened by the emulator with the real
  Linux path. `Save World name.vlod` with a bare name saves beside the
  world that was booted (verified).

## Display facts

- Two windows are normal: the cold load stream (fallback console, used
  at boot and for serious errors) and Genera's main screen.
- The main screen is an X client written in Lisp inside the world. It
  sends raw X protocol, which `console.c` relays byte for byte. There
  is no drawing code in C to port; replacing X would mean embedding an
  X server subset or writing a new screen driver inside Genera.
- `console.c` rewrites Genera's `SetModifierMapping` request to leave
  the server's map unchanged. Genera puts keycodes on two modifiers,
  which current X servers reject with BadValue, killing the screen
  process. Do not remove this filter.
- Works under XWayland. Tiling window managers ignore the geometry
  options.
- PC keys: SELECT = F1, ABORT = F6, RESUME = F5, CLEAR INPUT = F9,
  HELP = Insert, Meta = Alt. `<Select> D` in Symbolics manuals means
  press F1, then D.

## Genera source as reference

The `sys.sct` tree holds the Lisp source of Genera and is the best
reference for its behaviour. Files carry version suffixes
(`name.lisp.~123~`). Useful places: `io1/time.lisp` (boot time logic),
`x11/screen/x-console.lisp` (keyboard and screen), `l-sys/disk-save.lisp`
(Save World), `cp/utility-commands.lisp` (Halt Genera and friends),
`site/` (starter site files, `sys.translations`).

## Status

- Verified: build, boot to `Command:`, time from the host, reading
  documentation over NFS (Document Examiner), `Save World`.
- Not verified: Genera writing through `nfs2d.py --rw`, the
  `Define Site` / `Set Site` steps in `Setup.md`, `Halt Genera`,
  the tap-creating and server-starting branches of `run-genera.sh`.

## Conventions

- Documentation is plain text or Markdown at the top level, short and
  practical. Keep `README`, `NETWORKING` and `Setup.md` consistent when
  behaviour changes.
- Symbolics software (worlds, debugger, `sys.sct`) is proprietary and
  must never be committed. The manuals in `docs/` are an exception the
  owner chose to include.
- Do not commit local files: `.VLM`, `run-genera.conf`, build output.
