#!/usr/bin/env python3
"""nfs2d - a small user-space NFS version 2 server for Genera.

Genera reads the host's files (the sys.sct tree in particular) over NFS
version 2 on UDP.  Current Linux kernels no longer serve version 2, so
this program does: it answers the portmapper, mount and NFS version 2
protocols itself and needs neither rpcbind nor the kernel NFS server.

    sudo ./nfs2d.py --root /path/to/tree [--bind 10.0.0.1] [--rw] [-v]

The directory given with --root appears to Genera as "/".  Symbolic
links inside it are followed on the server, so Genera only ever sees
plain files and directories; that makes it easy to assemble the tree
Genera expects, for example

    mkdir -p /srv/genera
    ln -s /path/to/opengenera-cd /srv/genera/cdrom

which makes /cdrom/sys.sct visible.

It also answers the time protocol (RFC 868, port 37).  Genera asks the
host for the time when it boots; if nobody answers it asks the user,
and on this emulator that ends in "Unable to set calendar clock".

Root is needed only to bind the portmapper and time ports (111, 37).  Once the
sockets are open the server drops to the user who invoked sudo (or
--user) and all files are accessed as that user.  It listens only on
the --bind address, which should be the host's address on the tap
device.  Without --rw every modifying request is refused.
"""

import argparse
import errno
import fcntl
import os
import pwd
import secrets
import selectors
import socket
import stat
import struct
import sys
import time

PMAP_PROG, NFS_PROG, MOUNT_PROG = 100000, 100003, 100005
IPPROTO_TCP, IPPROTO_UDP = 6, 17

NFS_OK, NFSERR_NOENT, NFSERR_IO, NFSERR_ACCES = 0, 2, 5, 13
NFSERR_EXIST, NFSERR_NOTDIR, NFSERR_ISDIR, NFSERR_FBIG = 17, 20, 21, 27
NFSERR_NOSPC, NFSERR_ROFS, NFSERR_NAMETOOLONG = 28, 30, 63
NFSERR_NOTEMPTY, NFSERR_STALE = 66, 70

ERRNO_MAP = {
    errno.ENOENT: NFSERR_NOENT, errno.EACCES: NFSERR_ACCES,
    errno.EPERM: NFSERR_ACCES, errno.EEXIST: NFSERR_EXIST,
    errno.ENOTDIR: NFSERR_NOTDIR, errno.EISDIR: NFSERR_ISDIR,
    errno.EFBIG: NFSERR_FBIG, errno.ENOSPC: NFSERR_NOSPC,
    errno.EROFS: NFSERR_ROFS, errno.ENAMETOOLONG: NFSERR_NAMETOOLONG,
    errno.ENOTEMPTY: NFSERR_NOTEMPTY,
}

NFS_PROCS = ["NULL", "GETATTR", "SETATTR", "ROOT", "LOOKUP", "READLINK",
             "READ", "WRITECACHE", "WRITE", "CREATE", "REMOVE", "RENAME",
             "LINK", "SYMLINK", "MKDIR", "RMDIR", "READDIR", "STATFS"]
MOUNT_PROCS = ["NULL", "MNT", "DUMP", "UMNT", "UMNTALL", "EXPORT"]
MODIFYING = {"SETATTR", "WRITE", "CREATE", "REMOVE", "RENAME", "LINK",
             "SYMLINK", "MKDIR", "RMDIR"}

UNSET = 0xFFFFFFFF
FHSIZE = 32


