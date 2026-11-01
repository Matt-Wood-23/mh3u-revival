# 60 FPS fix (Cemu graphic pack)

MH3U ships with its frame limiter switched off, so Cemu runs it at 60 fps or faster. The game
was built for 30, and some things run at the wrong speed above that. This pack turns on the game's own frame
limiter and corrects those things for the frame rate you pick.

It's optional and only changes your own game. You can use it with or without online play.

## What it fixes at 60 fps

| Without the pack | With the pack |
| --- | --- |
| Camera turns about 1.8x too fast with the stick (underwater too) | normal speed |
| Lance charge drains stamina twice as fast | normal rate |
| Buff icons beside your name cycle twice as fast | normal speed |
| Hammer golf swing out of the Spinning Bludgeon can't be done | works again |
| Alatreon's running turn plays twice as fast | normal speed |

Playing at 60 also halves input lag. The game takes about 6 frames to react to a button in
either case, which is about 200 ms at 30 fps and about 100 ms at 60. This pack lets you keep
60 without the speed bugs.

## Presets

- **60 FPS (normalized beta)**: recommended.
- **45 FPS (middle ground)**: the same fixes, tuned for 45.
- **30 FPS (vanilla-correct)**: everything exactly as designed.
- **Uncapped (stock 3000, for A/B)**: the game as it ships, the same as not using the pack.
  For comparing.

## Install

1. Download **[MH3U_FPS_Cap.zip](https://github.com/Matt-Wood-23/mh3u-revival/releases/download/v0.2.0-beta/MH3U_FPS_Cap.zip)**
   (the same files are in [graphic_packs/MH3U_FPS_Cap](../graphic_packs/MH3U_FPS_Cap)).
2. In Cemu, click **File → Open Cemu folder**. Open the `graphicPacks` folder there (create
   it if it's missing) and unzip into it, so you end up with
   `graphicPacks\MH3U_FPS_Cap\rules.txt`. In the MH3U Online Bundle, that folder is
   `portable\graphicPacks`.
3. In Cemu, open **Options → Graphic packs → Monster Hunter 3 Ultimate → Mods → FPS Cap**.
   Tick it and pick the **60 FPS (normalized beta)** preset.
4. Start the game. If it was running, restart it. Changing presets also needs a game restart.

**Check it's on:** Cemu's title bar should hold steady at the frame rate you picked, even on
a high-refresh monitor. Cemu's `log.txt` (in the same Cemu folder) also has a line like
`Applying patch group 'MH3U_FpsCap_US_v13'`.

## Game versions

- **US v1.3 and EU v1.3**: tested in-game.
- **JP (MH3G HD Ver. v96)**: included but not tested yet.

The patches target the v1.3 update (shown as **v32** in Cemu's game list for US and EU). If the
update isn't installed, the pack does nothing.

## Online

Each player chooses for themselves, since the pack only changes their own game. In testing, a
room with one player on the 60 preset and one without played and cleared hunts normally.

## Known issues at 60 fps

- Some hit reactions, probably roars or tremors, push your hunter back about twice as far.
  The fix is found but isn't in the pack yet.
- A few Arzuros and Zinogre jumps may still run fast. A separate fix exists but hasn't been
  confirmed in-game yet.

## Reporting problems

If something still looks too fast, too slow, or broken, report it on the
[issue tracker](https://github.com/Matt-Wood-23/mh3u-revival/issues) or the
[Discord](https://discord.gg/HTEWJDYgzJ). Please include:

- your game region (US, EU or JP) and the preset you used;
- the weapon or monster involved;
- what looked off.

A short clip at 30 and at 60 helps a lot. Switch presets in Graphic packs and restart the game
to compare.

## Credits

The technique follows [fadillzzz/mh3u-patches](https://github.com/fadillzzz/mh3u-patches),
a frame-rate patch for the 3DS version of MH3U, which shares much of its code with the Wii U
game.
