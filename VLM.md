# The `.VLM` configuration file

`.VLM` tells the `genera` program which world to load, how much memory
to give it, how it is attached to the network, and how its windows
look. `dot.VLM` in this directory is a sample to copy.

This description is taken from the emulator's source
(`src/utilities.c`, `include/VLM_configuration.h`,
`life-support/network-tap-linux.c`). Settings marked *untested* have not
been tried on this port.

## Where it is read from

`genera` reads up to three files, in this order. All are optional.

1. `/var/lib/symbolics/.VLM`
2. `$HOME/.VLM`
3. `.VLM` in the directory `genera` is started from

A setting in a later file replaces the same setting from an earlier
one, and a command-line option replaces them all. `run-genera.sh`
changes to the repository directory first, so with that script "the
directory genera is started from" is the repository.

## Syntax

The file is in X resource format, one setting per line:

    genera.name: value

- Every setting starts with `genera.`. Lines starting with `minima.` or
  `iverify.` belong to other programs built from this source and are
  ignored.
- Lines starting with `!` or `#` are comments. Blank lines are ignored.
- Names are case-sensitive. Leading spaces in the value are dropped.
- Do not quote values.
- Yes/no settings take exactly `yes` or `no`, in lower case. Anything
  else stops `genera` with an error.

A file that cannot be parsed, or an invalid value, stops `genera` at
startup with a message.

## Summary

| Setting | Command line | Default |
|---|---|---|
| `genera.world` | `-world` | `/var/lib/symbolics/Genera-8-5.vlod` |
| `genera.debugger` | `-debugger` | `/var/lib/symbolics/VLM_debugger` |
| `genera.virtualMemory` | `-vm` | `200` |
| `genera.network` | `-network` | none; required |
| `genera.enableIDS` | `-ids` | `no` |
| `genera.worldSearchPath` | `-searchpath` | `/var/lib/symbolics:/usr/lib/symbolics` |
| `genera.main.*` | see below | |
| `genera.coldLoad.*` | see below | |
| `genera.spy` | `-spy` | `no` |
| `genera.diagnosticHost` | `-diagnostic` | none |
| `genera.testfunction` | `-testfunction` | `no` |

On the command line each option is followed by its value as a separate
word, including the yes/no ones: `genera -ids yes -vm 1024`.

## The world

### `genera.world`

The world file to boot: the saved image of the Lisp system (see
`Setup.md`).

    genera.world: /srv/genera/worlds/Home-Genera-8-5.vlod

The name is used exactly as written. A relative name, or a bare file
name, is looked up from the directory `genera` is started from; there
is no search path for this file. If the file cannot be opened `genera`
stops with "Unable to open world file".

Genera learns the name of its world from this text and uses its
directory as the default for `Save World`. Give an absolute path if you
intend to save worlds.

### `genera.debugger`

The `VLM_debugger` file from the Open Genera distribution. It is a
small Ivory program the emulator loads beside the world. Same path
rules as `genera.world`.

### `genera.virtualMemory`

Size of the emulated machine's virtual memory, in megabytes. A whole
number, at least 125.

    genera.virtualMemory: 2048

This is address space, not memory taken at once: the host commits only
what Genera touches. The default of 200 is small for real use. `genera`
warns at startup when the size is less than twice the size of the
world, because Genera needs working room beyond the loaded image.

The emulator sets no upper limit, but use 10239 or less: from 10240
upward Genera's own count of words overflows. `Memory.md` has the
measurements and explains words and megawords.

### `genera.enableIDS`

`yes` allows Genera to save *incremental* worlds (Incremental Disk
Save): a file holding only the difference from the world that was
booted. `no`, the default, means `Save World` always writes a complete
world. An incremental world cannot be booted without its parent worlds.
*Untested.*

### `genera.worldSearchPath`

Directories, separated by colons, in which the emulator looks for the
parent worlds of an incremental world. It is not used to find
`genera.world` itself.

    genera.worldSearchPath: /srv/genera/worlds:+

A value starting with `+:` or ending with `:+` is added after or before
the path already in effect rather than replacing it. The environment
variable `WORLDPATH` and the command-line option `-searchpath` set the
same thing. *Untested.*

## The network

### `genera.network`

Required. `genera` stops with "At least one network interface must be
defined" without it.

    genera.network: tap0:INTERNET|10.0.0.2;mask=255.255.255.0;gateway=10.0.0.1

The general form is

    device:address;options

**device** is the tap device the emulator opens, which must already
exist (see `NETWORKING`). If it is left out, with its colon, the
environment variable `VLM_TAP` is used, and failing that `tap0`.

