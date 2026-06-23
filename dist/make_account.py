#!/usr/bin/env python3
"""Generate a fresh Cemu account.dat for a revival player with a UNIQUE NEX PID.

The revival NEX server keys each player purely on PrincipalId and auto-provisions any
numeric PID (see users.py), so every player just needs a DISTINCT PrincipalId. This
writes a clean, gate-valid account.dat -- AccountId set, IsPasswordCacheEnabled=1,
AccountPasswordCache nonzero, PrincipalId != 0 -- with a fresh random Uuid /
TransferableIdBase and the stock default Mii. It contains NO personal data.

PID assignment is RANDOM by default (a value in [1000000000, 1999999999]) so two players
who each run this independently essentially never collide -- the old "host=1, friends use
2,3,4..." hand-numbering made everyone pick low numbers and clash (and a copied bundle
guaranteed it). Within a 4-player room the random collision chance is ~6e-9, and the
server rejects any residual duplicate. Pass an explicit --player N only if you WANT a
fixed/memorable PID (e.g. a host that likes 1000000001); otherwise just take the random one.

Usage:
    python make_account.py "<act_dir>"                 # random unique PID (recommended)
    python make_account.py "<act_dir>" --player 1      # explicit PID 1000000000+N (advanced)

(The old `make_account.py <number> "<act_dir>"` order is still accepted.)

<act_dir> = the account folder in the player's Cemu data, normally:
    <cemu_data>/mlc01/usr/save/system/act/80000001
"""
import os
import sys
import secrets

# Stock Cemu default Mii (cosmetic; the in-game hunter name comes from the MH3U save,
# not from here). Not personal data.
DEFAULT_MII = ("010001100000d73e030034330100010001000100010001000100640065006600610075"
               "006c0074000000000000000100010001000100010001000106010001000100010001"
               "000100010001000100010001000100010001000100010001000100")
DEFAULT_MIINAME = "00640065006600610075006c00740000000000000000"  # "default" (UTF-16LE)

# Random PID range: 10-digit, 1.0-2.0 billion. Fits u32, sits above every reserved low PID
# (server=2, guest=100, hunter1=1000) and clear of the explicit-player band's low end.
PID_LO = 1_000_000_000
PID_HI = 1_999_999_999


def make_account_dat(act_dir, n=None):
    if n is None:
        pid = PID_LO + secrets.randbelow(PID_HI - PID_LO + 1)   # random, collision-safe
    else:
        if not (1 <= n <= 250):
            raise SystemExit("explicit player number must be between 1 and 250")
        pid = 0x3b9aca00 + n                     # explicit: player 1 -> 0x3b9aca01 = 1000000001
    fields = [
        "AccountInstance_20120705",
        "PersistentId=80000001",             # Cemu first-slot id (same on every install)
        f"TransferableIdBase={secrets.token_hex(8)}",
        f"Uuid={secrets.token_hex(16)}",
        f"MiiData={DEFAULT_MII}",
        f"MiiName={DEFAULT_MIINAME}",
        f"AccountId=CemuMH3U{pid & 0xffff:04X}",
        "BirthYear=0", "BirthMonth=0", "BirthDay=0", "Gender=0",
        "EmailAddress=",
        "Country=0", "SimpleAddressId=0",
        f"PrincipalId={pid:08x}",
        "IsPasswordCacheEnabled=1",
        f"AccountPasswordCache={secrets.token_hex(32)}",
    ]
    os.makedirs(act_dir, exist_ok=True)
    path = os.path.join(act_dir, "account.dat")
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(fields) + "\n")
    return path, pid


def _parse_args(argv):
    """Accept, in any order: one path (the act_dir) and an optional explicit player number
    (bare digits, or `--player N` / `-p N`). Random PID if no number is given."""
    act_dir = None
    n = None
    it = iter(argv)
    for a in it:
        if a in ("--player", "-p"):
            n = int(next(it))
        elif a.startswith("--player="):
            n = int(a.split("=", 1)[1])
        elif a.isdigit():
            n = int(a)                       # back-compat: bare number = explicit player
        else:
            act_dir = a                      # anything else is the act_dir path
    return act_dir, n


if __name__ == "__main__":
    act_dir, n = _parse_args(sys.argv[1:])
    if not act_dir:
        print(__doc__)
        sys.exit(1)
    path, pid = make_account_dat(act_dir, n)
    print(f"wrote {path}")
    print(f"  AccountId=CemuMH3U{pid & 0xffff:04X}  PrincipalId={pid:08x}  NEX PID {pid}"
          + ("  (random unique)" if n is None else f"  (explicit player {n})"))
    print("  Cemu must be CLOSED when you run this (it rewrites account.dat on exit).")
