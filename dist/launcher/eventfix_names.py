"""Quest names for the cross-version event quest fix, built from the player's own game.

On a US/EU game, a quest hosted by a Japanese player arrives with Shift-JIS text, and the
Western font has kana but no kanji. The fix (graphic pack MH3U_EventQuestFix) looks the
quest number up in a table and shows Western text instead; numbers not in the table are
converted to kana with '*' for each kanji.

The pack ships with a table holding only JP_NAMES below (our own English text for the
nine quests whose Western copies are DUMMY placeholders). localize() rebuilds the table
from the player's own US/EU quest files, so the names of the other 50 never ship with
the bundle. The output is identical to build/event_quest_fix/build_names.py.
STDLIB ONLY (the launcher freezes to one exe).
"""
import re
import struct
from pathlib import Path

TITLE_MAX, OBJECTIVE_MAX = 0x1D, 0x3D
PREFIXES = ("U", "E")                    # the pack's US and EU groups

# Fields: name, objective, sub objective, failure, client, description (one text for all
# five language slots). 20101 reuses the official 20151 quest's text; the other eight are
# translations from the Japanese files, approved for English by Matt on 2026-11-23.
JP_NAMES = {'20101': ['Sgt. Frog: Recon Mission',
           'Hunt a Gobul',
           '',
           'Reward hits 0, or time\r\nexpires.',
           'Keronians in Hiding',
           'Reports say a powerful military\r\n'
           'force is hidden in the seas around\r\n'
           'this island to counter our invasion!\r\n'
           'I must assess its strength at once,\r\n'
           "but I'm tied up with daily duties.\r\n"
           "I'm counting on you!"],
 '20204': ['JUMP: Twin Red Menaces',
           'Hunt 2 Volvidons',
           '',
           'Reward hits 0, or time\r\nexpires.',
           'One-Eyed Blackbeard',
           'Two red objects fell on the\r\n'
           'Sandy Plains. The men I sent to\r\n'
           'investigate never came back, so\r\n'
           "that's where you come in. Your\r\n"
           'reward? A ticket to becoming a\r\n'
           "real pirate. It's a rare one!"],
 '20206': ['YAIBA: Wind and Thunder Gods',
           'Hunt a Sand Barioth\r\nand a Zinogre',
           '',
           'Reward hits 0, or time\r\nexpires.',
           'Sharp-Eyed Little Old Man',
           'I came to slay the fearsome wind\r\n'
           'and thunder wyverns, but my back\r\n'
           'chose this moment to give out!\r\n'
           'Be a dear and beat them for me.\r\n'
           "Do it and I'll hand over my\r\n"
           'secret scroll of techniques.'],
 '20207': ["Baki: The Demon's Genes",
           'Hunt a Zinogre',
           '',
           'Reward hits 0, or time\r\nexpires.',
           '13th Head of the Tokugawa',
           'Any born a hunter dreams of\r\n'
           'being the strongest on Earth!\r\n'
           'Come, mighty one! Grapple bare\r\n'
           'and show me your true strength!\r\n'
           'To the victor, I shall grant\r\n'
           'the Proof of a true warrior!'],
 '20208': ["Armed Front: A Man's Duel!",
           'Hunt 2 Barroth',
           '',
           'Reward hits 0, or time\r\nexpires.',
           "Armed Front's 7th Leader",
           'Hunt two brawler monsters. This\r\n'
           "job won't be easy, but pull it\r\n"
           "off and I'll call you a real man.\r\n"
           "Let's see if you've got what it\r\n"
           'takes to wear our skull crest.'],
 '20301': ['JUMP: Agnaktor Onslaught!!',
           'Hunt 2 Agnaktor',
           '',
           'Reward hits 0, or time\r\nexpires.',
           'One-Eyed Blackbeard',
           'A tough job for the hunters\r\n'
           'among hunters. With effort,\r\n'
           'friendship and victory as your\r\n'
           'weapons, hunt two Agnaktor! Win\r\n'
           "and I'll give you a special\r\n"
           'ticket for the great sword of a\r\n'
           'legendary one-eyed pirate!'],
 '20304': ['USJ: Plesioth 3D',
           'Hunt a Plesioth',
           '',
           'Reward hits 0, or time\r\nexpires.',
           'Swordsman in Silver Sol',
           'USJ presents its hottest, most\r\n'
           'exciting attraction: Plesioth\r\n'
           'Adventure! A colossal body\r\n'
           'bearing down! Thrills that leap\r\n'
           'right out at you! Come join\r\n'
           'this grand adventure!'],
 '20305': ['USJ: Azure Rathalos Hunt',
           'Hunt 2 Azure Rathalos',
           '',
           'Reward hits 0, or time\r\nexpires.',
           'Swordsman in Silver Sol',
           'USJ presents its coolest, most\r\n'
           'fantastic attraction: the Azure\r\n'
           'Rathalos Show! "Azure" is a\r\n'
           'foreign word for blue. Even\r\n'
           'hunting has gone international!'],
 '20308': ['Attack on Titan: Cadet Drill',
           'Slay a Hallowed Jhen Mohran\r\nor repel it',
           '',
           'Reward or Dragonship Integrity\r\nhits 0, or time expires.',
           'Girl with a Big Appetite',
           "I'd love to see how your soldiers\r\n"
           '...I mean hunters, take down a\r\n'
           'beast this size without vertical\r\n'
           "maneuver gear. As thanks, I'll\r\n"
           'give you materials for the\r\n'
           'special blades our soldiers use.']}


