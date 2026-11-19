# Symbolics-VM

An emulator for the Symbolics Virtual Lisp Machine (VLM). It runs
**Open Genera 2.0** (Genera 8.5), the Symbolics Lisp Machine operating
system, on 64-bit x86 Linux.

This is a fork of [linux-vlm](https://github.com/jjachemich/linux-vlm)
by Joachim Jachemich, brought up to date so that it builds and runs on
a current Linux system, with the missing host-side pieces and
documentation added.

> **This repository contains only the emulator.** Genera itself is
> Symbolics proprietary software and is not included. See
> [What is not included](#what-is-not-included).

## Contents

- [What you get](#what-you-get)
- [What is not included](#what-is-not-included)
- [Requirements](#requirements)
- [Building](#building)
- [Setting up](#setting-up)
- [Running](#running)
- [Reading the on-line documentation](#reading-the-on-line-documentation)
- [Documentation](#documentation)
- [Changes in this fork](#changes-in-this-fork)
- [Known limitations](#known-limitations)
- [History and credits](#history-and-credits)

## What you get

| File | Purpose |
|---|---|
| `src/genera` (after building) | the emulator |
| `run-genera.sh` | starts everything in one step |
| `setup-tap.sh` | creates the network device Genera needs |
| `nfs2d.py` | NFS version 2 and time server, so Genera can read its files from the host |
| `dot.VLM`, `dot.run-genera.conf` | sample configuration files |
| `docs/` | the Symbolics manuals for Genera 8 and Open Genera |

## What is not included

The emulator alone runs nothing. You must supply three things from the
Symbolics Open Genera 2.0 distribution (a CD labelled
`OPEN_GENERA_2_0`, 1998):

| File | What it is | Needed |
|---|---|---|
| `Genera-8-5.vlod` | the Genera *world*: the Lisp system image | to boot |
| `VLM_debugger` | a debugger image loaded at startup | to boot |
| `sys.sct/` | Genera's sources, fonts and on-line documentation | for the Document Examiner and for loading more software |

How to find them:

- If you own Open Genera 2.0, use your CD or an image of it.
- Symbolics Technologies, the current rights holder, licenses Genera,
  at the time of writing free of charge for non-commercial use through
  its "Friends of Symbolics" program. See <https://www.symbolics.biz>.
- The manuals, though not the software, are public at
  <http://bitsavers.org/pdf/symbolics/software/genera_8/>. Copies are in
  [`docs/`](docs/).

On the CD the world and the debugger are inside the `VLMBASE200`
subset, and `sys.sct` is a directory at the top level:

    zcat AXP/OSF/VLMBASE200 | tar xf - ./usr/opt/VLM200/lib/symbolics

## Requirements

- Linux on x86-64
- gcc, make, autoconf and automake
- X11 and xcb development files, and libcrypt
- clisp (it generates the instruction emulator's C code during the build)
- python3 (for `nfs2d.py`; standard library only)
- an X display; XWayland works
- `sudo`, once per boot of the host, to create the network device and
  start the file server

## Building

    autoreconf -fi
    ./configure
    make

The result is `src/genera`. `./configure --help` lists the build
options, and `INSTALL` has the generic instructions. `make distclean`
removes everything generated.

Tested with GCC 16 and autoconf 2.72 on Fedora 44.

## Setting up

1. **Configuration file.** Copy `dot.VLM` to `.VLM`, in your home
   directory or in this directory, and set `genera.world` and
   `genera.debugger` to where you put those two files.
   [`VLM.md`](VLM.md) describes every setting.

2. **Files for Genera.** Build a directory in which the `sys.sct` tree
   appears as `cdrom/sys.sct`, which is where the distribution world
   looks for it:

       mkdir /srv/genera
       ln -s /path/to/opengenera-cd /srv/genera/cdrom

   (`/path/to/opengenera-cd` is the directory that contains `sys.sct`.)
   If you use a directory other than `/srv/genera`, copy
   `dot.run-genera.conf` to `run-genera.conf` and set `NFSROOT`.

3. **Firewall.** If the host has a firewall that drops incoming
   traffic, let Genera's in on the tap device. With ufw:

       sudo ufw allow in on tap0 from 10.0.0.0/24

   Without this Genera boots but asks for the date and cannot read its
   files. The host still answers pings, which makes the cause easy to
   miss.

## Running

    ./run-genera.sh

The script creates the tap network device and starts `nfs2d.py` if they
are not already there, asking for `sudo` only when it has to, and then
starts `genera`. Any arguments are passed on, for example
`./run-genera.sh -world /path/to/My-World.vlod`. `./run-genera.sh -h`
shows its settings.

What to expect:

- Two windows open. The **cold load stream** is Genera's fallback
  console, used during boot and for serious errors. The large one is
  Genera's screen.
- After about a minute the screen shows `Please login.` and a
  `Command:` prompt.
- The notices "This Lisp world has not been configured for use at the
  local site" and "Servers are currently disabled" are normal for the
  distribution world. [`Setup.md`](Setup.md) explains how to define a
  site and save a configured world of your own.

Keys on a PC keyboard:

| Symbolics key | PC key |
|---|---|
| SELECT | F1 |
| ABORT | F6 |
| RESUME | F5 |
| CLEAR INPUT | F9 |
| HELP | Insert |
| META | Alt |

When a Symbolics manual says `SELECT D`, press F1, release it, then
press D.

To leave, type `Halt Genera` at the `Command:` prompt. `genera` does
not exit on SIGTERM; Ctrl-C in its terminal asks for confirmation
instead.

To do the steps by hand rather than with the script:

    sudo ./setup-tap.sh
    sudo ./nfs2d.py --root /srv/genera
    src/genera

## Reading the on-line documentation

Genera carries its complete documentation on line, in the Document
Examiner. In the distribution world, type these two forms at the
`Command:` prompt after each boot:

    (si:login-to-sys-host)
    (fs:set-logical-pathname-host "SYS"
      :translations '(("**;*.*" "dis-emb-host:/cdrom/sys.sct/**/*.*")))

then press F1 and D. Click a title in the list on the right to read it.

Once you have saved a site-configured world ([`Setup.md`](Setup.md))
the two forms are no longer needed.

## Documentation

| File | Contents |
|---|---|
| [`NETWORKING`](NETWORKING) | what the tap device and the NFS and time server are, how they fit together, firewalls, troubleshooting |
| [`Setup.md`](Setup.md) | defining a site and saving your own world |
| [`VLM.md`](VLM.md) | every setting of the `.VLM` configuration file |
| [`Memory.md`](Memory.md) | memory limits, the 40-bit word, how Lisp data is stored |
| [`docs/README`](docs/README) | the Symbolics manuals and the order to read them in |
| [`CLAUDE.md`](CLAUDE.md) | notes for AI coding assistants; also a compact summary of how the system works |

New to Genera? Read *Genera Concepts*, then work through the *Genera
Workbook*, both in `docs/`.

## Changes in this fork

- Builds with current tools: autoconf 2.72, and GCC 15 and later, which
  default to C23.
- `nfs2d.py`: Genera speaks only NFS version 2, which Linux kernels no
  longer serve. This small server replaces the kernel's, and also
  answers Genera's request for the time at boot.
- A fix for current X servers, which reject the keyboard modifier
  mapping Genera asks for; without it Genera's screen never starts.
- `run-genera.sh` and `setup-tap.sh`.
- `make distclean` removes all generated files.
- The documentation listed above, and the manuals in `docs/`.

## Known limitations

- Genera can reach the host and nothing else; it has no route to your
  network or the Internet.
- The site definition procedure in `Setup.md` is taken from the
  Symbolics manuals and has not yet been run end to end here.
- `genera` changes the keyboard modifier map of the whole X display
  (Meta on Alt, Hyper on Menu, NumLock disabled) and does not restore
  it if it is killed.
- Tiling window managers ignore the window geometry settings.

## History and credits

The VLM was written at Symbolics for the DEC Alpha by P. T. Withington,
Scott McKay and Gary Palter, with Paul Robertson of the Dynamic Object
Language Group; see <http://pt.withy.org/publications/VLM.html>. Brad
Parker ported it to x86-64 by changing the Alpha assembler code
generator to produce C. Joachim Jachemich's linux-vlm, the parent of
this repository, built on that work. See `AUTHORS`.

The notes below are from the linux-vlm README and describe what that
version added to Brad Parker's.

**Networking.** It uses a TUN/TAP *tap* device, so `genera` needs no
root privileges once the device exists. A tap device, rather than a
tun device, gives access to the complete Ethernet frame, which a
Chaosnet implementation needs. Tap devices can also be put on a bridge
with different MAC addresses to let several VLM instances talk to each
other over Chaosnet.

**Fixes.**

- *X11 with the xcb library* (it runs with or without xcb). Genera's
  CLX talks the bare X11 protocol directly, and xcb is confused by a
  mixture of Xlib calls and direct protocol access when the display is
  closed or synchronized. That kept the VLM from closing a display
  cleanly, which it does when terminating or saving a world. If xcb is
  detected, a workaround is used for closing displays.
- *Keyboard mapping for the cold load and debugger window.* Control,
  Meta, Super and Hyper work there as they do in Genera.
- *Rational division.* `(/ 3)` yields 1/3 instead of 0. Rational
  division must trap when the remainder is not zero; a new pseudo
  Alpha instruction (`x64ratquo`) generates the code. See
  `alpha-emulator/imacmath.lisp` and `stub/process.lisp`.
- *Double-float exceptions.* `(/ 0.0d0)` now produces a valid trap. See
  `alpha-emulator/imactrap.lisp`.

**Extensions.** These are usable only if the corresponding Lisp
definitions are patched and recompiled as well.

- The block size can be set for `attach-disk-channel`, to use FEP file
  images with blocks other than 2048 words, such as images taken from
  old ESDI disks.
- A link to the Unix `crypt` routine, for modern password hashes.
- The Unix working directory and home directory are placed in the
  embedded communication area.
