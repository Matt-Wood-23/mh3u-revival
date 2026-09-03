"""MH3U NEX server — configuration.

Credentials recovered by reverse-engineering the retail client (MH3G_Cafe_US_v1.3):
GameServerID + AccessKey are call-path-proven and hardcoded in two builders.

The NEX *library version* could not be pinned statically (stripped binary). It is
a small search space and a wrong value fails with an obvious PRUDP/RMC parse
error, so it is the one knob to TUNE empirically — see README "NEX version".
"""

import os


def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _float_env(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default

# --- RUNTIME-CONFIRMED (2026-06-14, live PRUDP handshake) -------------------
# serverId proven by the patched Cemu's ACT_GetNexToken log; access key proven
# by brute-forcing MH3U's real SYN signature (matched 'cb2b2f5a', NOT the two
# statically-extracted candidates below). Both earlier static guesses were wrong.
GAME_SERVER_ID = 0x10104d00      # logged from ACT_GetNexToken_WithCache(serverId)
ACCESS_KEY = "cb2b2f5a"          # SYN-signature-verified PRUDP access key
# The other hardcoded 8-hex strings near it (now known NOT to be the access key):
ACCESS_KEY_ALT = "168d08d9"      # stored UTF-16 in .elf
ACCESS_KEY_ALT2 = "deed2a88"     # stored ASCII in .elf

# --- TUNE THIS (see README) -------------------------------------------------
# Early Wii U title (US release 2013). Candidates to try, in rough order:
#   30000 (3.0.0), 30400 (3.4.0), 30504 (3.5.4), 30609, 30810, 31000, 40000
NEX_VERSION = 30000

# Base PRUDP/kerberos profile. "default" = Wii U-style (PRUDP V1, RC4, 32B keys).
SETTINGS_BASE = "default"

# --- topology ---------------------------------------------------------------
# Bind to 0.0.0.0 by default so a host can accept remote players (LAN / port-
# forwarded / overlay). 0.0.0.0 still serves localhost, so single-machine tests
# are unaffected. Override with MH3U_BIND=127.0.0.1 to restrict to local only.
HOST = os.environ.get("MH3U_BIND", "0.0.0.0")
AUTH_PORT = 1223                 # NEX authentication server (Quazal RendezVous)
SECURE_PORT = 1224               # NEX secure server (matchmaking lives here)

# Co-location override (env MH3U_ADVERTISE). When the host PLAYER runs on the same
# machine as the server, its Cemu connects via loopback, so the server observes its
# address as 127.x — useless to a remote joiner. Set this to the host's REACHABLE IP
# (LAN IP for a LAN game, public IP for port-forward, overlay IP for Tailscale) and the
# server substitutes it for loopback-observed peers only. Genuinely remote players keep
# their observed (NAT-external) address. Leave empty to always use the observed address.
ADVERTISE_ADDRESS = os.environ.get("MH3U_ADVERTISE", "").strip()

# Address clients are TOLD to connect to for the secure server (baked into the kerberos
# ticket). This must be a REACHABLE address, NOT the 0.0.0.0 bind address — the advertise
# IP if set (LAN/public/overlay), else 127.0.0.1 for single-machine use. Splitting this
# from HOST is why binding 0.0.0.0 no longer breaks the ticket.
SERVER_ADDRESS = ADVERTISE_ADDRESS or "127.0.0.1"

# --- optional UDP P2P relay -------------------------------------------------
# Direct peer-to-peer remains the default. Set MH3U_RELAY=force to advertise a relay
# endpoint for every host<->guest gameplay link. Set MH3U_RELAY=auto to learn
# failed direct pairs in memory and relay those pairs on later attempts.
RELAY_MODE = os.environ.get("MH3U_RELAY", "off").strip().lower()
if RELAY_MODE not in ("off", "force", "auto"):
    RELAY_MODE = "off"

# Address/ports advertised for relayed gameplay UDP. The relay binds on MH3U_BIND and tells
# clients to connect to RELAY_ADDRESS. Use the same reachable address as the NEX server unless
# the relay is exposed through a different IP/name.
RELAY_ADDRESS = os.environ.get("MH3U_RELAY_ADVERTISE", SERVER_ADDRESS).strip() or SERVER_ADDRESS
RELAY_PORT_START = _int_env("MH3U_RELAY_PORT_START", 27100)
RELAY_PORT_END = _int_env("MH3U_RELAY_PORT_END", 27164)
RELAY_IDLE_TIMEOUT = _float_env("MH3U_RELAY_IDLE_TIMEOUT", 300.0)

# Endpoint pinning for relay ports. A relay port otherwise belongs to the first two
# endpoints that send to it, with no tie to the NEX session -- fine for a small private
# host, a griefing surface on a public one. Strict mode drops datagrams whose SOURCE IP
# is not one of the pair's registered addresses.
#
# OFF BY DEFAULT, deliberately. Pinning on port is impossible (confirmed on hardware
# 2026-09-03: a Wii U registered PRUDP :61906 but sent gameplay UDP from :55250, and Cemu
# :58828 -> :64005 -- the game opens a separate P2P socket). Pinning on IP is workable but
# not risk-free: on an overlay network a peer can legitimately send from its Radmin/
# Tailscale address rather than the one the NEX connection was observed on. Mismatches are
# therefore ALWAYS logged; enable this only once your own logs show no false positives.
RELAY_STRICT = os.environ.get("MH3U_RELAY_STRICT", "").strip() == "1"

# Which NAT-traversal probes get their peer address rewritten to a relay endpoint.
# Measured 2026-09-03: the game IGNORES the get_session_urls address for gameplay and
# uses the probe-advertised one, so this switch controls whether the relay carries any
# traffic at all (with probes direct, relay ports saw 0 packets).
#   all  - rewrite every probe (full relay; breaks 3-player rooms as of 2026-09-03)
#   host - rewrite only probes for pairs involving the room HOST, leave guest<->guest
#          direct. Diagnostic bisect: isolates whether guest<->guest relaying is the
#          part that breaks the mesh.
#   off  - never rewrite probes. Relay ports then carry nothing; gameplay is fully direct.
# "host" and "off" both expose real peer addresses -- diagnostics, not privacy settings.
RELAY_PROBES_MODE = os.environ.get("MH3U_RELAY_PROBES", "all").strip().lower()
if RELAY_PROBES_MODE in ("1", "true", "yes"):
    RELAY_PROBES_MODE = "all"
elif RELAY_PROBES_MODE in ("0", "false", "no"):
    RELAY_PROBES_MODE = "off"
if RELAY_PROBES_MODE not in ("all", "host", "off"):
    RELAY_PROBES_MODE = "all"

# LAN-side relay address, for sessions that mix local and internet players.
#
# RELAY_ADDRESS is advertised to everyone, which cannot be right for both halves of a
# mixed room: give out the public IP and a player on the SERVER'S OWN LAN has to leave
# the network and come back in (NAT hairpin, which many routers refuse); give out the
# LAN IP and remote players cannot reach it at all. So when the relay is published on a
# PUBLIC address, peers observed on a private address are handed this one instead. This
# mirrors what _build_public() already does for direct connections, where each peer is
# stamped with the address it was actually observed on.
#
# Auto-detected from the default route; override if that picks the wrong NIC (a Radmin /
# Tailscale / Hyper-V adapter). Only ever consulted when RELAY_ADDRESS is public AND the
# recipient is private, so a pure-LAN deployment behaves exactly as before.
def is_private_ip(ip):
    """RFC1918 / loopback / link-local — i.e. not reachable from the internet.

    Caveat: ipaddress also reports the TEST-NET documentation ranges (192.0.2.0/24,
    198.51.100.0/24, 203.0.113.0/24) as private, so do not use those as stand-in
    "public" addresses in tests. Overlay networks go the other way — Radmin 26.x and
    Tailscale 100.64/10 both read as NOT private, which is what keeps overlay
    deployments on the single-address path they have always used.
    """
    if not ip:
        return False
    try:
        import ipaddress
        a = ipaddress.ip_address(ip)
        return a.is_private or a.is_loopback or a.is_link_local
    except ValueError:
        return False


def _default_lan_ip():
    """Address on the default route, but ONLY if it is private.

    On a host using IP passthrough the default-route address is the PUBLIC one (measured:
    a passthrough box returns its own public address here), which is useless as a "LAN alternative"
    -- so reject anything non-private and leave the field empty rather than store a value
    that silently means nothing.
    """
    import socket
    try:
        s_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s_.connect(("8.8.8.8", 80))   # no packets sent; just resolves the route
            ip = s_.getsockname()[0]
        finally:
            s_.close()
    except Exception:
        return ""
    return ip if is_private_ip(ip) else ""


RELAY_ADDRESS_LAN = (os.environ.get("MH3U_RELAY_ADVERTISE_LAN", "").strip()
                     or _default_lan_ip())

# In-memory auto-relay learning. This state is deliberately not persisted across
# server restarts; it only prevents repeated failed direct joins during one uptime.
RELAY_AUTO_MAX_CLIENTS = _int_env("MH3U_RELAY_AUTO_MAX_CLIENTS", 500)
RELAY_AUTO_MAX_PAIRS = _int_env("MH3U_RELAY_AUTO_MAX_PAIRS", 2000)
RELAY_AUTO_PAIR_TTL = _float_env("MH3U_RELAY_AUTO_PAIR_TTL", 86400.0)
RELAY_AUTO_CLIENT_TTL = _float_env("MH3U_RELAY_AUTO_CLIENT_TTL", 3600.0)

# Optional comma-separated NAT property values to treat as relay-worthy once the
# game's natm/natf constants are decoded from live captures.
RELAY_AUTO_BAD_NATM = os.environ.get("MH3U_RELAY_AUTO_BAD_NATM", "").strip()
RELAY_AUTO_BAD_NATF = os.environ.get("MH3U_RELAY_AUTO_BAD_NATF", "").strip()

# The fixed NEX password the patched Cemu hands the game (napi_act.cpp
# ACT_GetNexToken redirect). The game derives its kerberos key from this, so the
# server MUST derive the connecting player's key from the same value.
# MUST MATCH the Cemu patch's `nexPassword`.
NEX_PASSWORD = "mh3u_revival_pw"

# Secure-server identity (the "Quazal Rendez-Vous" account, PID 2 by convention).
SECURE_SERVER_PID = 2
SECURE_SERVER_NAME = "Quazal Rendez-Vous"
SERVER_DISPLAY_NAME = "MH3U Revival (dev)"