def walk(r):
    """(quest number, six text fields of five language strings) of a Western record."""
    pos, fields = 8, []

    def strings():
        nonlocal pos
        out = []
        for _ in range(5):
            n = struct.unpack_from("<I", r, pos)[0]
            if n > 0x1800 or pos + 4 + n > len(r):
                raise ValueError("bad string")
            out.append(bytes(r[pos + 4:pos + 4 + n]))
            pos += 4 + n
        fields.append(out)

    strings()
    no = struct.unpack_from("<H", r, pos)[0]
    pos += 2
    strings()
    pos += 2
    strings()
    pos += 2
    strings()
    pos += 6
    strings()
    strings()
    return no, fields


def clip(s, limit):
    """Cut to at most limit bytes without splitting a UTF-8 character."""
    if len(s) <= limit:
        return s
    s = s[:limit]
    while s and (s[-1] & 0xC0) == 0x80:
        s = s[:-1]
    if s and s[-1] >= 0xC0:
        s = s[:-1]
    return s


def collect(qdir):
    """{number: fields} from a Western game's quest folder (its us/ and eu/ copies are
    identical), plus JP_NAMES for the numbers it lacks. Event (20000-29999) and arena or
    challenge (60000-69999) quests only; DUMMY placeholders are skipped."""
    table = {}
    if qdir is not None:
        for sub in ("eu", "us"):
            d = Path(qdir) / sub
            if not d.is_dir():
                continue
            for p in sorted(d.glob("q_[0-9]*.quest")):
                m = re.search(r"q_(\d+)", p.name)
                n = int(m.group(1))
                if not (20000 <= n < 30000 or 60000 <= n < 70000) or n in table:
                    continue
                try:
                    no, fields = walk(p.read_bytes())
                except (OSError, ValueError, struct.error):
                    continue
                if no != n or not fields[0][0] or fields[0][0].upper().startswith(b"DUMMY"):
                    continue
                table[n] = fields
    for k, v in JP_NAMES.items():
        if int(k) not in table:
            table[int(k)] = [[t.encode("utf-8")] * 5 for t in v]
    for fields in table.values():
        fields[0] = [clip(s, TITLE_MAX) for s in fields[0]]
        fields[1] = [clip(s, OBJECTIVE_MAX) for s in fields[1]]
    return table


def table_asm(prefix, table):
    """The pack's name table for one group: count, then per quest its number and six
    offsets (from the table start) into a blob of five NUL-ended strings per field."""
    entry_size = 7 * 4
    blob, offsets, rows = bytearray(), {}, {}
    base = 4 + entry_size * len(table)
    for n in sorted(table):
        row = []
        for strings in table[n]:
            key = tuple(strings)
            if key not in offsets:
                offsets[key] = base + len(blob)
                for s in strings:
                    blob += s + b"\0"
            row.append(offsets[key])
        rows[n] = row
    lines = ["_eqf%sNames:" % prefix, ".int %d" % len(table)]
    for n in sorted(table):
        lines.append(".int " + ", ".join("0x%X" % v for v in [n] + rows[n]))
    for i in range(0, len(blob), 16):
        lines.append(".byte " + ",".join("0x%02X" % c for c in blob[i:i + 16]))
    lines += [".align 4", "", ""]
    return "\n".join(lines)


def localize(asm, qdir):
    """The pack's patch_eventquest.asm text with both Western name tables rebuilt from the
    quest folder `qdir`, in the text's own line endings. Raises ValueError if the text has
    no such tables."""
    crlf = "\r\n" in asm
    if crlf:
        return localize(asm.replace("\r\n", "\n"), qdir).replace("\n", "\r\n")
    table = collect(qdir)
    end_mark = ".align 4\n\n"
    for prefix in PREFIXES:
        label = "_eqf%sNames:\n" % prefix
        start = asm.find(label)
        if start < 0 or asm.count(label) != 1:
            raise ValueError("no %s name table in the pack" % prefix)
        end = asm.find(end_mark, start)
        if end < 0:
            raise ValueError("unterminated %s name table" % prefix)
        asm = asm[:start] + table_asm(prefix, table) + asm[end + len(end_mark):]
    return asm
