/* 2D pixel-art office: walking avatars, hover stats. Pause when hidden, cap 30fps. */
(() => {
  const TILE = 16;
  const COLS = 40, ROWS = 22;
  const FPS = 30;
  const canvas = document.getElementById("c");
  const ctx = canvas.getContext("2d");
  const tipEl = document.getElementById("tip");
  const view = document.getElementById("view");

  const ROOMS = [
    { id: "lead", title: "مدیریت", x: 1, y: 1, w: 12, h: 10, floor: "#3d2a6b", wall: "#6b4dff" },
    { id: "eng", title: "مهندسی", x: 14, y: 1, w: 12, h: 10, floor: "#1d3a4a", wall: "#2ec8c8" },
    { id: "sci", title: "علم", x: 27, y: 1, w: 12, h: 10, floor: "#1e3a2a", wall: "#3dcc7a" },
    { id: "soc", title: "جامعه", x: 1, y: 12, w: 18, h: 9, floor: "#3a2a1c", wall: "#f0a92e" },
    { id: "ops", title: "عملیات", x: 20, y: 12, w: 19, h: 9, floor: "#2a1e3a", wall: "#ef6b8a" },
  ];
  const HALL = { x: 13, y: 11, w: 14, h: 1 }; // corridor strip

  const PAL = ["#7c6cff", "#2fbf71", "#2ec8c8", "#f0a92e", "#ef4b5b", "#6b8cff", "#c084fc", "#fb7185"];
  const SKIN = ["#f1c27d", "#e0ac69", "#c68642", "#8d5524", "#ffdbac"];
  const HAIR = ["#1a1a1a", "#4a3728", "#8b5a2b", "#d4a017", "#c0392b", "#3d3d5c"];

  let scale = 2, offX = 0, offY = 0;
  let last = 0, acc = 0;
  let hidden = false;
  let hoverName = null;
  let pinName = null;
  let mouse = { x: 0, y: 0 };
  let state = { desks: [], messages: [], running: false, status: "idle", topic: "", office: {}, usage: {} };
  let score = { employees: {} };
  let project = { goal: "", started_at: "", progress: 0, eta: "" };
  let lastEventId = "";
  const avatars = new Map(); // name -> sprite state

  function hash(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function pick(arr, h) { return arr[h % arr.length]; }

  function roomForRole(role, seat, i) {
    if (seat === "boss" || seat === "secretary" || role === "boss" || role === "secretary") return "lead";
    if (role === "optimizer" || role === "inspector") return "ops";
    const map = { researcher: "sci", programmer: "eng", engineer: "eng", coder: "eng", critic: "soc", psychologist: "soc", philosopher: "sci", scientist: "sci", lawyer: "soc", journalist: "soc", historian: "sci", economist: "ops" };
    if (map[role]) return map[role];
    return ROOMS[1 + (i % (ROOMS.length - 1))].id;
  }

  function desksInRoom(roomId, n) {
    const r = ROOMS.find((x) => x.id === roomId);
    const spots = [];
    const cols = Math.max(3, Math.min(5, r.w - 3));
    const count = Math.max(n || 3, 3);
    for (let i = 0; i < count; i++) {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const x = r.x + 2 + col * 2;
      const y = r.y + 2 + row * 3;
      spots.push({ x, y, px: x * TILE + 2, py: y * TILE });
    }
    return spots;
  }

  function walkable(tx, ty) {
    if (tx < 0 || ty < 0 || tx >= COLS || ty >= ROWS) return false;
    for (const r of ROOMS) {
      if (tx > r.x && tx < r.x + r.w - 1 && ty > r.y && ty < r.y + r.h - 1) return true;
    }
    // hallway between rooms
    if (ty === 11 && tx >= 1 && tx <= 38) return true;
    return false;
  }

  function bfs(sx, sy, gx, gy) {
    const key = (x, y) => x + "," + y;
    const q = [[sx, sy]];
    const prev = new Map();
    prev.set(key(sx, sy), null);
    const dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
    while (q.length) {
      const [x, y] = q.shift();
      if (x === gx && y === gy) break;
      for (const [dx, dy] of dirs) {
        const nx = x + dx, ny = y + dy;
        const k = key(nx, ny);
        if (prev.has(k) || !walkable(nx, ny)) continue;
        prev.set(k, [x, y]);
        q.push([nx, ny]);
      }
    }
    if (!prev.has(key(gx, gy))) return [];
    const path = [];
    let cur = [gx, gy];
    while (cur) {
      path.push(cur);
      cur = prev.get(key(cur[0], cur[1]));
    }
    path.reverse();
    return path;
  }

  function ensureAvatar(d, i) {
    let a = avatars.get(d.name);
    const room = roomForRole(d.role, d.seat, i);
    const used = [...avatars.values()].filter((v) => v.room === room && v.name !== d.name).length;
    const spots = desksInRoom(room, used + 4);
    const spot = spots[Math.min(used, spots.length - 1)];
    if (!a) {
      const h = hash(d.name);
      a = {
        name: d.name,
        role: d.role,
        role_title: d.role_title || d.role,
        seat: d.seat,
        present: !!d.present,
        room,
        homeX: spot.x,
        homeY: spot.y + 2,
        tx: spot.x,
        ty: spot.y + 2,
        x: spot.x * TILE,
        y: (spot.y + 2) * TILE,
        path: [],
        frame: 0,
        dir: 0, // 0 down 1 left 2 right 3 up
        idle: 0,
        bubble: "",
        bubbleT: 0,
        mood: d.present ? "idle" : "absent",
        shirt: pick(PAL, h),
        skin: pick(SKIN, h >> 3),
        hair: pick(HAIR, h >> 7),
        delivering: false,
      };
      avatars.set(d.name, a);
    } else {
      a.present = !!d.present;
      a.role = d.role;
      a.role_title = d.role_title || d.role;
      a.seat = d.seat;
    }
    return a;
  }

  function setPath(a, gx, gy) {
    const sx = Math.round(a.x / TILE), sy = Math.round(a.y / TILE);
    a.path = bfs(sx, sy, gx, gy).slice(1);
  }

  function goHome(a) { setPath(a, a.homeX, a.homeY); a.delivering = false; }

  function walkToBoss(a, text) {
    const boss = [...avatars.values()].find((v) => v.seat === "boss") || [...avatars.values()].find((v) => v.role === "boss");
    const r = ROOMS.find((x) => x.id === "lead");
    const gx = boss ? Math.round(boss.x / TILE) : r.x + 6;
    const gy = boss ? Math.round(boss.y / TILE) + 1 : r.y + 6;
    setPath(a, gx, gy);
    a.delivering = true;
    a.bubble = text || "{}";
    a.bubbleT = 8;
    a.mood = "work";
  }

  function tick(dt) {
    for (const a of avatars.values()) {
      if (!a.present) continue;
      a.idle += dt;
      a.frame += dt * 8;
      if (a.bubbleT > 0) a.bubbleT -= dt;
      if (a.path.length) {
        const [nx, ny] = a.path[0];
        const px = nx * TILE, py = ny * TILE;
        const dx = px - a.x, dy = py - a.y;
        const sp = 56 * dt;
        if (Math.abs(dx) + Math.abs(dy) <= sp) {
          a.x = px; a.y = py; a.path.shift();
          if (!a.path.length && a.delivering) {
            a.bubbleT = 2.5;
            a.mood = "ok";
            setTimeout(() => goHome(a), 700);
          }
        } else {
          const len = Math.hypot(dx, dy) || 1;
          a.x += (dx / len) * sp;
          a.y += (dy / len) * sp;
          a.dir = Math.abs(dx) > Math.abs(dy) ? (dx < 0 ? 1 : 2) : (dy < 0 ? 3 : 0);
        }
      } else if (a.idle > 4 + (hash(a.name) % 6) && a.mood !== "work") {
        // wander inside own room
        const r = ROOMS.find((x) => x.id === a.room);
        if (r) {
          const gx = r.x + 2 + ((hash(a.name + String(a.idle | 0)) % (r.w - 4)));
          const gy = r.y + 3 + ((hash(a.name + "y" + String(a.idle | 0)) % (r.h - 5)));
          if (walkable(gx, gy)) setPath(a, gx, gy);
        }
        a.idle = 0;
      }
    }
  }

  function px(x, y, w, h, color) {
    ctx.fillStyle = color;
    ctx.fillRect(x | 0, y | 0, w, h);
  }

  function drawTileFloor(r) {
    for (let y = r.y; y < r.y + r.h; y++) {
      for (let x = r.x; x < r.x + r.w; x++) {
        const light = ((x + y) & 1) === 0;
        px(x * TILE, y * TILE, TILE, TILE, light ? r.floor : shade(r.floor, -12));
      }
    }
    // walls
    ctx.strokeStyle = r.wall;
    ctx.lineWidth = 2;
    ctx.strokeRect(r.x * TILE + 1, r.y * TILE + 1, r.w * TILE - 2, r.h * TILE - 2);
    // door gap on south or north
    const doorX = (r.x + Math.floor(r.w / 2)) * TILE;
    const doorY = (r.y + r.h - 1) * TILE;
    px(doorX - 8, doorY, 16, TILE, r.floor);
    // title
    ctx.fillStyle = r.wall;
    ctx.font = "8px monospace";
    ctx.textAlign = "right";
    ctx.fillText(r.title, (r.x + r.w) * TILE - 4, r.y * TILE + 10);
  }

  function shade(hex, d) {
    const n = parseInt(hex.slice(1), 16);
    const r = Math.max(0, Math.min(255, ((n >> 16) & 255) + d));
    const g = Math.max(0, Math.min(255, ((n >> 8) & 255) + d));
    const b = Math.max(0, Math.min(255, (n & 255) + d));
    return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
  }

  function drawDesk(x, y, present, color) {
    // desk + computer, pixel
    px(x, y + 8, 20, 8, present ? "#5a4632" : "#3a3a44");
    px(x + 2, y + 6, 16, 3, present ? "#3a2a1c" : "#2a2a32");
    px(x + 6, y, 8, 6, present ? "#1a2030" : "#222");
    px(x + 7, y + 1, 6, 4, present ? color : "#555");
    px(x + 9, y + 6, 2, 2, "#888");
  }

  function drawAvatar(a) {
    const x = Math.round(a.x), y = Math.round(a.y);
    const walk = a.path.length && ((a.frame | 0) % 2);
    const bob = walk ? 1 : 0;
    if (!a.present) {
      // empty grey silhouette
      px(x + 5, y + 4, 6, 6, "#5a5a66");
      px(x + 4, y + 10, 8, 8, "#4a4a55");
      return;
    }
    // shadow
    px(x + 4, y + 20, 8, 2, "rgba(0,0,0,.35)");
    // legs
    const swing = walk ? 2 : 0;
    px(x + 5 - swing, y + 16 - bob, 3, 5, "#2a2a40");
    px(x + 8 + swing, y + 16 - bob, 3, 5, "#2a2a40");
    // body
    px(x + 4, y + 9 - bob, 8, 8, a.shirt);
    px(x + 4, y + 9 - bob, 8, 2, shade(a.shirt, 20));
    // head
    px(x + 5, y + 3 - bob, 6, 6, a.skin);
    // hair
    if (a.dir !== 0) px(x + 5, y + 2 - bob, 6, 3, a.hair);
    else { px(x + 4, y + 2 - bob, 8, 3, a.hair); px(x + 5, y + 1 - bob, 6, 2, a.hair); }
    // eyes
    if (a.dir !== 3) {
      px(x + 6, y + 5 - bob, 1, 1, "#1a1a1a");
      px(x + 9, y + 5 - bob, 1, 1, "#1a1a1a");
    }
    // mood icon
    const st = statsOf(a.name);
    const mood = moodOf(a, st);
    const col = { work: "#f0a92e", ok: "#2fbf71", tired: "#ef4b5b", sad: "#8b6bff", idle: "#7c6cff", talk: "#2ec8c8" }[mood] || "#aaa";
    px(x + 6, y - 3, 4, 3, col);
    // name
    ctx.fillStyle = "#eef0f6";
    ctx.font = "7px monospace";
    ctx.textAlign = "center";
    ctx.fillText(a.name.split(" ")[0].slice(0, 12), x + 8, y + 24);
    // bubble
    if (a.bubbleT > 0 && a.bubble) {
      const t = a.bubble.replace(/\s+/g, " ").slice(0, 22);
      ctx.font = "8px monospace";
      const w = Math.max(24, ctx.measureText(t).width + 8);
      px(x + 8 - w / 2, y - 16, w, 11, "#fff");
      ctx.fillStyle = "#111";
      ctx.textAlign = "center";
      ctx.fillText(t, x + 8, y - 8);
    }
  }

  function statsOf(name) {
    const e = (score.employees || {})[name] || {};
    const a = avatars.get(name) || {};
    const thinking = (state.thinking || {}).name === name;
    return {
      role: e.role_title || a.role_title || a.role || "—",
      seat: e.seat || a.seat || "employee",
      current: thinking ? (state.status || "در حال کار") : (e.current_work || a.bubble || (a.present ? "آماده" : "غایب")),
      fatigue: num(e.fatigue),
      frustration: num(e.frustration),
      usefulness: num(e.usefulness),
      harm: num(e.harm),
      contribution: e.contribution ?? e.session_tokens ?? 0,
      tokens: e.session_tokens || 0,
      present: a.present,
    };
  }
  function num(v) { v = Number(v); return Number.isFinite(v) ? v : 0; }
  function moodOf(a, st) {
    if (!a.present) return "absent";
    if ((state.thinking || {}).name === a.name) return "work";
    if (st.fatigue >= 70) return "tired";
    if (st.frustration >= 50) return "sad";
    if (st.usefulness >= 40) return "ok";
    if (a.bubbleT > 0) return "talk";
    return a.mood || "idle";
  }

  function hitTest(mx, my) {
    // canvas pixel coords
    let best = null, bestD = 18;
    for (const a of avatars.values()) {
      const d = Math.hypot(mx - (a.x + 8), my - (a.y + 10));
      if (d < bestD) { bestD = d; best = a.name; }
    }
    return best;
  }

  function showTip(name, cx, cy) {
    const st = statsOf(name);
    const a = avatars.get(name);
    tipEl.style.display = "block";
    tipEl.innerHTML = `<h4>${esc(name)}</h4>
      <div class="kv"><span>نقش</span><b>${esc(st.role)} · ${esc(st.seat)}</b></div>
      <div class="kv"><span>کار فعلی</span><b>${esc(String(st.current).slice(0, 80))}</b></div>
      <div>خستگی ${st.fatigue.toFixed(0)}</div><div class="bar fat"><i style="width:${clamp(st.fatigue)}%"></i></div>
      <div>سرخوردگی ${st.frustration.toFixed(0)}</div><div class="bar fru"><i style="width:${clamp(st.frustration)}%"></i></div>
      <div>سودمندی ${st.usefulness.toFixed(0)}</div><div class="bar use"><i style="width:${clamp(st.usefulness)}%"></i></div>
      <div>آسیب ${st.harm.toFixed(0)}</div><div class="bar harm"><i style="width:${clamp(st.harm)}%"></i></div>
      <div class="kv"><span>سهم / توکن</span><b>${st.contribution} · ${st.tokens}</b></div>
      <div class="kv"><span>وضعیت</span><b>${a && a.present ? "حاضر" : "غایب"}</b></div>`;
    const rect = view.getBoundingClientRect();
    let left = cx + 16, top = cy - 10;
    if (left + 280 > rect.width) left = cx - 290;
    if (top + 260 > rect.height) top = cy - 220;
    tipEl.style.left = Math.max(8, left) + "px";
    tipEl.style.top = Math.max(8, top) + "px";
  }
  function hideTip() { if (!pinName) tipEl.style.display = "none"; }
  function clamp(n) { return Math.max(0, Math.min(100, n)); }
  function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  function layout() {
    const w = view.clientWidth, h = view.clientHeight;
    const sw = Math.max(1, Math.floor(w / (COLS * TILE)));
    const sh = Math.max(1, Math.floor(h / (ROWS * TILE)));
    scale = Math.max(1, Math.min(sw, sh));
    canvas.width = w;
    canvas.height = h;
    ctx.imageSmoothingEnabled = false;
    offX = Math.floor((w - COLS * TILE * scale) / 2);
    offY = Math.floor((h - ROWS * TILE * scale) / 2);
  }

  function draw() {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = "#120c1e";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(scale, 0, 0, scale, offX, offY);
    ctx.imageSmoothingEnabled = false;
    // hallway
    for (let x = 1; x < COLS - 1; x++) {
      px(x * TILE, 11 * TILE, TILE, TILE, ((x + 11) & 1) ? "#2a2438" : "#241e32");
    }
    for (const r of ROOMS) drawTileFloor(r);
    // desks under avatars
    let i = 0;
    const byRoom = {};
    for (const a of avatars.values()) {
      byRoom[a.room] = byRoom[a.room] || 0;
      const idx = byRoom[a.room]++;
      const spots = desksInRoom(a.room, idx + 1);
      const s = spots[Math.min(idx, spots.length - 1)];
      drawDesk(s.px, s.py, a.present, a.shirt);
      i++;
    }
    // avatars back-to-front
    const list = [...avatars.values()].sort((p, q) => p.y - q.y);
    for (const a of list) drawAvatar(a);
  }

  function loop(t) {
    requestAnimationFrame(loop);
    if (hidden) return;
    if (!last) last = t;
    acc += t - last;
    last = t;
    const step = 1000 / FPS;
    let n = 0;
    while (acc >= step && n < 3) {
      tick(step / 1000);
      acc -= step;
      n++;
    }
    draw();
    const shown = pinName || hoverName;
    if (shown) {
      const a = avatars.get(shown);
      if (a) {
        const sx = offX + (a.x + 8) * scale;
        const sy = offY + (a.y + 4) * scale;
        showTip(shown, sx, sy);
      }
    }
  }

  function toWorld(ev) {
    const r = canvas.getBoundingClientRect();
    const mx = ev.clientX - r.left;
    const my = ev.clientY - r.top;
    return { x: (mx - offX) / scale, y: (my - offY) / scale, sx: mx, sy: my };
  }

  canvas.addEventListener("mousemove", (ev) => {
    const w = toWorld(ev);
    hoverName = hitTest(w.x, w.y);
    if (!hoverName && !pinName) hideTip();
  });
  canvas.addEventListener("mouseleave", () => { hoverName = null; if (!pinName) hideTip(); });
  canvas.addEventListener("click", (ev) => {
    const w = toWorld(ev);
    const n = hitTest(w.x, w.y);
    pinName = (n && pinName === n) ? null : n;
    if (!pinName && !hoverName) hideTip();
  });

  document.addEventListener("visibilitychange", () => {
    hidden = document.hidden;
    if (!hidden) { last = 0; acc = 0; }
  });
  window.addEventListener("resize", layout);

  function applyDesks(desks) {
    const names = new Set();
    (desks || []).forEach((d, i) => { names.add(d.name); ensureAvatar(d, i); });
    for (const k of [...avatars.keys()]) if (!names.has(k)) avatars.delete(k);
    // if no desks, keep empty rooms
  }

  function consumeEvents(msgs) {
    const internals = (msgs || []).filter((m) => m.kind === "internal" || m.kind === "boss" || m.kind === "secretary");
    if (!internals.length) return;
    const last = internals[internals.length - 1];
    const id = (last.t || "") + last.speaker + (last.kind || "") + String(last.text || "").slice(0, 20);
    if (id === lastEventId) return;
    lastEventId = id;
    const a = avatars.get(last.speaker);
    if (!a || !a.present) return;
    if (last.kind === "internal") walkToBoss(a, last.text);
    else {
      a.bubble = String(last.text || "").slice(0, 22);
      a.bubbleT = 5;
      a.mood = "talk";
    }
  }

  function berlin(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return new Intl.DateTimeFormat("fa-IR", { timeZone: "Europe/Berlin", dateStyle: "short", timeStyle: "short" }).format(d) + " (Europe/Berlin)";
    } catch { return iso; }
  }

  function updateBar() {
    const goal = project.goal || state.topic || "بدون پروژه فعال";
    document.getElementById("goal").textContent = goal.slice(0, 80);
    const start = project.started_at ? berlin(project.started_at) : "شروع نشده";
    const prog = project.progress || 0;
    const eta = project.eta || "—";
    const run = state.running ? "در حال کار" : (state.status || "آماده");
    document.getElementById("meta").textContent = `${run} · شروع: ${start} · پیشرفت ${prog}% · ETA ${eta}`;
    document.getElementById("pfill").style.width = clamp(prog) + "%";
  }

  async function poll() {
    try {
      const [st, sc, pr] = await Promise.all([
        fetch("/api/state").then((r) => r.json()),
        fetch("/api/scorecard").then((r) => r.ok ? r.json() : { employees: {} }).catch(() => ({ employees: {} })),
        fetch("/api/project").then((r) => r.ok ? r.json() : {}).catch(() => ({})),
      ]);
      state = st;
      score = sc || { employees: {} };
      project = pr || {};
      applyDesks(st.desks || []);
      consumeEvents(st.messages || []);
      updateBar();
      if (location.search.includes("shot") && !window.__shotDone) {
        window.__shotDone = true;
        const boss = [...avatars.values()].find((v) => v.seat === "boss") || [...avatars.values()][0];
        const staff = [...avatars.values()].find((v) => v.present && v.seat === "employee");
        if (boss) pinName = boss.name;
        if (staff) walkToBoss(staff, '{"claim":"report"}');
      }
    } catch (e) { /* keep last frame */ }
  }

  layout();
  requestAnimationFrame(loop);
  poll();
  setInterval(poll, 1500);
})();