class NFSError(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.status = status


class BadCall(Exception):
    """The request could not be decoded."""


def p32(*values):
    return struct.pack(">%dI" % len(values), *[v & 0xFFFFFFFF for v in values])


def popaque(data):
    return p32(len(data)) + data + b"\0" * (-len(data) % 4)


class Unpacker:
    def __init__(self, data, pos=0):
        self.data, self.pos = data, pos

    def u32(self):
        if self.pos + 4 > len(self.data):
            raise BadCall
        (value,) = struct.unpack_from(">I", self.data, self.pos)
        self.pos += 4
        return value

    def fixed(self, n):
        if self.pos + n > len(self.data):
            raise BadCall
        value = self.data[self.pos:self.pos + n]
        self.pos += n + (-n % 4)
        return value

    def opaque(self):
        return self.fixed(self.u32())

    def string(self):
        return self.opaque().decode("latin-1")


class Handles:
    """Maps the 32-byte NFS file handles to paths relative to the root.

    Handles do not survive a restart of the server; a client holding old
    ones gets NFSERR_STALE and has to look the files up again.
    """

    def __init__(self):
        self.nonce = secrets.token_bytes(8)
        self.by_id = {1: ""}
        self.by_path = {"": 1}
        self.next_id = 2

    def make(self, rel):
        ident = self.by_path.get(rel)
        if ident is None:
            ident = self.next_id
            self.next_id += 1
            self.by_path[rel] = ident
            self.by_id[ident] = rel
        return self.nonce + struct.pack(">Q", ident) + b"\0" * (FHSIZE - 16)

    def path(self, handle):
        if len(handle) != FHSIZE or handle[:8] != self.nonce:
            raise NFSError(NFSERR_STALE)
        (ident,) = struct.unpack_from(">Q", handle, 8)
        rel = self.by_id.get(ident)
        if rel is None:
            raise NFSError(NFSERR_STALE)
        return rel

    def forget(self, rel):
        for path in [p for p in self.by_path if p == rel or p.startswith(rel + "/")]:
            del self.by_id[self.by_path.pop(path)]

    def rename(self, old, new):
        self.forget(new)
        for path in [p for p in self.by_path if p == old or p.startswith(old + "/")]:
            ident = self.by_path.pop(path)
            moved = new + path[len(old):]
            self.by_path[moved] = ident
            self.by_id[ident] = moved


class Server:
    def __init__(self, root, writable, verbose, nfs_port, pmap_port, tcp):
        self.root = os.path.realpath(root)
        self.writable = writable
        self.verbose = verbose
        self.nfs_port = nfs_port
        self.pmap_port = pmap_port
        self.tcp = tcp
        self.handles = Handles()
        self.dir_cache = {}
        self.replies = {}           # duplicate request cache
        self.unknown = set()

    # ---- helpers -------------------------------------------------------

    def log(self, client, text, always=False):
        if always or self.verbose:
            print("%s %s %s" % (time.strftime("%H:%M:%S"), client[0], text),
                  flush=True)

    def real(self, rel):
        return os.path.join(self.root, rel) if rel else self.root

    @staticmethod
    def child(rel, name):
        if name in ("", "."):
            return rel
        if name == "..":
            return rel.rpartition("/")[0]
        if "/" in name or "\0" in name:
            raise NFSError(NFSERR_NOENT)
        return rel + "/" + name if rel else name

    @staticmethod
    def fattr(st):
        if stat.S_ISREG(st.st_mode):
            ftype = 1
        elif stat.S_ISDIR(st.st_mode):
            ftype = 2
        else:
            ftype = 0
        def when(t):
            return int(t), int((t - int(t)) * 1000000)
        return p32(ftype, st.st_mode, st.st_nlink, st.st_uid, st.st_gid,
                   min(st.st_size, 0x7FFFFFFF), 4096, 0,
                   min(st.st_blocks, 0xFFFFFFFF), 1, st.st_ino,
                   *when(st.st_atime), *when(st.st_mtime), *when(st.st_ctime))

    def attrstat(self, rel):
        return p32(NFS_OK) + self.fattr(os.stat(self.real(rel)))

    def diropres(self, rel):
        st = os.stat(self.real(rel))
        return p32(NFS_OK) + self.handles.make(rel) + self.fattr(st)

    def diropargs(self, u):
        rel = self.handles.path(u.fixed(FHSIZE))
        name = u.string()
        return rel, name

    @staticmethod
    def sattr(u):
        mode, uid, gid, size = u.u32(), u.u32(), u.u32(), u.u32()
        atime = (u.u32(), u.u32())
        mtime = (u.u32(), u.u32())
        return mode, uid, gid, size, atime, mtime

    def apply_sattr(self, path, sattr, skip_size=False):
        mode, _uid, _gid, size, atime, mtime = sattr
        if mode != UNSET:
            os.chmod(path, mode & 0o7777)
        if size != UNSET and not skip_size:
            os.truncate(path, size)
        if atime[0] != UNSET or mtime[0] != UNSET:
            st = os.stat(path)
            a = atime[0] + atime[1] / 1e6 if atime[0] != UNSET else st.st_atime
            m = mtime[0] + mtime[1] / 1e6 if mtime[0] != UNSET else st.st_mtime
            os.utime(path, (a, m))

    def listing(self, rel):
        path = self.real(rel)
        mtime = os.stat(path).st_mtime_ns
        cached = self.dir_cache.get(rel)
        if cached and cached[0] == mtime:
            return cached[1]
        entries = [(".", os.stat(path).st_ino),
                   ("..", os.stat(self.real(self.child(rel, ".."))).st_ino)]
        with os.scandir(path) as it:
            for entry in sorted(it, key=lambda e: e.name):
                try:
                    ino = (os.stat(entry.path).st_ino if entry.is_symlink()
                           else entry.inode())
                except OSError:
                    continue        # dangling symbolic link
                entries.append((entry.name, ino))
        if len(self.dir_cache) > 256:
            self.dir_cache.clear()
        self.dir_cache[rel] = (mtime, entries)
        return entries

    # ---- NFS version 2 -------------------------------------------------

    def nfs(self, proc, u, client):
        name = NFS_PROCS[proc]
        if name in ("NULL", "ROOT", "WRITECACHE"):
            return b""
        if name in MODIFYING and not self.writable:
            self.log(client, "%s refused: server is read-only" % name)
            return p32(NFSERR_ROFS)
        try:
            return getattr(self, "nfs_" + name)(u, client)
        except NFSError as e:
            self.log(client, "%s -> error %d" % (name, e.status))
            return p32(e.status)
        except OSError as e:
            self.log(client, "%s -> %s" % (name, e.strerror))
            return p32(ERRNO_MAP.get(e.errno, NFSERR_IO))

    def nfs_GETATTR(self, u, client):
        rel = self.handles.path(u.fixed(FHSIZE))
        self.log(client, "GETATTR /%s" % rel)
        return self.attrstat(rel)

    def nfs_SETATTR(self, u, client):
        rel = self.handles.path(u.fixed(FHSIZE))
        self.log(client, "SETATTR /%s" % rel)
        self.apply_sattr(self.real(rel), self.sattr(u))
        return self.attrstat(rel)

    def nfs_LOOKUP(self, u, client):
        rel, name = self.diropargs(u)
        self.log(client, "LOOKUP /%s %s" % (rel, name))
        return self.diropres(self.child(rel, name))

    def nfs_READLINK(self, u, client):
        raise NFSError(NFSERR_IO)   # links are followed by the server

    def nfs_READ(self, u, client):
        rel = self.handles.path(u.fixed(FHSIZE))
        offset, count = u.u32(), u.u32()
        self.log(client, "READ /%s %d+%d" % (rel, offset, count))
        fd = os.open(self.real(rel), os.O_RDONLY)
        try:
            data = os.pread(fd, min(count, 8192), offset)
            st = os.fstat(fd)
        finally:
            os.close(fd)
        return p32(NFS_OK) + self.fattr(st) + popaque(data)

    def nfs_WRITE(self, u, client):
        rel = self.handles.path(u.fixed(FHSIZE))
        _begin, offset, _total = u.u32(), u.u32(), u.u32()
        data = u.opaque()
        self.log(client, "WRITE /%s %d+%d" % (rel, offset, len(data)))
        fd = os.open(self.real(rel), os.O_WRONLY)
        try:
            os.pwrite(fd, data, offset)
        finally:
            os.close(fd)
        return self.attrstat(rel)

    def nfs_CREATE(self, u, client):
        rel, name = self.diropargs(u)
        sattr = self.sattr(u)
        new = self.child(rel, name)
        self.log(client, "CREATE /%s" % new)
        mode = sattr[0] & 0o7777 if sattr[0] != UNSET else 0o644
        flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if sattr[3] == 0 else 0)
        os.close(os.open(self.real(new), flags, mode))
        self.apply_sattr(self.real(new), (UNSET,) + sattr[1:], skip_size=True)
        return self.diropres(new)

    def nfs_REMOVE(self, u, client):
        rel, name = self.diropargs(u)
        target = self.child(rel, name)
        self.log(client, "REMOVE /%s" % target)
        os.unlink(self.real(target))
        self.handles.forget(target)
        return p32(NFS_OK)

    def nfs_RENAME(self, u, client):
        old = self.child(*self.diropargs(u))
        new = self.child(*self.diropargs(u))
        self.log(client, "RENAME /%s /%s" % (old, new))
        os.rename(self.real(old), self.real(new))
        self.handles.rename(old, new)
        return p32(NFS_OK)

    def nfs_LINK(self, u, client):
        raise NFSError(NFSERR_ACCES)

    def nfs_SYMLINK(self, u, client):
        raise NFSError(NFSERR_ACCES)

    def nfs_MKDIR(self, u, client):
        rel, name = self.diropargs(u)
        sattr = self.sattr(u)
        new = self.child(rel, name)
        self.log(client, "MKDIR /%s" % new)
        os.mkdir(self.real(new),
                 sattr[0] & 0o7777 if sattr[0] != UNSET else 0o755)
        return self.diropres(new)

    def nfs_RMDIR(self, u, client):
        rel, name = self.diropargs(u)
        target = self.child(rel, name)
        self.log(client, "RMDIR /%s" % target)
        os.rmdir(self.real(target))
        self.handles.forget(target)
        return p32(NFS_OK)

    def nfs_READDIR(self, u, client):
        rel = self.handles.path(u.fixed(FHSIZE))
        cookie, count = u.u32(), u.u32()
        self.log(client, "READDIR /%s from %d" % (rel, cookie))
        entries = self.listing(rel)
        out = [p32(NFS_OK)]
        size = 16
        index = cookie
        while index < len(entries):
            name, ino = entries[index]
            item = p32(1, ino) + popaque(name.encode("latin-1", "replace")) \
                + p32(index + 1)
            if size + len(item) > max(count, 512):
                break
            out.append(item)
            size += len(item)
            index += 1
        out.append(p32(0, 1 if index >= len(entries) else 0))
        return b"".join(out)

    def nfs_STATFS(self, u, client):
        rel = self.handles.path(u.fixed(FHSIZE))
        self.log(client, "STATFS /%s" % rel)
        vfs = os.statvfs(self.real(rel))
        clamp = lambda n: min(n, 0x7FFFFFFF)
        return p32(NFS_OK, 8192, clamp(vfs.f_frsize), clamp(vfs.f_blocks),
                   clamp(vfs.f_bfree), clamp(vfs.f_bavail))

    # ---- mount version 1 -----------------------------------------------

    def mount(self, proc, u, client):
        name = MOUNT_PROCS[proc]
        if name == "MNT":
            wanted = u.string()
            rel = ""
            for part in wanted.split("/"):
                rel = self.child(rel, part) if "\0" not in part else rel
            try:
                if not stat.S_ISDIR(os.stat(self.real(rel)).st_mode):
                    raise NotADirectoryError(errno.ENOTDIR, "Not a directory")
            except OSError as e:
                self.log(client, "MNT %s refused: %s" % (wanted, e.strerror),
                         always=True)
                return p32(e.errno or errno.EIO)
            self.log(client, "MNT %s" % wanted, always=True)
            return p32(0) + self.handles.make(rel)
        if name == "DUMP":
            return p32(0)
        if name == "EXPORT":
            self.log(client, "EXPORT")
            return p32(1) + popaque(b"/") + p32(0) + p32(0)
        self.log(client, name)
        return b""                  # NULL, UMNT, UMNTALL

    # ---- portmapper version 2 ------------------------------------------

    def portmap(self, proc, u, client):
        services = [(PMAP_PROG, 2, self.pmap_port), (MOUNT_PROG, 1, self.nfs_port),
                    (NFS_PROG, 2, self.nfs_port)]
        protocols = [IPPROTO_UDP] + ([IPPROTO_TCP] if self.tcp else [])
        if proc == 0:
            return b""
        if proc == 3:               # GETPORT
            prog, vers, prot = u.u32(), u.u32(), u.u32()
            port = 0
            for sprog, _svers, sport in services:
                if sprog == prog and prot in protocols:
                    port = sport
            if port == 0 and (prog, prot) not in self.unknown:
                self.unknown.add((prog, prot))
                self.log(client, "GETPORT for program %d version %d protocol "
                         "%d: not served" % (prog, vers, prot), always=True)
            return p32(port)
        if proc == 4:               # DUMP
            out = b""
            for sprog, svers, sport in services:
                for prot in protocols:
                    out += p32(1, sprog, svers, prot, sport)
            return out + p32(0)
        if proc in (1, 2):          # SET, UNSET: not allowed
            return p32(0)
        return None

    # ---- RPC -----------------------------------------------------------

    def handle(self, data, client):
        """Returns the reply to one RPC call, or None to stay silent."""
        try:
            u = Unpacker(data)
            xid, mtype = u.u32(), u.u32()
            if mtype != 0:
                return None
            rpcvers, prog, vers, proc = u.u32(), u.u32(), u.u32(), u.u32()
            u.u32(); u.opaque()     # credentials (ignored)
            u.u32(); u.opaque()     # verifier
        except BadCall:
            return None
        if rpcvers != 2:
            return p32(xid, 1, 1, 0, 2, 2)      # denied: RPC mismatch
        accepted = p32(xid, 1, 0, 0, 0)

        key = (client, xid, prog, proc)
        if key in self.replies:
            return self.replies[key]

        table = {PMAP_PROG: (2, 5, self.portmap),
                 MOUNT_PROG: (1, len(MOUNT_PROCS) - 1, self.mount),
                 NFS_PROG: (2, len(NFS_PROCS) - 1, self.nfs)}.get(prog)
        if table is None:
            if prog not in self.unknown:
                self.unknown.add(prog)
                self.log(client, "call to program %d, which is not served"
                         % prog, always=True)
            return accepted + p32(1)            # PROG_UNAVAIL
        version, maxproc, function = table
        # the mount program is asked for by several version numbers; all
        # of them share the procedures used here
        if vers != version and prog != MOUNT_PROG:
            return accepted + p32(2, version, version)   # PROG_MISMATCH
        if proc > maxproc:
            return accepted + p32(3)            # PROC_UNAVAIL
        try:
            result = function(proc, u, client)
        except BadCall:
            return accepted + p32(4)            # GARBAGE_ARGS
        if result is None:
            return accepted + p32(3)
        reply = accepted + p32(0) + result
        if prog == NFS_PROG and NFS_PROCS[proc] in MODIFYING:
            if len(self.replies) > 256:
                self.replies.clear()
            self.replies[key] = reply
        return reply


