"""Check the host's NAT-check responder (UDP 10025) from OUTSIDE their network.

Before a Cemu player creates a room, the game asks "what's my public address?" on UDP
10025. The patched Cemu sends that question to the Revival server, and the game refuses
to create a room if nothing answers. check_server_leg.py does not cover this port, so a
host can pass that test and still have every Cemu player fail at "Create Room".

Run it from a machine that is NOT on the host's network, with the host's server running.
Stdlib only, single file — copy it anywhere:

    python check_natcheck.py <HOST_PUBLIC_IP> [port=10025]

PASS = the server answered (it also prints the address it sees you at).
FAIL = no answer: UDP 10025 isn't forwarded to the server PC, Windows Firewall is
       blocking it, or the server isn't running.
"""
import socket
import struct
import sys

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(2)

host = sys.argv[1]
port = int(sys.argv[2]) if len(sys.argv) > 2 else 10025

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(3)
# The game sends types 0x65/0x66/0x67; servers answer 0x65 and 0x67 only.
for attempt in range(3):
    s.sendto(struct.pack(">IIII", 0x65, 0, 0, 0), (host, port))
    try:
        data, addr = s.recvfrom(64)
    except socket.timeout:
        print("attempt %d: no reply" % (attempt + 1))
        continue
    except ConnectionResetError:
        # Windows reports an ICMP "port unreachable" this way: something answered, but
        # nothing is listening on that port.
        print("attempt %d: port closed (nothing listening)" % (attempt + 1))
        continue
    if len(data) >= 16:
        _type, seen_port, seen_ip, _srv = struct.unpack(">IIII", data[:16])
        print("PASS: %s:%d answered; it sees you at %s:%d"
              % (addr[0], addr[1], socket.inet_ntoa(struct.pack(">I", seen_ip)), seen_port))
        sys.exit(0)
    print("attempt %d: unexpected %d-byte reply" % (attempt + 1, len(data)))

print("FAIL: nothing answered on %s:%d (UDP). Check the router forward (UDP, to the "
      "server PC), the Windows Firewall rule, and that the server is running." % (host, port))
sys.exit(1)
