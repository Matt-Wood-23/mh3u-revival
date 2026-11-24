"""The admin dashboard page (GET / on the admin port): who's online, announcements,
planned restarts and play metrics in one place. Self-contained (no external files or
scripts); it reads /players, /restart and /metrics and posts to /announce and /restart on
the same port.

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
  /* Metrics */
  :root { --s1:#3987e5; --s2:#d95926; --tile:#22242a; --grid:#33363f; --base:#4a4d58;
          --critical:#d03b3b; }
  .mhead { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin:22px 0 10px; }
  .mhead h1 { margin:0; }
  .filters { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:14px; }
  .seg { display:inline-flex; border:1px solid var(--line); border-radius:6px; overflow:hidden; }
  .seg button { border:0; border-radius:0; background:#1a1b1f; padding:6px 12px; }
  .seg button + button { border-left:1px solid var(--line); }
  .seg button.on { background:#4a4230; color:var(--gold); font-weight:600; }
  #metrics.loading { opacity:.55; transition:opacity .2s; }
  .tiles { display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr));
           gap:10px; margin-bottom:14px; }
  .tile { background:var(--panel); border:1px solid var(--line); border-radius:8px;
          padding:10px 12px; min-width:0; }
  section .tile { background:var(--tile); }
  .tile .l { color:var(--dim); font-size:12px; }
  .tile .v { font-size:22px; font-weight:600; line-height:1.3; }
  .tile .n { color:var(--dim); font-size:12px; }
  h3 { font-size:12px; color:var(--dim); font-weight:500; margin:2px 0 8px; }
  .note { color:var(--dim); font-size:12px; margin:-4px 0 10px; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
  .grid3 { display:grid; grid-template-columns:repeat(3, 1fr); gap:18px; }
  .grid2 > div, .grid3 > div { min-width:0; }
  .geonote { margin:10px 0 18px; }
  .note a { color:var(--dim); }
  @media (max-width: 760px) { .grid2, .grid3 { grid-template-columns:1fr; } }
  .chart svg { display:block; width:100%; overflow:visible; }
  .chart text { fill:var(--dim); font-size:11px; font-variant-numeric:tabular-nums; }
  .chart .hit { fill:transparent; cursor:default; outline:none; }
  .chart .hit:hover, .chart .hit:focus { fill:rgba(255,255,255,.05); }
  .legend { display:flex; gap:16px; flex-wrap:wrap; color:var(--dim); font-size:12px;
            margin-bottom:6px; }
  .legend i { display:inline-block; width:10px; height:10px; border-radius:2px;
              margin-right:6px; vertical-align:-1px; }
  .heat { display:grid; grid-template-columns:34px repeat(24, minmax(0, 1fr)); gap:2px;
          align-items:center; }
  .heat .c { height:20px; border-radius:3px; outline:none; }
  .heat .c:hover, .heat .c:focus { box-shadow:0 0 0 2px var(--text) inset; }
  .heat .none { box-shadow:0 0 0 1px var(--line) inset; }
  .heat .lab { color:var(--dim); font-size:11px; white-space:nowrap; overflow:hidden; }
  .ramp { display:flex; align-items:center; gap:6px; color:var(--dim); font-size:12px;
          margin-top:8px; }
  .ramp span.sw { display:inline-block; width:18px; height:10px; border-radius:2px; }
  .bars .row { display:grid; grid-template-columns:minmax(80px, 34%) 1fr auto; gap:8px;
               align-items:center; margin:5px 0; font-size:13px; }
  .bars .lab { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .bars .track { height:12px; }
  .bars .fill { height:12px; background:var(--s1); border-radius:0 4px 4px 0; min-width:2px; }
  .bars .fill.zero { background:transparent; }
  .bars .val { color:var(--text); font-variant-numeric:tabular-nums; min-width:44px;
               text-align:right; }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
  td .alt { color:var(--dim); font-weight:400; margin-left:6px; }
  .inbar { display:inline-block; height:8px; background:var(--s1); border-radius:0 4px 4px 0;
           margin-left:8px; vertical-align:middle; }
  .crash { color:var(--text); }
  .crash::before { content:""; display:inline-block; width:8px; height:8px; border-radius:50%;
                   background:var(--critical); margin-right:6px; }
  details summary { color:var(--dim); cursor:pointer; font-size:12px; margin-top:8px; }
  .tip { position:fixed; z-index:10; pointer-events:none; background:#111216;
         border:1px solid var(--line); border-radius:6px; padding:6px 9px; font-size:12px;
         max-width:260px; }
  .tip strong { display:block; font-size:14px; color:var(--text); }
  .tip .tl { color:var(--dim); }
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

  <div class="mhead"><h1>Metrics</h1><span class="msg" id="mnote"></span></div>
  <div class="filters">
    <div class="seg" role="group" aria-label="Period">
      <button data-days="7">Last 7 days</button>
      <button data-days="30" class="on">Last 30 days</button>
      <button data-days="0">All time</button>
    </div>
    <span class="msg">Times and days are in your time zone. Leaderboard and names are
      for this page only.</span>
  </div>
  <div class="empty" id="metricsoff" hidden>Metrics are off on this server. They record on a
    public server (status page or Discord on), or with MH3U_METRICS=1.</div>
  <div id="metrics">
    <div class="tiles" id="tiles"></div>

    <section>
      <h2>Busiest hours</h2>
      <div class="note">Average players online, by weekday and hour</div>
      <div class="chart" id="heat"></div>
      <div class="ramp" id="heatramp"></div>
      <details><summary>Show as a table</summary><div class="scroll"><table id="heattable"></table></div></details>
    </section>

    <section>
      <h2>Players per day</h2>
      <div class="legend"><span><i style="background:var(--s1)"></i>Returning</span>
        <span><i style="background:var(--s2)"></i>New</span></div>
      <div class="chart" id="days"></div>
    </section>

    <section>
      <h2>Leaderboard</h2>
      <div class="note">Sorted by time in rooms (online time includes idling in town)</div>
      <div class="scroll"><table>
        <thead><tr><th class="num">#</th><th>Hunter</th><th class="num">HR</th>
          <th>Time in rooms</th><th class="num">Time online</th><th class="num">Sessions</th>
          <th>Last seen</th></tr></thead>
        <tbody id="board"></tbody>
      </table></div>
      <div class="empty" id="noboard" hidden>Nobody has played in this period.</div>
      <div class="row"><button id="boardmore">Show top 10</button></div>
    </section>

    <section>
      <h2>Connection health</h2>
      <div class="note">A join "stays" when the player is still in the room a minute later.
        Links are the player-to-player connections the server sets up when someone joins.</div>
      <div class="tiles" id="healthtiles"></div>
      <div class="grid2">
        <div><h3>Per day</h3><div class="scroll"><table>
          <thead><tr><th>Day</th><th class="num">Joins</th><th class="num">Stayed</th>
            <th class="num">Guest links up</th></tr></thead>
          <tbody id="healthdays"></tbody></table></div>
          <div class="empty" id="nohealth" hidden>No joins in this period.</div></div>
        <div><h3>Most failed joins</h3><div class="scroll"><table>
          <thead><tr><th>Hunter</th><th class="num">Failed</th><th class="num">Joins</th></tr></thead>
          <tbody id="trouble"></tbody></table></div>
          <div class="empty" id="notrouble" hidden>No failed joins.</div></div>
      </div>
    </section>

    <section>
      <h2>Where players are</h2>
      <div class="grid2">
        <div><h3>Players per country</h3><div class="bars" id="countries"></div></div>
        <div><h3>Players per state / province</h3><div class="bars" id="regions"></div></div>
      </div>
      <div class="note geonote" id="geonote"></div>
      <div class="grid3">
        <div><h3>Players per hall</h3><div class="bars" id="halls"></div></div>
        <div><h3>Round trip to the server (per player)</h3><div class="bars" id="rtt"></div>
          <div class="note" id="rttnote"></div></div>
        <div><h3>Game version</h3><div class="bars" id="games"></div></div>
      </div>
    </section>

    <section>
      <h2>Rooms</h2>
      <div class="tiles" id="roomtiles"></div>
      <div class="grid2">
        <div><h3>Most players at once</h3><div class="bars" id="roomsize"></div></div>
        <div><h3>Rooms per day</h3><div class="chart" id="roomdays"></div></div>
      </div>
    </section>

    <section>
      <h2>Relay traffic and chat</h2>
      <div class="grid2">
        <div><h3>Relay data sent per day</h3><div class="chart" id="relaydays"></div></div>
        <div><h3>Chat messages per day</h3><div class="chart" id="chatdays"></div></div>
      </div>
    </section>

    <section>
      <h2>Hunter rank and uptime</h2>
      <div class="grid2">
        <div><h3>Hunter rank (each player's latest)</h3><div class="bars" id="hr"></div></div>
        <div><h3>Server starts</h3><div class="tiles" id="uptiles"></div>
          <div class="scroll"><table>
            <thead><tr><th>Started</th><th>Why</th><th class="num">Down for</th></tr></thead>
            <tbody id="starts"></tbody></table></div></div>
      </div>
    </section>
  </div>
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

// --- Metrics (GET /metrics; metrics.py) ---------------------------------------
const S1 = "#3987e5", S2 = "#d95926", GRID = "#33363f", BASE = "#4a4d58";
const HEAT = ["#184f95", "#1c5cab", "#2a78d6", "#5598e7", "#86b6ef", "#b7d3f6"];
const ZERO = "#30333b";
const WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MX = { days: 30, data: null, top: 5 };

const tip = document.createElement("div");
tip.className = "tip";
tip.hidden = true;
document.body.append(tip);

function showTip(x, y, value, label) {
  const v = document.createElement("strong");
  v.textContent = value;
  const l = document.createElement("div");
  l.className = "tl";
  l.textContent = label;
  tip.replaceChildren(v, l);
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  let left = x + 14, top = y + 14;
  if (left + r.width > window.innerWidth - 8) left = x - r.width - 14;
  if (top + r.height > window.innerHeight - 8) top = y - r.height - 14;
  tip.style.left = Math.max(4, left) + "px";
  tip.style.top = Math.max(4, top) + "px";
}

function hover(node, text) {            // text() -> [value, label]; same on keyboard focus
  const [v0, l0] = text();
  node.setAttribute("tabindex", "0");
  node.setAttribute("aria-label", v0 + ", " + l0);
  node.addEventListener("pointermove", (e) => {
    const [v, l] = text();
    showTip(e.clientX, e.clientY, v, l);
  });
  node.addEventListener("pointerleave", () => { tip.hidden = true; });
  node.addEventListener("focus", () => {
    const r = node.getBoundingClientRect();
    const [v, l] = text();
    showTip(r.right, r.top, v, l);
  });
  node.addEventListener("blur", () => { tip.hidden = true; });
}

function svg(tag, attrs) {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text != null) e.textContent = String(text);   // text only: names are player-made
  if (cls) e.className = cls;
  return e;
}

const plural = (n, w) => n + " " + w + (n === 1 ? "" : "s");
const pct = (a, b) => (b ? Math.round((100 * a) / b) + "%" : "-");
const count = (v) => (v % 1 ? v.toFixed(1) : String(v));

function hrs(h) {
  if (h == null) return "";
  if (h < 1) return Math.round(h * 60) + " min";
  return (h < 10 ? h.toFixed(1) : String(Math.round(h))) + " h";
}

function bytes(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(n >= 1e10 ? 0 : 1) + " GB";
  if (n >= 1e6) return Math.round(n / 1e6) + " MB";
  if (n >= 1e3) return Math.round(n / 1e3) + " KB";
  return Math.round(n) + " B";
}

function dur(s) {
  if (s < 60) return Math.round(s) + " s";
  if (s < 3600) return Math.round(s / 60) + " min";
  return Math.floor(s / 3600) + " h " + Math.round((s % 3600) / 60) + " min";
}

function dayName(day, long) {           // "2026-11-22", already the viewer's own day
  return new Date(day + "T12:00:00Z").toLocaleDateString(undefined, long
    ? { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" }
    : { month: "short", day: "numeric", timeZone: "UTC" });
}

function when(t) {
  return new Date(t * 1000).toLocaleString(undefined,
    { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function seen(t, now) {
  const s = now - t;
  if (s < 90) return "Online now";
  if (s < 3600) return Math.round(s / 60) + " min ago";
  if (s < 86400) return Math.round(s / 3600) + " h ago";
  return new Date(t * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function hourName(h) {
  return h === 0 ? "12 am" : h < 12 ? h + " am" : h === 12 ? "12 pm" : (h - 12) + " pm";
}

function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

function barPath(x, y, w, h, r) {       // rounded data end, square at the baseline
  return "M" + x + "," + (y + h) + "V" + (y + r) + "Q" + x + "," + y + " " + (x + r) + "," + y +
    "H" + (x + w - r) + "Q" + (x + w) + "," + y + " " + (x + w) + "," + (y + r) +
    "V" + (y + h) + "Z";
}

// Columns, one per day; series stack bottom-up with a 2px gap.
function columns(box, rows, series, axis, value) {
  box.replaceChildren();
  if (!rows.length) { box.append(el("div", "No data yet.", "empty")); return; }
  const W = Math.max(240, box.clientWidth), H = 150, left = 44, bottom = 20, top = 8;
  const plotH = H - top - bottom, n = rows.length, band = (W - left) / n;
  const bw = Math.max(2, Math.min(24, band - 2));
  const totals = rows.map((r) => series.reduce((a, s) => a + (r[s.key] || 0), 0));
  const max = niceMax(Math.max(...totals));
  const s = svg("svg", { viewBox: "0 0 " + W + " " + H, height: H });
  for (const f of [0, 0.5, 1]) {
    const y = top + plotH * (1 - f);
    s.append(svg("line", { x1: left, x2: W, y1: y, y2: y, stroke: f ? GRID : BASE,
                           "stroke-width": 1 }));
    const t = svg("text", { x: left - 6, y: y + 4, "text-anchor": "end" });
    t.textContent = axis(max * f);
    s.append(t);
  }
  const every = Math.ceil(n / Math.max(1, Math.floor((W - left) / 60)));
  rows.forEach((r, i) => {
    const x = left + band * i + (band - bw) / 2;
    let y = top + plotH;
    const parts = series.filter((sr) => (r[sr.key] || 0) > 0);
    parts.forEach((sr, j) => {
      const h = (r[sr.key] / max) * plotH;
      const gap = j > 0 ? 2 : 0;
      const hh = h - gap;
      if (hh >= 0.5) {
        const rad = j === parts.length - 1 ? Math.min(4, bw / 2, hh) : 0;
        s.append(svg("path", { d: barPath(x, y - h, bw, hh, rad), fill: sr.color }));
      }
      y -= h;
    });
    if ((n - 1 - i) % every === 0) {
      const t = svg("text", { x: left + band * i + band / 2, y: H - 4, "text-anchor": "middle" });
      t.textContent = dayName(r.day);
      s.append(t);
    }
    const hit = svg("rect", { x: left + band * i, y: top, width: band, height: plotH,
                              class: "hit" });
    hover(hit, () => [value(totals[i]), dayName(r.day, true) + (series.length > 1
      ? " (" + series.map((sr) => sr.label + " " + (r[sr.key] || 0)).join(", ") + ")" : "")]);
    s.append(hit);
  });
  box.append(s);
}

function heatmap(box, rampBox, table, grid) {
  box.replaceChildren();
  rampBox.replaceChildren();
  table.replaceChildren();
  const vals = grid.flat().filter((v) => v != null);
  if (!vals.length) { box.append(el("div", "No hours recorded yet.", "empty")); return; }
  const max = Math.max(...vals);
  const color = (v) => (v <= 0 ? ZERO
    : HEAT[Math.min(HEAT.length - 1, Math.floor((v / max) * HEAT.length - 0.000001))]);
  const wrap = el("div", null, "heat");
  wrap.append(el("div", "", "lab"));
  for (let h = 0; h < 24; h += 3) {      // each label spans its three hours
    const lab = el("div", hourName(h), "lab");
    lab.style.gridColumn = "span 3";
    wrap.append(lab);
  }
  grid.forEach((row, d) => {
    wrap.append(el("div", WD[d], "lab"));
    row.forEach((v, h) => {
      const c = el("div", null, "c");
      if (v == null) c.classList.add("none");
      else c.style.background = color(v);
      hover(c, () => [v == null ? "No data" : v.toFixed(1) + " players on average",
                      WD[d] + ", " + hourName(h) + " to " + hourName((h + 1) % 24)]);
      wrap.append(c);
    });
  });
  box.append(wrap);
  rampBox.append(el("span", "0"));
  for (const c of [ZERO, ...HEAT]) {
    const sw = el("span", null, "sw");
    sw.style.background = c;
    rampBox.append(sw);
  }
  rampBox.append(el("span", max.toFixed(1) + " players"),
                 el("span", "· outlined: not recorded (before metrics began, or server off)"));
  const head = document.createElement("tr");
  head.append(el("th", "Hour"), ...WD.map((d) => el("th", d, "num")));
  table.append(head);
  for (let h = 0; h < 24; h++) {
    const tr = document.createElement("tr");
    tr.append(el("td", hourName(h)),
              ...grid.map((row) => el("td", row[h] == null ? "" : row[h].toFixed(1), "num")));
    table.append(tr);
  }
}

function barList(box, rows, fmt) {      // rows: [[label, value]]
  box.replaceChildren();
  if (!rows.length) { box.append(el("div", "No data yet.", "empty")); return; }
  const max = Math.max(1, ...rows.map((r) => r[1]));
  for (const [label, v] of rows) {
    const row = el("div", null, "row");
    const track = el("div", null, "track");
    const fill = el("div", null, "fill" + (v ? "" : " zero"));
    fill.style.width = (100 * v) / max + "%";
    track.append(fill);
    const lab = el("div", label, "lab");
    lab.title = label;                    // the full text when it's cut short
    row.append(lab, track, el("div", fmt(v), "val"));
    box.append(row);
  }
}

let regionNames = null;
try { regionNames = new Intl.DisplayNames(["en"], { type: "region" }); } catch (e) { /* old browser */ }
function countryName(cc) {
  try { return (regionNames && regionNames.of(cc)) || cc; } catch (e) { return cc; }
}

function geoNote(box, w) {
  box.replaceChildren();
  if (!w.geoip && !(w.countries || []).length) {
    box.append("No location database on the server yet (deploy/geoip_update.py builds it).");
    return;
  }
  let t = "From the address each player connects from; only the country and state / " +
    "province are kept.";
  if (w.unlocated) t += " " + plural(w.unlocated, "player") + " not located (LAN or VPN " +
    "address, or only played before locations were recorded).";
  if (w.region_count > (w.regions || []).length)
    t += " Top " + w.regions.length + " of " + w.region_count + " states / provinces.";
  const a = el("a", "IP Geolocation by DB-IP");
  a.href = "https://db-ip.com";
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  box.append(t + " ", a);
}

function tiles(box, items) {            // [label, value, note]
  box.replaceChildren();
  for (const [label, value, note] of items) {
    const t = el("div", null, "tile");
    t.append(el("div", label, "l"), el("div", value, "v"));
    if (note) t.append(el("div", note, "n"));
    box.append(t);
  }
}

function renderMetrics() {
  const d = MX.data;
  if (!d) return;
  $("metricsoff").hidden = !!d.enabled;
  $("metrics").hidden = !d.enabled;
  if (!d.enabled) return;
  const p = d.players, period = d.days ? "last " + d.days + " days" : "all time";
  $("mnote").textContent = "Recorded since " + new Date(d.since * 1000).toLocaleDateString(
    undefined, { month: "long", day: "numeric", year: "numeric" }) + ".";
  const pk = d.peak.all;
  tiles($("tiles"), [
    ["Players today", p.today],
    ["Last 7 days", p.week],
    ["Last 30 days", p.month],
    ["All time", p.all],
    ["New, " + period, p.new_period, p.returning.eligible
      ? pct(p.returning.returned, p.returning.eligible) + " came back within a week" : null],
    ["Most online at once", pk.players,
     (pk.t ? when(pk.t) + " · " : "") + "today " + d.peak.today],
    ["Median session", d.sessions.median_min == null ? "-" : d.sessions.median_min + " min",
     plural(d.sessions.count, "session")],
  ]);

  heatmap($("heat"), $("heatramp"), $("heattable"), d.busiest.heat);

  columns($("days"), p.days.map((r) => ({ day: r.day, returning: r.unique - r.new, new: r.new })),
          [{ key: "returning", label: "returning", color: S1 },
           { key: "new", label: "new", color: S2 }],
          count, (v) => plural(v, "player"));

  const body = $("board");
  body.replaceChildren();
  const topRoom = Math.max(0.01, ...d.leaderboard.map((r) => r.room_h));
  d.leaderboard.slice(0, MX.top).forEach((r, i) => {
    const tr = document.createElement("tr");
    const name = el("td", r.name, "name");
    if (r.others.length) name.append(el("span", "also " + r.others.join(", "), "alt"));
    const room = el("td", hrs(r.room_h));
    const bar = el("span", null, "inbar");
    bar.style.width = Math.round((80 * r.room_h) / topRoom) + "px";
    room.append(bar);
    tr.append(el("td", i + 1, "num"), name, el("td", r.hr == null ? "" : r.hr, "num"), room,
              el("td", hrs(r.online_h), "num"), el("td", r.sessions, "num"),
              el("td", seen(r.last_seen, d.now)));
    body.append(tr);
  });
  $("noboard").hidden = d.leaderboard.length > 0;
  $("boardmore").hidden = d.leaderboard.length <= 5;
  $("boardmore").textContent = MX.top === 5 ? "Show top 10" : "Show top 5";

  const h = d.health, how = h.how || {};
  const usual = (x) => (x.median_s != null ? " · usually " + x.median_s + " s" : "");
  tiles($("healthtiles"), [
    ["Joins that stayed", pct(h.stayed, h.joins), h.stayed + " of " + h.joins +
      (h.joins > h.stayed ? " · dropped " + (how.logout || 0) + ", backed out " +
       (how.left || 0) : "")],
    ["Guest-to-guest links up", pct(h.guest.ok, h.guest.n),
     h.guest.ok + " of " + h.guest.n + usual(h.guest)],
    ["Host links up", pct(h.host.ok, h.host.n), h.host.ok + " of " + h.host.n + usual(h.host)],
    ["Dropped from a room", d.sessions.dropped, "disconnected with others still in it"],
    ["Short sessions", d.sessions.short, "under 2 minutes, of " + d.sessions.count],
  ]);
  const hd = $("healthdays");
  hd.replaceChildren();
  const hdays = h.days.filter((r) => r.joins || r.guest).reverse();
  for (const r of hdays) {
    const tr = document.createElement("tr");
    tr.append(el("td", dayName(r.day, true)), el("td", r.joins, "num"),
              el("td", r.stayed + " (" + pct(r.stayed, r.joins) + ")", "num"),
              el("td", r.guest ? r.guest_ok + " of " + r.guest : "", "num"));
    hd.append(tr);
  }
  $("nohealth").hidden = hdays.length > 0;
  const tb = $("trouble");
  tb.replaceChildren();
  for (const r of h.trouble) {
    const tr = document.createElement("tr");
    tr.append(el("td", r.name, "name"), el("td", r.failed, "num"), el("td", r.joins, "num"));
    tb.append(tr);
  }
  $("notrouble").hidden = h.trouble.length > 0;

  const w = d.where;
  barList($("countries"), (w.countries || []).map((r) => [countryName(r.cc), r.players]),
          (v) => plural(v, "player"));
  barList($("regions"), (w.regions || []).map((r) => [r.region + ", " + r.cc, r.players]),
          (v) => plural(v, "player"));
  geoNote($("geonote"), w);
  barList($("halls"), w.halls.map((r) => [r.hall, r.players]), (v) => plural(v, "player"));
  barList($("rtt"), w.rtt.buckets.map((r) => [r.label, r.players]), (v) => plural(v, "player"));
  $("rttnote").textContent = w.rtt.players ? "Median " + w.rtt.median + " ms; " +
    w.rtt.over_150 + " of " + w.rtt.players + " players are 150 ms or more away." : "";
  barList($("games"), Object.entries(w.games), (v) => plural(v, "player"));

  const rm = d.rooms, big = rm.size[2].rooms + rm.size[3].rooms;
  tiles($("roomtiles"), [
    ["Rooms", rm.count],
    ["Reached 3 or 4 players", pct(big, rm.count), big + " of " + rm.count],
    ["Cross-version rooms", rm.cross_version, "JP and US/EU players together"],
  ]);
  barList($("roomsize"), rm.size.map((r) => [r.label, r.rooms]), (v) => plural(v, "room"));
  columns($("roomdays"), rm.days, [{ key: "rooms", label: "rooms", color: S1 }],
          count, (v) => plural(v, "room"));
  columns($("relaydays"), d.daily, [{ key: "relay_out", label: "sent", color: S1 }],
          bytes, bytes);
  columns($("chatdays"), d.daily, [{ key: "chat", label: "messages", color: S1 }],
          count, (v) => plural(v, "message"));

  barList($("hr"), d.hr.map((r) => [r.label, r.players]), (v) => plural(v, "player"));
  const u = d.uptime;
  tiles($("uptiles"), [["Starts", u.starts], ["Crashes", u.crashes, "stopped without warning"]]);
  const st = $("starts");
  st.replaceChildren();
  for (const r of u.last) {
    const tr = document.createElement("tr");
    tr.append(el("td", when(r.t)), el("td", r.crash ? "Crash" : "Restart", r.crash ? "crash" : ""),
              el("td", r.down_s == null ? "" : dur(r.down_s), "num"));
    st.append(tr);
  }
}

async function loadMetrics() {
  $("metrics").classList.add("loading");          // keep the old numbers while loading
  try {
    const tz = new Date().getTimezoneOffset();
    MX.data = await fetch("/metrics?days=" + MX.days + "&tz=" + tz).then((x) => x.json());
    renderMetrics();
  } catch (e) {
    $("mnote").textContent = "Can't load metrics (" + e + ").";
  } finally {
    $("metrics").classList.remove("loading");
  }
}

document.querySelectorAll(".seg button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll(".seg button").forEach((x) => x.classList.toggle("on", x === b));
    MX.days = Number(b.dataset.days);
    loadMetrics();
  };
});
$("boardmore").onclick = () => { MX.top = MX.top === 5 ? 10 : 5; renderMetrics(); };
let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(renderMetrics, 150);
});
loadMetrics();
setInterval(loadMetrics, 60000);
</script>
</body>
</html>
"""