def interface_of(address):
    """Name of the network interface that carries the given address."""
    wanted = socket.inet_aton(address)
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for _index, name in socket.if_nameindex():
            request = struct.pack("256s", name.encode()[:15])
            try:        # SIOCGIFADDR
                reply = fcntl.ioctl(probe.fileno(), 0x8915, request)
            except OSError:
                continue
            if reply[20:24] == wanted:
                return name
    finally:
        probe.close()
    return None


def rfc868_time():
    """Seconds since 1900-01-01 00:00 UTC, as the time protocol sends it."""
    return p32(int(time.time()) + 2208988800)


def serve(server, bind, time_port):
    selector = selectors.DefaultSelector()
    buffers = {}

    if time_port:
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp.bind((bind, time_port))
        selector.register(udp, selectors.EVENT_READ, "time-udp")
        time_reply_socket = udp
        # Genera asks for the time by broadcast, which a socket bound to
        # the host's own address never sees.  Listen for those on the
        # interface that carries the address, and answer from the address.
        device = interface_of(bind)
        if device:
            try:
                extra = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                extra.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                extra.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE,
                                 device.encode())
                extra.bind(("", time_port))
                selector.register(extra, selectors.EVENT_READ, "time-udp")
            except OSError as e:
                print("nfs2d: not listening for time broadcasts on %s: %s"
                      % (device, e.strerror), flush=True)
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.bind((bind, time_port))
        tcp.listen(8)
        selector.register(tcp, selectors.EVENT_READ, "time-listen")

    for port in sorted({server.pmap_port, server.nfs_port}):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind((bind, port))
        selector.register(udp, selectors.EVENT_READ, "udp")
        if server.tcp:
            tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            tcp.bind((bind, port))
            tcp.listen(8)
            selector.register(tcp, selectors.EVENT_READ, "listen")
    yield                           # sockets are bound; caller drops root

    while True:
        for key, _events in selector.select():
            sock, kind = key.fileobj, key.data
            if kind == "time-udp":
                try:
                    _data, client = sock.recvfrom(1024)
                    server.log(client, "TIME (udp)", always=True)
                    time_reply_socket.sendto(rfc868_time(), client)
                except OSError as e:
                    print("nfs2d: time reply failed: %s" % e, flush=True)
            elif kind == "time-listen":
                try:
                    conn, client = sock.accept()
                    conn.sendall(rfc868_time())
                    conn.close()
                    server.log(client, "TIME (tcp)", always=True)
                except OSError:
                    pass
            elif kind == "udp":
                try:
                    data, client = sock.recvfrom(65536)
                except OSError:
                    continue
                reply = server.handle(data, client)
                if reply is not None:
                    try:
                        sock.sendto(reply, client)
                    except OSError as e:
                        server.log(client, "send failed: %s" % e, always=True)
            elif kind == "listen":
                conn, client = sock.accept()
                buffers[conn] = (b"", b"", client)
                selector.register(conn, selectors.EVENT_READ, "tcp")
            else:
                pending, record, client = buffers[sock]
                try:
                    chunk = sock.recv(65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    selector.unregister(sock)
                    sock.close()
                    del buffers[sock]
                    continue
                pending += chunk
                while len(pending) >= 4:
                    (mark,) = struct.unpack_from(">I", pending)
                    length = mark & 0x7FFFFFFF
                    if len(pending) < 4 + length:
                        break
                    record += pending[4:4 + length]
                    pending = pending[4 + length:]
                    if mark & 0x80000000:
                        reply = server.handle(record, client)
                        record = b""
                        if reply is not None:
                            try:
                                sock.sendall(p32(0x80000000 | len(reply)) + reply)
                            except OSError:
                                pass
                buffers[sock] = (pending, record, client)


def drop_privileges(user):
    if os.geteuid() != 0:
        return
    if user is None and os.environ.get("SUDO_UID"):
        entry = pwd.getpwuid(int(os.environ["SUDO_UID"]))
    elif user is not None:
        entry = pwd.getpwnam(user)
    else:
        entry = None
    if entry is None or entry.pw_uid == 0:
        sys.exit("nfs2d: will not serve files as root; "
                 "run it through sudo or give --user")
    os.setgroups(os.getgrouplist(entry.pw_name, entry.pw_gid))
    os.setgid(entry.pw_gid)
    os.setuid(entry.pw_uid)


def main():
    parser = argparse.ArgumentParser(
        description="User-space NFS version 2 server for Genera.")
    parser.add_argument("--root", required=True,
                        help="directory Genera sees as /")
    parser.add_argument("--bind", default="10.0.0.1",
                        help="address to listen on (default: %(default)s)")
    parser.add_argument("--rw", action="store_true",
                        help="allow Genera to modify files (default: read-only)")
    parser.add_argument("--user",
                        help="user to serve files as when started as root "
                             "(default: the user who invoked sudo)")
    parser.add_argument("--nfs-port", type=int, default=2049)
    parser.add_argument("--portmap-port", type=int, default=111)
    parser.add_argument("--time-port", type=int, default=37,
                        help="port for the time protocol; 0 disables it "
                             "(default: %(default)s)")
    parser.add_argument("--no-tcp", action="store_true",
                        help="serve UDP only")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="log every request")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        sys.exit("nfs2d: %s is not a directory" % args.root)
    server = Server(args.root, args.rw, args.verbose, args.nfs_port,
                    args.portmap_port, not args.no_tcp)
    loop = serve(server, args.bind, args.time_port)
    try:
        next(loop)
    except OSError as e:
        sys.exit("nfs2d: cannot listen on %s: %s" % (args.bind, e.strerror))
    drop_privileges(args.user)
    print("nfs2d: serving %s %s on %s as uid %d" % (
        server.root, "read-write" if args.rw else "read-only", args.bind,
        os.getuid()), flush=True)
    try:
        next(loop)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
