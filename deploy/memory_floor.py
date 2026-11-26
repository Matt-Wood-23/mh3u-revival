"""Memory floor: hold a fixed amount of RAM so an idle cloud VM doesn't look idle.

Oracle Cloud may reclaim an Always Free compute instance it deems idle: over 7 days, CPU (95th percentile), network
and, on Arm A1 shapes, memory all under 20%. A game server between sessions is light on all three, but any one of them
above 20% means the instance isn't idle. This holds MB megabytes of RAM, touched page by page and locked with
mlockall so it stays resident and counts as used memory.

    python3 memory_floor.py [MB]        (default 350)

Run it as its own systemd service (deploy/mh3u-memfloor.service): LimitMEMLOCK=infinity lets the lock succeed, and a
high OOMScoreAdjust makes it the first thing the kernel drops if the VM ever runs short of memory.
"""
import ctypes
import os
import signal
import sys

PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
MCL_CURRENT, MCL_FUTURE = 1, 2


def meminfo():
    """(total, available) in MB from /proc/meminfo."""
    values = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, _, rest = line.partition(":")
            values[key] = int(rest.split()[0]) // 1024
    return values.get("MemTotal", 0), values.get("MemAvailable", 0)


def main():
    mb = int(sys.argv[1]) if len(sys.argv) > 1 else 350
    block = bytearray(mb * 1024 * 1024)
    for i in range(0, len(block), PAGE):  # write every page, so each one is really allocated
        block[i] = 1
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.mlockall(MCL_CURRENT | MCL_FUTURE) != 0:
        print(f"memory floor: mlockall failed ({os.strerror(ctypes.get_errno())}); holding {mb} MB unlocked",
              flush=True)
    total, available = meminfo()
    used = total - available
    print(f"memory floor: holding {mb} MB; VM memory in use {used} of {total} MB "
          f"({100 * used / max(total, 1):.0f}%)", flush=True)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True:
        signal.pause()


if __name__ == "__main__":
    main()
