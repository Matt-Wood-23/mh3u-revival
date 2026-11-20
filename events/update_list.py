"""Rebuild events/events.json from the q_NNNNN.quest files in this folder.

The launcher (Join tab, "Add the official event quests") downloads events.json and the
quest files it lists, checks each against its sha256, and puts them into the player's
event quest packs. To publish an event quest:

  1. Get the quest as a loose q_<number>.quest file in this folder. A quest someone sent
     in a quest pack (quest1..quest3 from their save folder, see README.md here) is
     pulled out with
         python events/update_list.py --add <pack file> <quest number> [--as <new number>]
     which also renumbers it (--as) when its number is taken or in the wrong block.
     The number sets the rank the game lists it under; use the official block for that
     rank (Capcom's own event quests are 20102-20104, 20201-20210 and 20302-20324):
         20150-20199  low rank        20250-20299  high rank        20350-20399  G rank
  2. Run:  python events/update_list.py   (--add does this too)
  3. Commit events.json and the .quest file. Players get it the next time they press
     Save + Play. Delete the file (and rerun this) to end the event: the launcher then
     removes it from players' packs, but only if they haven't edited it.

One file works for the US and EU games (quest text is stored in all five languages).
The Japanese game isn't supported yet.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RANGES = ((20150, 20199), (20250, 20299), (20350, 20399))   # low, high, G rank
SLOT_DATA = 0x2000
PACK_HEADER, PACK_SLOT, PACK_SLOTS = 0x28, 0x2010, 20


def _no_offset(rec):
    """Offset of the u16 quest number in a QTDS record (after the 5 quest names)."""
    if rec[:4] != b"QTDS" or int.from_bytes(rec[4:8], "little") != 5:
        return None
    pos = 8
    for _ in range(5):
        pos += 4 + int.from_bytes(rec[pos:pos + 4], "little")
    return pos if pos + 2 <= len(rec) else None


def quest_no(rec):
    pos = _no_offset(rec)
    return None if pos is None else int.from_bytes(rec[pos:pos + 2], "little")


def in_ranges(no):
    return any(lo <= no <= hi for lo, hi in RANGES)


def find_in(data, no):
    """The record numbered `no` from a quest pack, or a loose .quest file's own record."""
    if data[:4] == b"QTDS":
        return data.rstrip(b"\0") if quest_no(data) == no else None
    for i in range(PACK_SLOTS):
        o = PACK_HEADER + i * PACK_SLOT
        rec = data[o:o + SLOT_DATA]
        if rec[:4] == b"QTDS" and quest_no(rec) == no:
            return rec.rstrip(b"\0")
    return None


def add(source, no, new_no=None):
    data = Path(source).read_bytes()
    rec = find_in(data, no)
    if rec is None:
        sys.exit(f"{source}: no quest numbered {no} in it")
    new_no = new_no or no
    if not in_ranges(new_no):
        blocks = ", ".join(f"{lo}-{hi}" for lo, hi in RANGES)
        sys.exit(f"quest number {new_no} is outside {blocks}: pick one with --as")
    dst = HERE / f"q_{new_no:05d}.quest"
    if dst.exists():
        sys.exit(f"{dst.name} already exists: pick another number with --as")
    pos = _no_offset(rec)
    rec = rec[:pos] + new_no.to_bytes(2, "little") + rec[pos + 2:]
    dst.write_bytes(rec)
    print(f"added {dst.name} ({len(rec)} bytes" + (f", renumbered from {no}" if new_no != no else "")
          + "). Open it in Quest Studio and play it before you commit it.")


def rebuild():
    quests, bad = [], []
    for path in sorted(HERE.glob("*.quest")):
        rec = path.read_bytes()
        no = quest_no(rec)
        m = re.fullmatch(r"q_(\d{5})\.quest", path.name)
        if no is None:
            bad.append(f"{path.name}: not a quest file")
        elif not in_ranges(no):
            blocks = ", ".join(f"{lo}-{hi}" for lo, hi in RANGES)
            bad.append(f"{path.name}: quest number {no} is outside {blocks}")
        elif not m or int(m.group(1)) != no:
            bad.append(f"{path.name}: rename it to q_{no:05d}.quest")
        elif len(rec.rstrip(b"\0")) > SLOT_DATA:
            bad.append(f"{path.name}: too big for a quest slot ({len(rec)} bytes)")
        else:
            quests.append({"file": path.name, "sha256": hashlib.sha256(rec).hexdigest()})
    if bad:
        print("\n".join(bad))
        sys.exit(1)
    out = {"schema": 1, "quests": quests}
    (HERE / "events.json").write_bytes((json.dumps(out, indent=2) + "\n").encode("utf-8"))
    print(f"events.json: {len(quests)} quest(s)" + "".join(f"\n  {q['file']}" for q in quests))


def main(argv):
    if argv[:1] == ["--add"]:
        if len(argv) not in (3, 5) or (len(argv) == 5 and argv[3] != "--as"):
            sys.exit("usage: update_list.py --add <pack or .quest file> <number> [--as <new number>]")
        add(argv[1], int(argv[2]), int(argv[4]) if len(argv) == 5 else None)
    elif argv:
        sys.exit(__doc__)
    rebuild()


if __name__ == "__main__":
    main(sys.argv[1:])
