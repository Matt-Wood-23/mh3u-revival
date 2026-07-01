"""Tier-2 wrapper: confirm the SERVER LEG over the public path in one command.

Drives ONE headless hunter through the full lifecycle (connect/auth on :1223 ->
secure register/join on :1224 -> matchmaking create+leave) against a public IP, so
you don't have to remember the load_sim flags. Run it from the EXTERNAL box (phone
hotspot / VPS), aimed at the host's PUBLIC IP, AFTER Tier 1 (udp_probe_*) is green.

THE GOTCHA THIS ENCODES: in external mode the client auths at <host>:<auth_port>,
but then follows the StationURL the AUTH SERVER HANDS BACK for the secure leg. That
URL = whatever the HOST server ADVERTISES. So the host MUST be started advertising
its PUBLIC IP:

    MH3U_RAW=1 MH3U_ADVERTISE=<HOST_PUBLIC_IP> python server.py

If the host advertises a LAN/Tailscale/127 address, auth will pass but register/
join will fail (the client is told to connect somewhere it can't reach).

PREREQS: Tier 1 PASSed for 1223 AND 1224; host server up advertising the public IP;
this box has the repo + external/NintendoClients.

Usage:
    python check_server_leg.py <HOST_PUBLIC_IP> [auth_port=1223]
"""
import os
import sys
import subprocess

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(2)

host = sys.argv[1]
auth_port = sys.argv[2] if len(sys.argv) > 2 else "1223"

_HERE = os.path.dirname(os.path.abspath(__file__))
load_sim = os.path.join(os.path.dirname(_HERE), "load_sim.py")  # tests/load_sim.py

cmd = [sys.executable, load_sim,
       "--mode", "external", "--host", host, "--auth-port", str(auth_port),
       "--clients", "1", "--scenario", "rooms", "--players", "1"]
print("[extkit] server-leg check ->\n  " + " ".join(cmd) + "\n", flush=True)
rc = subprocess.call(cmd)

print("\n[extkit] how to read the phase table above:")
print("  connect / login err      = AUTH :%s unreachable over the public path" % auth_port)
print("                             (forward 1223 broken, or wrong public IP)")
print("  register / join_hall /   = SECURE :1224 unreachable -- the auth server")
print("  find_lobbys / create_room  handed back a StationURL the client can't reach")
print("                             (forward 1224 broken, OR host didn't advertise")
print("                              its PUBLIC IP -> set MH3U_ADVERTISE=<PUBLIC_IP>)")
print("  ALL phases pass (PASS)   = server leg works end-to-end over the public path")
print("                             (P2P hole-punch between 2 real clients is still")
print("                              a separate, untested leg)")
sys.exit(rc)
