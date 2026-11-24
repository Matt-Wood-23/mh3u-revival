# Event quests

The quests in this folder are the official event quests. The launcher adds them to your game
when you press **Save + Play** (Join tab, "Add the official event quests to my game", on by
default), and they show up with the other event quests at the Quest Counter. Online, event
quests come from the room's host, so the others in the room don't need them.

They work on the US and EU games. The Japanese game isn't supported yet.

## Make your own and send it in

Anyone can make an event quest and send it in to be added to the list.

1. **Get [MH3U Quest Studio](https://github.com/Matt-Wood-23/mh3u-quest-studio/releases)**,
   the quest editor.
2. **Open a quest pack.** Close the game first. In Quest Studio, open the **Cemu save packs**
   menu and pick `quest1` or `quest3` under your MH3U Online folder. If the folder
   isn't listed, use **Add a Cemu folder…** and pick the folder that has `MH3U_Online.exe` in
   it. The game's Event Quests list only reads `quest1` and `quest3`: a quest in `quest2`
   never shows, and `quest4` is for arena quests. Keep a pack's quests together from the
   first slot: the game reads only as many slots from the start as the pack has quests, so
   an empty slot in between hides the last quest.
3. **Click New quest…** and pick an event quest to copy. The official ones (A Golden Welcome,
   The Gilded King, The Little Queen) are good starting points. Edit your copy, not the
   official quest itself: the launcher leaves a quest you've changed alone, so you would stop
   getting its updates.
4. **Give it a number** from the block for its rank. The number decides which rank's list
   the game shows it in:

   | Rank      | Quest numbers |
   |-----------|---------------|
   | Low rank  | 20150–20199   |
   | High rank | 20250–20299   |
   | G rank    | 20350–20399   |

   Don't use a number that's already a `q_<number>.quest` file in this folder. Capcom's own
   event quests use other numbers from 20100–20399, so stay inside these blocks.
5. **Set it up**: monsters, difficulty, rewards and text. Quest Studio shows the real HP and
   attack numbers for each difficulty, and warns about things the game can't handle, like
   text that's too long. Fix every warning before you send it.
   - **Text**: the game shows the language it's set to (English, French, German, Italian or
     Spanish). Write at least the English; the other languages are welcome. Leave none of
     them with the copied quest's old text.
   - **Fair for its rank**: keep the monster, difficulty and rewards in line with the rank
     and star level you picked.
6. **Play it all the way through**, ideally once online with a friend as well.
7. **Send it in**: select your quest in Quest Studio and click **Export quest…**. It saves
   just your quest as one file, named after its number (for example `q_20360.quest`). Then
   either:
   - open an issue with the
     [event quest form](https://github.com/Matt-Wood-23/mh3u-revival/issues/new?template=event_quest.yml)
     and attach the file in a zip (GitHub doesn't take `.quest` files), or
   - post it on the [Discord](https://discord.gg/HTEWJDYgzJ).

   With an older Quest Studio that has no **Export quest…**, send the whole pack file instead
   (for example `quest1`, from `portable\mlc01\usr\save\00050000\10118300\user\80000001\` in
   your MH3U Online folder, or `10117200` instead of `10118300` for the EU game) in a zip, and
   say which quest in it is yours (its number and name).

**What happens next:** every quest is tested before it goes on the list, and its number,
text, difficulty or rewards may be changed. Quests with offensive text, or copied from
someone else's work without asking, won't be added. By sending a quest you agree that it can
be shared here under the project's license ([AGPL-3.0](../LICENSE)).

Once it's on the list, everyone with the launcher gets it the next time they press Save +
Play. Then delete your own copy (**Delete quest** in Quest Studio), so you get the official
version and its updates: the launcher won't add a quest when you already have one with the
same number.

## For maintainers: adding a quest

1. Unzip the submission if it's zipped, then add the quest from the exported `.quest` file
   (or pull it out of a pack file, the same way):

   ```
   python events/update_list.py --add <.quest or pack file> <quest number> [--as <new number>]
   ```

   This writes `events/q_<number>.quest` and rebuilds `events.json`. Use `--as` to give it a
   new number when its own is taken or outside the blocks above.
2. Open the `.quest` file in Quest Studio (it opens loose `.quest` files) and check it.
3. Test it in game. To try the launcher's download path without publishing, serve this
   folder (`python -m http.server 8090` from inside `events/`) and start the launcher with
   `MH3U_EVENTS_BASE=http://127.0.0.1:8090`.
4. Commit the `.quest` file and `events.json`. Players get it the next time they press Save +
   Play.

To end an event, delete its file, run `python events/update_list.py`, and commit. The launcher
then removes the quest from players' packs, unless they've edited it.
