"""UDP reachability probe LISTENER + ECHO (port-forward diagnostics).

Binds 0.0.0.0:<port> (one or more ports) and, for every datagram that arrives,
(1) prints the sender addr + payload and (2) ECHOES the exact bytes back to the
sender. The echo is what lets the remote `udp_probe_send.py` self-report PASS/FAIL
with nobody watching this console — it proves the UDP path works BOTH ways
(inbound forward + outbound reply), which is exactly what NEX/PRUDP needs and what
a TCP checker like canyouseeme.org (TCP-only) physically cannot tell you.

Run this on the HOST behind the router (the port-forward target machine), with the
live NEX server STOPPED (it owns 1223/1224). Test both forwarded ports:

    python udp_probe_listen.py 1223 1224

Then from a machine on a DIFFERENT network (phone hotspot / VPS / friend's PC) run
`udp_probe_send.py <this-host-PUBLIC-IP> 1223 1224`. If the sender prints PASS, the
forward delivers UDP in and back out. (See tests/extkit/README for the full runbook.)
"""
import socket
import sys
import datetime
import select

ports = [int(a) for a in sys.argv[1:]] or [1223]
socks = []
for p in ports:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", p))
    socks.append(s)
    print(f"[probe] listening UDP 0.0.0.0:{p} (echo on)", flush=True)
print("[probe] waiting for datagrams — Ctrl-C to stop", flush=True)

by_fd = {s.fileno(): s for s in socks}
while True:
    ready, _, _ = select.select(socks, [], [])
    for s in ready:
        data, addr = s.recvfrom(4096)
        port = s.getsockname()[1]
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[probe] {ts}  :{port} RECV from {addr[0]}:{addr[1]}  len={len(data)}  data={data[:64]!r}", flush=True)
        try:
            s.sendto(data, addr)  # echo exact bytes back to source addr:port
        except OSError as e:
            print(f"[probe] {ts}  :{port} echo FAILED to {addr}: {e}", flush=True)
