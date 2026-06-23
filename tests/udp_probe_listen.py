"""Throwaway UDP reachability probe listener (LAN diagnostics).

Binds 0.0.0.0:<port> and prints the sender address + payload of every datagram
that arrives. Used to prove whether a remote PC's UDP packets actually reach this
host's NIC+socket (i.e. isolate "Cemu isn't sending" from "the network path drops
it"). Kept as a LAN diagnostic (dist/README test-order rung 2): run it on the host,
fire a UDP packet at it from the other PC; if a host-local probe lands but the remote
one never does, the LAN is dropping PC-to-PC UDP (client/AP isolation) — use Tailscale.
"""
import socket
import sys
import datetime

port = int(sys.argv[1]) if len(sys.argv) > 1 else 1223
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", port))
print(f"[probe] listening UDP 0.0.0.0:{port} — waiting for datagrams (Ctrl-C to stop)", flush=True)
while True:
    data, addr = s.recvfrom(4096)
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[probe] {ts}  RECV from {addr[0]}:{addr[1]}  len={len(data)}  data={data[:64]!r}", flush=True)
