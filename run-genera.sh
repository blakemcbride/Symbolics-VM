#!/bin/bash
# Start Genera, first bringing up what it needs if it is not already there:
#
#   - the tap network device          (setup-tap.sh)
#   - the NFS v2 and time server      (nfs2d.py)
#
# sudo is used only for those two steps, and only when they are needed.
# Any arguments are passed on to genera.
#
# Settings may be overridden in the environment or in a file named
# run-genera.conf next to this script; dot.run-genera.conf is a sample:
#
#   NFSROOT   directory nfs2d.py exports     (default /srv/genera)
#   NFSRW     yes lets Genera write there    (default no, read-only)
#   TAPDEV    tap device                     (default tap0)
#   HOSTADDR  host's address on that device  (default 10.0.0.1)
#   PREFIX    its prefix length              (default 24)

set -e
cd "$(dirname "$0")"
HERE=$(pwd)

[ -f run-genera.conf ] && . ./run-genera.conf
NFSROOT=${NFSROOT:-/srv/genera}
TAPDEV=${TAPDEV:-tap0}
HOSTADDR=${HOSTADDR:-10.0.0.1}
PREFIX=${PREFIX:-24}
RW=
[ "${NFSRW:-no}" = yes ] && RW=--rw
UNIT=genera-nfs2d

if [ ! -x src/genera ]; then
    echo "$0: src/genera not found; build it first (see README)" >&2
    exit 1
fi

# The tap device: present, and carrying the host address?
if ! ip -4 -o addr show dev "$TAPDEV" 2>/dev/null | grep -qw "$HOSTADDR"; then
    echo "Setting up $TAPDEV (needs sudo)"
    sudo ./setup-tap.sh "$(id -un)" "$TAPDEV" "$HOSTADDR/$PREFIX"
fi

# The NFS server: is anything answering on the host address, UDP port 2049?
if ! ss -Hlun 2>/dev/null | grep -qF "$HOSTADDR:2049 "; then
    if [ ! -d "$NFSROOT" ]; then
        echo "$0: NFS root $NFSROOT does not exist; skipping the NFS server." >&2
        echo "Genera will run, but will ask for the date and cannot read sys.sct." >&2
    else
        echo "Starting the NFS and time server on $HOSTADDR (needs sudo)"
        sudo systemctl reset-failed "$UNIT" 2>/dev/null || true
        sudo systemd-run --quiet --unit="$UNIT" -p MemoryMax=1G \
            /usr/bin/env python3 "$HERE/nfs2d.py" --root "$NFSROOT" \
            --bind "$HOSTADDR" --user "$(id -un)" $RW
        for i in 1 2 3 4 5 6 7 8 9 10; do
            ss -Hlun 2>/dev/null | grep -qF "$HOSTADDR:2049 " && break
            sleep 0.3
        done
        if ! ss -Hlun 2>/dev/null | grep -qF "$HOSTADDR:2049 "; then
            echo "$0: the NFS server did not start; see journalctl -u $UNIT" >&2
            exit 1
        fi
    fi
fi

exec ./src/genera "$@"
