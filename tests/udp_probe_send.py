"""UDP reachability probe SENDER (port-forward diagnostics) — zero deps, single file.

Stdlib only, so it copies to ANY box with Python (phone-hotspot laptop, $5 VPS,
friend's PC) with no repo / NintendoClients needed. Run it from a network OTHER
than the host's (the whole point — you cannot validate a public forward from the
host's own LAN; many gateways hairpin to the LAN and "succeed" meaninglessly).

For each port it fires a few datagrams carrying a unique token at <host>:<port> and
waits for the listener's echo of that exact token. Echo back == the router forwards
UDP inbound AND lets the reply back out == the NEX server leg is reachable.

    python udp_probe_send.py <HOST_PUBLIC_IP> 1223 1224

Pair with `udp_probe_listen.py 1223 1224` running on the host (server stopped).
A PASS here is the definitive UDP port-forward result; a TCP checker can't give it.
"""
import socket
import sys
import os
import time

if len(sys.argv) < 3:
    print("usage: python udp_probe_send.py <host> <port> [port2 ...]")
    sys.exit(2)

host = sys.argv[1]
ports = [int(a) for a in sys.argv[2:]]
TRIES = 4          # datagrams per port
TIMEOUT = 2.0      # seconds to wait for an echo per try

print(f"[send] probing {host} on ports {ports}  ({TRIES} tries x {TIMEOUT}s each)\n", flush=True)
results = {}
for port in ports:
    token = f"MH3U-PROBE {os.urandom(4).hex()} :{port}".encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(TIMEOUT)
    got = False
    rtt = None
    for i in range(1, TRIES + 1):
        try:
            t0 = time.time()
            s.sendto(token, (host, port))
            while True:
                data, addr = s.recvfrom(4096)
                if data == token:
                    rtt = (time.time() - t0) * 1000
                    got = True
                    break
                # stray packet (e.g. server still up sending PRUDP) — keep waiting within timeout
            if got:
                print(f"[send] :{port} try {i}  ECHO from {addr[0]}:{addr[1]}  rtt={rtt:.0f}ms  -> PASS", flush=True)
                break
        except socket.timeout:
            print(f"[send] :{port} try {i}  no echo ({TIMEOUT:.0f}s)", flush=True)
        except OSError as e:
            print(f"[send] :{port} try {i}  send error: {e}", flush=True)
            break
    s.close()
    results[port] = got
    if not got:
        print(f"[send] :{port}  -> FAIL (no echo after {TRIES} tries)", flush=True)
    print(flush=True)

ok = [p for p, v in results.items() if v]
bad = [p for p, v in results.items() if not v]
print("=" * 56, flush=True)
print(f"[send] RESULT  pass={ok or '-'}  fail={bad or '-'}", flush=True)
if bad:
    print("[send] FAIL = router not forwarding UDP both ways on those ports", flush=True)
    print("[send]        (or the host listener isn't running / server still owns the port)", flush=True)
sys.exit(0 if not bad else 1)
