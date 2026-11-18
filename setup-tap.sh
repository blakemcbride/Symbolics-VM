#!/bin/sh
# Create the tap network device the VLM needs.  Run as root, e.g.
#
#     sudo ./setup-tap.sh [user [device [host-address/prefix]]]
#
# user     the user who will run genera (default: the user invoking sudo)
# device   the tap device name                (default: tap0)
# address  the host's address on that device  (default: 10.0.0.1/24)
#
# The device does not survive a reboot; run this again after each one.
# The defaults match the sample configuration in dot.VLM.

set -e

TAPUSER=${1:-${SUDO_USER:-$(id -un)}}
DEV=${2:-tap0}
ADDR=${3:-10.0.0.1/24}

if [ "$(id -u)" -ne 0 ]; then
    echo "$0: must be run as root" >&2
    exit 1
fi

if ! ip link show "$DEV" >/dev/null 2>&1; then
    ip tuntap add dev "$DEV" mode tap user "$TAPUSER"
fi
ip addr replace "$ADDR" dev "$DEV"
ip link set "$DEV" up
echo "$DEV is up at $ADDR for user $TAPUSER"
