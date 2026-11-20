"""Rebuild events/events.json from the q_NNNNN.quest files in this folder.

The launcher (Join tab, "Add the official event quests") downloads events.json and the
quest files it lists, checks each against its sha256, and puts them into the player's
event quest packs. To publish an event quest:

  1. Make it in MH3U Quest Studio (DLC / Event tab: New quest...) with a number from
     20350 to 20399 (Capcom's own event quests use 20102-20324), then export it as a
     loose .quest file named q_<number>.quest.
  2. Copy it into this folder and run:  python events/update_list.py
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
NO_MIN, NO_MAX = 20350, 20399
SLOT_DATA = 0x2000


def quest_no(rec):
    if rec[:4] != b"QTDS" or int.from_bytes(rec[4:8], "little") != 5:
        return None
    pos = 8
    for _ in range(5):
        pos += 4 + int.from_bytes(rec[pos:pos + 4], "little")
    return int.from_bytes(rec[pos:pos + 2], "little") if pos + 2 <= len(rec) else None


def main():
    quests, bad = [], []
    for path in sorted(HERE.glob("*.quest")):
        rec = path.read_bytes()
        no = quest_no(rec)
        m = re.fullmatch(r"q_(\d{5})\.quest", path.name)
        if no is None:
            bad.append(f"{path.name}: not a quest file")
        elif not NO_MIN <= no <= NO_MAX:
            bad.append(f"{path.name}: quest number {no} is outside {NO_MIN}-{NO_MAX}")
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
    (HERE / "events.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"events.json: {len(quests)} quest(s)" + "".join(f"\n  {q['file']}" for q in quests))


if __name__ == "__main__":
    main()
