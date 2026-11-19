# Configuring a site and saving your own world

The world on the Open Genera CD is the *distribution* world. It belongs
to a placeholder site called DISTRIBUTION and says so at every boot:

> This Lisp world has not been configured for use at the local site.

It is usable as it is, but it forgets everything between sessions: the
two forms that locate `sys.sct` must be typed after every boot, the
clock assumes US Eastern time, and there are no users.

The cure is to **define a site** (a small database describing your
machines, kept in files on the host) and then **save a world** that
already belongs to it. You do this once. Afterwards Genera boots
configured.

> **Status.** These steps are taken from the Open Genera quick-start
> notes and Installation Guide and adapted to this emulator and
> `nfs2d.py`. The host-side steps have been tested. The steps inside
> Genera have **not yet been run end to end on this emulator**; in
> particular Genera writing files through `nfs2d.py` is untested.
> Nothing here changes the distribution world file, so a failed attempt
> costs nothing: quit Genera and start again.

Before starting, Genera must already boot and show documentation as
described in `README.md` and `NETWORKING`.

## Names used in this example

Choose your own; these are used below.

| What | Example | Notes |
|---|---|---|
| Site name | `HOME` | any short name |
| Genera's host name | `GENERA` | the Lisp machine, 10.0.0.2 |
| Linux host's name | `GENERA-HOST` | the host, 10.0.0.1 |
| Time zone | `CST` | a US-style abbreviation |
| NFS export directory | `/srv/genera` | what `nfs2d.py --root` serves |
| New world file | `/srv/genera/worlds/Home-Genera-8-5.vlod` | any directory you can write |

## Two kinds of host path

Inside Genera, files on the Linux machine are written `HOST:/...`.
There are two cases, and they do not agree:

- **Ordinary files** are read and written over NFS. The path is
  relative to the NFS export directory: `HOST:/cdrom/sys.sct/` is
  `/srv/genera/cdrom/sys.sct/` on Linux.
- **World files** are read and written by the emulator itself, not over
  NFS. The path is the real Linux path:
  `HOST:/srv/genera/worlds/Home-Genera-8-5.vlod` is exactly that file.

## Keys

| Symbolics key | PC keyboard |
|---|---|
| RETURN | Enter |
| END | End (if that does nothing, try keypad Enter) |
| ABORT | F6 |
| HELP | Insert |
| CLEAR INPUT | F9 |
| SELECT | F1 |

The command `Show X Keyboard Mapping` in Genera lists every key.

## Part 1: prepare the host

1. Create the directory for the site files, inside the NFS export. The
   path below is the default Genera proposes, so you can accept its
   suggestions later.

   ```
   mkdir -p /srv/genera/var/lib/symbolics/sys.sct/site
   mkdir -p /srv/genera/worlds
   ```

2. Protect your copy of `sys.sct`. The server is about to become
   writable, and Genera should not be able to alter the system tree.

   ```
   chmod -R a-w /path/to/opengenera-cd/sys.sct
   ```

3. Make the NFS server writable. In `run-genera.conf` set

   ```
   NFSRW=yes
   ```

   then quit Genera if it is running and restart the server:

   ```
   sudo systemctl stop genera-nfs2d
   ./run-genera.sh
   ```

   (If you start the server by hand, add `--rw` to the `nfs2d.py`
   command instead.)

4. Optional: add the two names to `/etc/hosts` so the host knows them
   too.

   ```
   10.0.0.1  genera-host
   10.0.0.2  genera
   ```

## Part 2: define the site

Genera is now running the distribution world.

5. At the `Command:` prompt, log in:

   ```
   (si:login-to-sys-host)
   ```

