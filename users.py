"""Dummy account store + kerberos key derivation for the MH3U NEX server.

NOTE — the auth model: on real Wii U the client does NOT send a username/password;
it presents a token minted by the *account server* (nn::act). The patched Cemu fork
redirects that account call to this server with a fixed nexPassword, so the client
and server derive the same kerberos key by PID. This password-based store is the
same mechanism, and also lets a NintendoClients test client connect with no Cemu.
"""
import collections

from nintendo.nex import kerberos

import config

User = collections.namedtuple("User", "pid name password")

# pid 2 = the secure server itself; others are test hunters.
USERS = [
    User(config.SECURE_SERVER_PID, config.SECURE_SERVER_NAME, "password"),
    User(100, "guest", "MMQea3n!fsik"),
    User(1000, "hunter1", "huntpass1"),
]


def by_name(name):
    for u in USERS:
        if u.name == name:
            return u
    return None


def by_pid(pid):
    for u in USERS:
        if u.pid == pid:
            return u
    return None


def resolve(username):
    """Accept a known test name, or any numeric PID (Wii U logs in by PID). A real
    patched-Cemu client presents its PID + the fixed nexPassword, so auto-create a
    user for unknown PIDs keyed on config.NEX_PASSWORD (the shared kerberos seed)."""
    u = by_name(username)
    if u:
        return u
    if str(username).isdigit():
        pid = int(username)
        return by_pid(pid) or User(pid, str(username), config.NEX_PASSWORD)
    return None


def derive_key(user):
    # KeyDerivationOld(base, count) — Wii U-era derivation. If real Cemu tickets
    # fail to decrypt, this is a candidate to swap (KeyDerivationNew / params).
    deriv = kerberos.KeyDerivationOld(65000, 1024)
    return deriv.derive_key(user.password.encode("ascii"), user.pid)
