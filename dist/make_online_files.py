#!/usr/bin/env python3
"""Generate the dummy Wii U online-gate files Cemu checks before enabling online play.

Cemu's iosuCrypt_checkRequirementsForOnlineMode() only checks these files EXIST
(otp.bin/seeprom.bin are size-checked; the cert files just need to load) -- it does NO
content/crypto validation, because our patched Cemu redirects the actual NEX connection
to the revival server instead of Nintendo. So right-sized GARBAGE files pass the gate
with ZERO Nintendo data in them: otp.bin is all zeros, and every cert file is a 4-byte
empty-DER stub (30 82 00 00). No real keys or certificates are produced or shipped.

Usage:
    python make_online_files.py "<cemu_data_dir>"

<cemu_data_dir> = the folder that holds settings.xml (your Cemu data root). For a
portable install that's the "portable" folder next to the exe; otherwise it's
%APPDATA%\\Cemu (Windows) / ~/.config/Cemu (Linux).
"""
import os
import sys

CERT_STUB = bytes.fromhex("30820000")  # minimal empty DER: SEQUENCE, length 0

# console cert store (mlc01/.../content/ccerts)
CCERTS = [
    "WIIU_ACCOUNT_1_CERT.der", "WIIU_ACCOUNT_1_RSA_KEY.aes",
    "WIIU_COMMON_1_CERT.der",  "WIIU_COMMON_1_RSA_KEY.aes",
    "WIIU_OLIVE_1_CERT.der",   "WIIU_OLIVE_1_RSA_KEY.aes",
    "WIIU_VINO_1_CERT.der",    "WIIU_VINO_1_RSA_KEY.aes",
    "WIIU_WOOD_1_CERT.der",    "WIIU_WOOD_1_RSA_KEY.aes",
]
# server CA store (mlc01/.../content/scerts) -- all .der
SCERTS = [
    "ADDTRUST_EXT_CA_ROOT", "BALTIMORE_CYBERTRUST_ROOT_CA", "CACERT_NINTENDO_CA",
    "CACERT_NINTENDO_CA_G2", "CACERT_NINTENDO_CA_G3", "CACERT_NINTENDO_CLASS2_CA",
    "CACERT_NINTENDO_CLASS2_CA_G2", "CACERT_NINTENDO_CLASS2_CA_G3", "COMODO_CA",
    "CYBERTRUST_GLOBAL_ROOT_CA", "DIGICERT_ASSURED_ID_ROOT_CA",
    "DIGICERT_ASSURED_ID_ROOT_CA_G2", "DIGICERT_GLOBAL_ROOT_CA",
    "DIGICERT_GLOBAL_ROOT_CA_G2", "DIGICERT_HIGH_ASSURANCE_EV_ROOT_CA",
    "ENTRUST_CA_2048", "ENTRUST_ROOT_CA", "ENTRUST_ROOT_CA_G2",
    "ENTRUST_SECURE_SERVER_CA", "EQUIFAX_SECURE_CA", "GEOTRUST_GLOBAL_CA",
    "GEOTRUST_GLOBAL_CA2", "GEOTRUST_PRIMARY_CA", "GEOTRUST_PRIMARY_CA_G3",
    "GLOBALSIGN_ROOT_CA", "GLOBALSIGN_ROOT_CA_R2", "GLOBALSIGN_ROOT_CA_R3",
    "GTE_CYBERTRUST_GLOBAL_ROOT", "THAWTE_PREMIUM_SERVER_CA", "THAWTE_PRIMARY_ROOT_CA",
    "THAWTE_PRIMARY_ROOT_CA_G3", "UTN_DATACORP_SGC_CA", "UTN_USERFIRST_HARDWARE_CA",
    "VERISIGN_CLASS3_PUBLIC_PRIMARY_CA", "VERISIGN_CLASS3_PUBLIC_PRIMARY_CA_G2",
    "VERISIGN_CLASS3_PUBLIC_PRIMARY_CA_G3", "VERISIGN_CLASS3_PUBLIC_PRIMARY_CA_G5",
    "VERISIGN_UNIVERSAL_ROOT_CA", "VERIZON_GLOBAL_ROOT_CA",
]


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def generate(root):
    _write(os.path.join(root, "otp.bin"), b"\x00" * 1024)
    _write(os.path.join(root, "seeprom.bin"), b"\x00" * 512)
    content = os.path.join(root, "mlc01", "sys", "title", "0005001b", "10054000", "content")
    for n in CCERTS:
        _write(os.path.join(content, "ccerts", n), CERT_STUB)
    for n in SCERTS:
        _write(os.path.join(content, "scerts", n + ".der"), CERT_STUB)
    return 2 + len(CCERTS) + len(SCERTS)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    root = sys.argv[1]
    count = generate(root)
    print(f"wrote {count} dummy online-gate files under {root}")
    print("  otp.bin (1024B zeros), seeprom.bin (512B zeros), 49 empty-DER cert stubs")
    print("  -> restart Cemu; enable online + set Network Service = Custom in Options > Account")