**address** is Genera's own address, in one of these forms:

| Form | Meaning |
|---|---|
| `INTERNET\|a.b.c.d` | an IP address |
| a host name | looked up on the Linux host; must not be `localhost` |
| `CHAOS\|nnn` | a Chaosnet address, in octal (*untested*) |
| `MAC\|aa:bb:cc:dd:ee:ff` | the Ethernet address Genera uses on this device (*untested*) |

**options** follow a semicolon and are separated by semicolons:

| Option | Meaning |
|---|---|
| `mask=a.b.c.d` | the subnet mask; handed to Genera |
| `gateway=a.b.c.d` | the default gateway; handed to Genera |
| `host=a.b.c.d` | the Linux host's address on this network |

The host's address matters because Genera reaches its files and the
time through it (Genera calls it DIS-EMB-HOST). Without `host=` the
emulator assumes **host number 1 on Genera's own /24 network**: for
Genera at 10.0.0.2 that is 10.0.0.1. `gateway=` does not change this.
If your tap device carries a different address, say so with `host=`.

Several entries may be given, separated by commas, to define up to 8
interfaces, or more than one address on the same device (*untested*):

    genera.network: tap0:INTERNET|10.0.0.2;mask=255.255.255.0,tap0:CHAOS|401

## The windows

Genera has two windows (see `NETWORKING` and `CLAUDE.md`): the main
screen and the cold load stream. Each has the same set of settings,
under `genera.main.` and `genera.coldLoad.`.

| Setting | Main window option | Cold load option |
|---|---|---|
| `display` | `-display` | `-coldloaddisplay`, `-cld` |
| `geometry` | `-geometry` | `-coldloadgeometry`, `-clg` |
| `iconic` | `-iconic` | `-coldloadiconic`, `-cli` |
| `foreground` | `-foreground`, `-fg` | `-coldloadforeground`, `-clfg` |
| `background` | `-background`, `-bg` | `-coldloadbackground`, `-clbg` |
| `borderColor` | `-bordercolor`, `-bd` | `-coldloadbordercolor`, `-clbd` |
| `borderWidth` | `-borderwidth`, `-bw` | `-coldloadborderwidth`, `-clbw` |

- **display** — the X display, as `host:display.screen`. The default is
  the `DISPLAY` environment variable, or `:0.0` if that is not set.
  A line `genera*display: value` sets both windows at once.
- **geometry** — size and position in the usual X form,
  `WIDTHxHEIGHT+X+Y`. For the main window the units are pixels; without
  it Genera sizes its screen to the whole display. For the cold load
  window the units are characters (columns x rows, 8 by 12 pixels
  each), and without it the window is 800 by 800 pixels (*untested*).
- **iconic** — `yes` starts the window as an icon, `no` as a normal
  window. The cold load window defaults to `yes`.
- **foreground**, **background**, **borderColor** — X color names. The
  background defaults to `white`.
- **borderWidth** — a whole number of pixels.

These are requests to the window manager. A tiling window manager
(sway, i3) places and sizes windows itself and ignores geometry and
position; many managers ignore `iconic` and the border settings too.
Apart from the main window's display, none of these has been seen to
take effect on this port.

## Debugging settings

These are for people working on the emulator. Leave them out.

- **`genera.spy`** — `yes` starts the "spy", a remote-debugging service
  inside the emulator that answers on the network. With it on, `genera`
  keeps running after Genera halts.
- **`genera.diagnosticHost`** — the host the spy talks to. Used only
  when the spy is on; defaults to Genera's own address.
- **`genera.testfunction`** — `yes` runs a different built-in test in
  place of the usual power-on self-test before the world starts.
- **`genera.trace`**, **`genera.tracePOST`** — instruction tracing.
  Recognized only if the emulator is compiled with `TRACING`, which the
  normal build does not do.

## Environment variables

| Variable | Effect |
|---|---|
| `DISPLAY` | default X display for both windows |
| `WORLDPATH` | default for the world search path |
| `VLM_TAP` | tap device, when the network setting names none |

## A complete example

    ! Genera at 10.0.0.2, Linux host at 10.0.0.1 on tap0
    genera.network: tap0:INTERNET|10.0.0.2;mask=255.255.255.0;gateway=10.0.0.1

    genera.world: /srv/genera/worlds/Home-Genera-8-5.vlod
    genera.debugger: /srv/genera/worlds/VLM_debugger
    genera.virtualMemory: 2048

    genera.main.geometry: 1200x900
