"""The admin dashboard page (GET / on the admin port): who's online, announcements and
planned restarts in one place. Self-contained (no external files or scripts); it reads
/players and /restart and posts to /announce and /restart on the same port.

Open it from your own PC through SSH, e.g.
    ssh -N -L 18081:127.0.0.1:8081 <user>@<server>     then http://localhost:18081/
"""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MH3U Server Admin</title>
<style>
  :root { --bg:#1d1e22; --panel:#272930; --line:#383b45; --text:#e4e2dc; --dim:#9a978f;
          --gold:#d2b06c; --ok:#7fbf8a; --warn:#e0a35a; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.45 system-ui, "Segoe UI", sans-serif; }
  main { max-width:1100px; margin:0 auto; padding:16px; }
  h1 { font-size:18px; margin:4px 0 2px; color:var(--gold); font-weight:600; }
  .sub { color:var(--dim); margin-bottom:14px; }
  section { background:var(--panel); border:1px solid var(--line); border-radius:8px;
            padding:12px 14px; margin-bottom:14px; }
  h2 { font-size:14px; margin:0 0 8px; color:var(--gold); font-weight:600; }
  table { width:100%; border-collapse:collapse; }
  th, td { text-align:left; padding:5px 8px; border-bottom:1px solid var(--line);
           white-space:nowrap; }
  th { color:var(--dim); font-weight:500; font-size:12px; }
  td.name { font-weight:600; }
  .scroll { overflow-x:auto; }
  .empty { color:var(--dim); padding:8px 0; }
  textarea, select, input, button { font:inherit; color:var(--text); background:#1a1b1f;
           border:1px solid var(--line); border-radius:6px; padding:6px 8px; }
  textarea { width:100%; min-height:56px; resize:vertical; }
  button { background:#3a3424; border-color:#6b5a35; cursor:pointer; }
  button:hover { background:#4a4230; }
  button.armed { background:#5a2e22; border-color:#a0533d; }
  .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:8px; }
  .msg { color:var(--dim); }
  .ok { color:var(--ok); } .warn { color:var(--warn); }
</style>
</head>
<body>
<main>
  <h1>MH3U Server Admin</h1>
  <div class="sub" id="summary">Loading...</div>

  <section>
    <h2>Online now</h2>
    <div class="scroll"><table>
      <thead><tr><th>Hunter</th><th>HR</th><th>Account</th><th>Game</th><th>Chat language</th>
        <th>Hall</th><th>Room</th><th>Online for</th><th>Master key</th></tr></thead>
      <tbody id="players"></tbody>
    </table></div>
    <div class="empty" id="noplayers" hidden>Nobody is online.</div>
  </section>

  <section>
    <h2>Announcement</h2>
    <textarea id="text" maxlength="360"
      placeholder="A chat message from Server to every hall and room (English)"></textarea>
    <div class="row">
      <select id="scope">
        <option value="all">Everyone</option>
        <option value="halls">Halls only</option>
        <option value="rooms">Rooms only</option>
      </select>
      <button id="send">Send</button>
      <span class="msg" id="sendmsg"></span>
    </div>
  </section>

  <section>
    <h2>Restart</h2>
    <div class="msg" id="restartstate"></div>
    <div class="row">
      <select id="wait">
        <option value="idle">when nobody is in a room</option>
        <option value="empty">when nobody is online</option>
        <option value="now">now (15 s warning)</option>
      </select>
      <label class="msg">give up waiting after
        <input id="maxmin" type="number" min="1" max="1440" value="60" style="width:70px"> min</label>
      <button id="restart">Schedule restart</button>
      <button id="cancel">Cancel</button>
      <span class="msg" id="restartmsg"></span>
    </div>
  </section>
</main>
<script>
"use strict";
const $ = (id) => document.getElementById(id);

function ago(s) {
  if (s == null) return "";
  if (s < 60) return s + " s";
  const m = Math.floor(s / 60);
  if (m < 60) return m + " min";
  return Math.floor(m / 60) + " h " + (m % 60) + " min";
}

function cell(text, cls) {
  const td = document.createElement("td");
  td.textContent = text == null ? "" : String(text);   // text only: names are player-made
  if (cls) td.className = cls;
  return td;
}

async function refresh() {
  try {
    const [p, r] = await Promise.all([
      fetch("/players").then((x) => x.json()),
      fetch("/restart").then((x) => x.json()),
    ]);
    const body = $("players");
    body.replaceChildren();
    for (const pl of p.players) {
      const tr = document.createElement("tr");
      const room = pl.room + (pl.room_password ? " (password " + pl.room_password + ")" : "");
      const key = document.createElement("button");
      key.textContent = pl.master_key ? "Take back" : "Give";
      if (pl.master_key) key.classList.add("armed");
      key.onclick = async () => {
        await fetch("/masterkey?player=" + pl.pid + "&on=" + (pl.master_key ? 0 : 1),
                    { method: "POST" });
        refresh();
      };
      const keycell = document.createElement("td");
      keycell.append(key);
      tr.append(cell(pl.hunter || "?", "name"), cell(pl.hr), cell(pl.account),
                cell(pl.game), cell(pl.language), cell(pl.hall), cell(room),
                cell(ago(pl.online_s)), keycell);
      body.append(tr);
    }
    $("noplayers").hidden = p.players.length > 0;
    const inRooms = p.players.filter((x) => x.room).length;
    $("summary").textContent = p.players.length + " online, " + p.rooms.length + " room" +
      (p.rooms.length === 1 ? "" : "s") + " (" + inRooms + " in rooms). Updated " +
      new Date().toLocaleTimeString() + ".";
    const st = $("restartstate");
    if (r.scheduled) {
      st.className = "warn";
      st.textContent = (r.firing ? "Restarting now." : "Restart pending (wait=" + r.wait +
        "), waiting " + ago(r.waiting_s) + ", gives up in " + ago(r.deadline_in_s) + ".");
    } else {
      st.className = "msg";
      st.textContent = "No restart scheduled.";
    }
  } catch (e) {
    $("summary").textContent = "Can't reach the server (" + e + "). Retrying...";
  }
}

$("send").onclick = async () => {
  const text = $("text").value.trim();
  if (!text) return;
  $("sendmsg").textContent = "Sending...";
  try {
    const r = await fetch("/announce?scope=" + $("scope").value, { method: "POST", body: text })
      .then((x) => x.json());
    if (r.error) throw new Error(r.error);
    $("sendmsg").className = "ok";
    $("sendmsg").textContent = "Sent to " + r.players + " player" + (r.players === 1 ? "" : "s") +
      " as " + r.messages + " chat message" + (r.messages === 1 ? "" : "s") + ".";
    $("text").value = "";
  } catch (e) {
    $("sendmsg").className = "warn";
    $("sendmsg").textContent = "Not sent: " + e.message;
  }
};

let armed = null;
$("restart").onclick = async () => {
  const b = $("restart");
  if (!armed) {                       // first click arms, second click (within 5 s) sends
    b.classList.add("armed");
    b.textContent = "Click again to confirm";
    armed = setTimeout(() => { armed = null; b.classList.remove("armed");
                               b.textContent = "Schedule restart"; }, 5000);
    return;
  }
  clearTimeout(armed); armed = null;
  b.classList.remove("armed"); b.textContent = "Schedule restart";
  const q = "wait=" + $("wait").value + "&max_minutes=" + encodeURIComponent($("maxmin").value);
  const r = await fetch("/restart?" + q, { method: "POST" }).then((x) => x.json());
  $("restartmsg").textContent = r.error ? "Not scheduled: " + r.error : "Scheduled.";
  refresh();
};

$("cancel").onclick = async () => {
  const r = await fetch("/restart/cancel", { method: "POST" }).then((x) => x.json());
  $("restartmsg").textContent = r.cancelled ? "Cancelled." : "Nothing to cancel.";
  refresh();
};

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""