6. Type the command below and press Enter. (A leading colon tells
   Genera that this is a command, not Lisp.)

   ```
   :Define Site HOME
   ```

   A form appears in place with one field, *Namespace Server Name*.
   Click left on the italic text, type `GENERA` and press Enter. The
   rest of the form appears:

   | Field | Enter |
   |---|---|
   | Namespace Server Name | `GENERA` |
   | System File Directory | `HOST:/var/lib/symbolics/sys.sct/site/` (the default) |
   | Namespace Descriptor File | `HOST:/var/lib/symbolics/sys.sct/site/home-namespace.text` (the default) |
   | Unix Host Name | `GENERA-HOST` |
   | Default Login | leave as it is |
   | Host for Bug Reports | leave as it is |
   | Local Timezone | `CST` |
   | Standalone Site | `Yes` |

   To change a field, click left on it (click middle to edit the
   existing value), type, and press Enter. When all fields are right,
   press END. Genera writes the site files and switches to the new
   site.

   On the host you should now see files in
   `/srv/genera/var/lib/symbolics/sys.sct/site/`.

7. Copy the site files from the CD into your site directory. They
   include `sys.translations`, which tells Genera that `sys.sct` is at
   `/cdrom/sys.sct` on the host, and the definitions of the loadable
   systems.

   ```
   Copy File host:/cdrom/sys.sct/site/* sys:site;
   ```

8. Shut Genera down:

   ```
   Halt Genera
   ```

## Part 3: save a world that belongs to the site

9. Start Genera again (`./run-genera.sh`). It is the distribution world
   again; the site lives only in the files so far.

10. Log in and switch to the site you defined:

    ```
    (si:login-to-sys-host)
    :Set Site HOME
    ```

    The form asks for these, one after another:

    | Field | Enter |
    |---|---|
    | Namespace Server Name | `GENERA` |
    | Namespace Server Address | `INTERNET 10.0.0.2` |
    | Namespace Descriptor File | `HOST:/var/lib/symbolics/sys.sct/site/home-namespace.text` |
    | Real Name of Unix Host | `GENERA-HOST` |

    Press END. Genera reloads the namespace and is now host `GENERA` at
    site `HOME`.

11. Check that the site works before saving. Press F1 then D, and open
    a document. This time you did not type the `SYS` translation form:
    it came from `sys.translations`. Return with F1 then L.

12. Save the world. Type `Save World`, a space, and the file name, then
    Enter:

    ```
    Save World HOST:/srv/genera/worlds/Home-Genera-8-5.vlod
    ```

    This is a real Linux path (see "Two kinds of host path"). If Genera
    asks whether to save an incremental world, answer no; a full world
    is one self-contained file of roughly the size of the original
    (55 megabytes). When it finishes Genera prints

    > You must update your ivory config file to use this world

13. Shut down with `Halt Genera`.

## Part 4: use the new world

14. In `.VLM`, point `genera.world` at the new file:

    ```
    genera.world: /srv/genera/worlds/Home-Genera-8-5.vlod
    ```

    Keep the old line as a comment. The distribution world is your way
    back if the new one misbehaves.

15. Start Genera. The "not been configured" notice is gone, the herald
    names your site and host, and the documentation works with nothing
    typed.

16. Log in under a name of your own:

    ```
    Login yourname
    ```

    The first time, Genera does not know the name and offers to create
    the user; accept, and it is recorded in the site files.

## Afterwards

- The server must stay writable (`NFSRW=yes`) if you want Genera to go
  on recording changes to the site, such as new users, or to save your
  own files on the host. If you only read, you can set it back to `no`.
- The site files in `.../sys.sct/site/` and the saved world belong
  together. Back them up together.
- To add software to your world (CLIM, for example), boot the site
  world, load the system, and `Save World` to a new file name. See
  `docs/Site_Operations.pdf` and
  `docs/Open_Genera_Installation_Guide.pdf`.

## If something goes wrong

- **A step in Genera fails or you are unsure of the state:** press
  ABORT (F6), or quit and start again. Until step 14 you are always
  booting the untouched distribution world.
- **To start over completely:** delete the files in
  `/srv/genera/var/lib/symbolics/sys.sct/site/` and begin again at
  step 5.
- **Genera reports a read-only file system or cannot write:** the
  server was not restarted with `NFSRW=yes`, or the site directory is
  not writable by your user. Watch what Genera asks for with
  `journalctl -u genera-nfs2d -f` (start the server with `-v` to see
  every request).
- **Save World fails:** the directory must exist and be writable by the
  user running `genera`, and the name must be the real Linux path.
- **The new world asks for the date:** see `NETWORKING`, section 4.
