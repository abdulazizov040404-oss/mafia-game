'use strict';
const CFG = {
  ICE: [{urls: 'stun:stun.l.google.com:19302'}],
  MIN: 2, MAX: 12  // Sinash uchun minimal 2 kishi qilindi
};
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {
  try {
    tg.ready();
    tg.expand();
  } catch (_) {}
}

const ROLES = {
  mirny:   {n: 'Tinch fuqaro', e: '🧑', team: 'city',  d: "Maxsus kuching yo'q. Kunduzi mantiq va ovoz bilan mafiyani toping.", act: null},
  komissar:{n: 'Komissar',     e: '🕵️', team: 'city',  d: "Har tun bitta o'yinchini tekshirasiz: mafiya yoki tinch.", act: 'Tekshirish'},
  shifokor:{n: 'Shifokor',     e: '💉', team: 'city',  d: "Har tun bittasini davolaysiz. Ketma-ket bir odamni davolab bo'lmaydi.", act: 'Davolash'},
  mafiya:  {n: 'Mafioz',       e: '🔫', team: 'mafia', d: "Jamoadoshlaringizni taniysiz. Har tun bittasini o'ldirasiz.", act: "O'ldirish"},
  don:     {n: 'Don',          e: '🎩', team: 'mafia', d: "Mafiya boshlig'i. Komissar sizni tinch deb ko'radi.", act: "O'ldirish"},
  maniak:  {n: 'Maniak',       e: '🔪', team: 'solo',  d: "Yolg'iz. Har tun bittasini o'ldirasiz va oxirgi tirik qolishingiz kerak.", act: "O'ldirish"}
};

const S = {
  screen: 'boot', me: null, mode: null, room: 'main', players: [], phase: 'lobby', day: 0, endsAt: 0,
  role: null, mates: [], chat: [], sel: null, voted: null, acted: false, hostPid: null,
  talking: {}, mic: false, revealed: false, end: null, micReady: false
};
const $app = document.getElementById('app');
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const meP = () => S.me && S.players.find(p => p.pid === S.me.pid);
const iAmAlive = () => { const p = meP(); return p ? p.alive : true; };
const left = () => { const s = Math.max(0, Math.ceil((S.endsAt - Date.now()) / 1000)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
function toast(t) { const d = document.createElement('div'); d.className = 'toast'; d.textContent = t; document.body.appendChild(d); setTimeout(() => d.remove(), 2600); }
function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (_) {} }
function say(who, text, cls) { S.chat.push({who, text, cls}); if (S.chat.length > 150) S.chat.shift(); drawChat(); }

/* ================= TARMOQ ================= */
const Net = {
  ws: null, h: {},
  on(t, f) { this.h[t] = f; },
  async connect() {
    const initData = (tg && tg.initData) ? tg.initData : '';
    const r = await fetch('/api/auth', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({initData})
    });
    if (!r.ok) throw new Error('auth');
    const j = await r.json();
    S.tgName = j.name;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    await new Promise((ok, no) => {
      const ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(j.token)}`);
      this.ws = ws;
      ws.onopen = ok; 
      ws.onerror = no;
      ws.onmessage = e => { 
        try { 
          const m = JSON.parse(e.data); 
          this.h[m.type] && this.h[m.type](m.data); 
        } catch (_) {} 
      };
      ws.onclose = () => toast("Aloqa uzildi. Mini App'ni qayta oching.");
    });
  },
  send(type, data) { if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({type, data})); }
};

Net.on('me', d => { S.me = d; });
Net.on('lobby', d => {
  S.players = d.players; S.hostPid = d.host; S.mode = d.mode; S.room = d.room; S.phase = 'lobby';
  document.body.classList.remove('day'); go('lobby');
});
Net.on('phase', d => {
  S.phase = d.name; S.day = d.day; S.endsAt = Date.now() + d.ms; S.players = d.players; S.mode = d.mode;
  S.sel = null; S.voted = null; S.acted = false; S.talking = {};
  if (d.name === 'night' && d.day === 0) { S.revealed = false; S.role = null; S.chat = []; Voice.connectAll(); }
  document.body.classList.toggle('day', d.name !== 'night');
  applyMic(); go('game');
});
Net.on('role', d => { S.role = d.role; S.mates = d.mates || []; if (navigator.vibrate) navigator.vibrate(60); render(); });
Net.on('chat', d => say(d.who, d.text, d.scope === 'mafia' ? 'mafia' : ''));
Net.on('result', d => { say('', d.text, 's'); toast(d.text); });
Net.on('check', d => { const t = S.players.find(p => p.pid === d.pid); const m = 'Tekshiruv: ' + (t ? t.nick : '') + ' — ' + (d.team === 'mafia' ? 'MAFIYA' : 'tinch'); toast(m); say('', m, 's'); });
Net.on('speaking', d => { S.talking[d.pid] = d.on; render(); });
Net.on('end', d => { S.end = d; S.phase = 'end'; document.body.classList.add('day'); stopVoice(); go('end'); });
Net.on('rtc', d => Voice.signal(d));
Net.on('error', d => toast(d.text));

/* ================= OVOZ (WebRTC) ================= */
const Voice = {
  stream: null, peers: {},
  async start() {
    if (this.stream) return true;
    try { this.stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}}); }
    catch (e) { toast('Mikrofonga ruxsat bering'); return false; }
    this.stream.getAudioTracks().forEach(t => t.enabled = false);
    return true;
  },
  peer(pid, init) {
    if (this.peers[pid]) return this.peers[pid];
    const pc = new RTCPeerConnection({iceServers: CFG.ICE});
    this.stream && this.stream.getTracks().forEach(t => pc.addTrack(t, this.stream));
    pc.onicecandidate = e => e.candidate && Net.send('rtc', {to: pid, kind: 'ice', payload: e.candidate});
    pc.ontrack = e => {
      let a = document.getElementById('a' + pid);
      if (!a) { a = document.createElement('audio'); a.id = 'a' + pid; a.autoplay = true; document.body.appendChild(a); }
      a.srcObject = e.streams[0];
    };
    this.peers[pid] = pc;
    if (init) pc.createOffer().then(o => pc.setLocalDescription(o).then(() => Net.send('rtc', {to: pid, kind: 'offer', payload: o})));
    return pc;
  },
  connectAll() {
    if (S.mode !== 'voice' || !this.stream) return;
    S.players.forEach(p => { if (p.pid !== S.me.pid && S.me.pid < p.pid) this.peer(p.pid, true); });
  },
  async signal({from, kind, payload}) {
    if (!this.stream) return;
    const pc = this.peer(from, false);
    try {
      if (kind === 'offer') { await pc.setRemoteDescription(payload); const a = await pc.createAnswer(); await pc.setLocalDescription(a); Net.send('rtc', {to: from, kind: 'answer', payload: a}); }
      else if (kind === 'answer') await pc.setRemoteDescription(payload);
      else if (kind === 'ice') await pc.addIceCandidate(payload);
    } catch (_) {}
  }
};

const micAllowed = () => S.mode === 'voice' && S.phase === 'day' && iAmAlive();
function applyMic() {
  if (!micAllowed()) S.mic = false;
  if (Voice.stream) Voice.stream.getAudioTracks().forEach(t => t.enabled = S.mic && micAllowed());
  if (S.mode === 'voice') Net.send('speaking', {on: S.mic});
}
function stopVoice() {
  Object.values(Voice.peers).forEach(p => p.close()); Voice.peers = {};
  document.querySelectorAll('audio').forEach(a => a.remove());
  if (Voice.stream) Voice.stream.getTracks().forEach(t => t.stop());
  Voice.stream = null; S.mic = false;
}

/* ================= EKRANLAR ================= */
let tick;
function go(s) { S.screen = s; render(); }
function render() {
  const a = document.activeElement;
  const keep = a && a.tagName === 'INPUT' ? {id: a.id, v: a.value} : null;
  ({boot, home, lobby, game, end})[S.screen]();
  if (keep) { const i = document.getElementById(keep.id); if (i) { i.value = keep.v; i.focus(); } }
  clearInterval(tick);
  if (S.screen === 'game') tick = setInterval(() => { const t = document.getElementById('tm'); if (t) t.textContent = left(); }, 500);
}

function boot() {
  const ok = !!(tg && tg.initData);
  $app.innerHTML = `<div class="stack" style="margin:auto 0"><h1>Mafiya</h1>
    <p>${ok ? 'Telegram akkauntingiz tekshirilmoqda…' : "Bu o'yin Telegram ichida ishlaydi. Botdagi tugma orqali oching."}</p></div>`;
}

function home() {
  const sp = tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param;
  const nick = store('nick') || S.tgName || '';
  const room = store('room') || sp || 'main';
  $app.innerHTML = `<div class="stack" style="margin:auto 0">
    <h1>Mafiya</h1>
    <p>Telegram akkauntingiz tasdiqlandi. O'yinda ko'rinadigan taxallusingizni yozing.</p>
    <div><label for="nk">Taxallus (2–16 belgi)</label><input id="nk" maxlength="16" value="${esc(nick)}" autocomplete="off"></div>
    <div><label for="rm">Xona kodi</label><input id="rm" maxlength="20" value="${esc(sp || room)}" autocomplete="off"></div>
    <div class="modes">
      <button data-m="chat"><b>💬 Chat</b><span class="mut">Yozib muhokama qilasiz.</span></button>
      <button data-m="voice"><b>🎙 Ovozli</b><span class="mut">Kunduzi gaplashasiz.</span></button>
    </div>
    <button class="pri" id="jn" disabled>Xonaga kirish</button></div>`;
  let mode = null;
  document.querySelectorAll('[data-m]').forEach(b => b.onclick = () => {
    mode = b.dataset.m;
    document.querySelectorAll('[data-m]').forEach(x => x.classList.toggle('on', x === b));
    document.getElementById('jn').disabled = false;
  });
  document.getElementById('jn').onclick = async () => {
    const n = document.getElementById('nk').value.trim(), r = document.getElementById('rm').value.trim() || 'main';
    if (n.length < 2) return toast('Taxallus kamida 2 belgi');
    if (mode === 'voice' && !(await Voice.start())) return;
    store('nick', n); store('room', r);
    S.mode = mode;
    Net.send('join', {nick: n, room: r, mode});
  };
}

function lobby() {
  const n = S.players.length, ok = n >= CFG.MIN, host = S.me && S.hostPid === S.me.pid;
  $app.innerHTML = `<div class="stack">
    <div class="top"><h2>${S.mode === 'voice' ? '🎙 Ovozli xona' : '💬 Chat xona'}</h2><span class="mut">${n}/${CFG.MAX}</span></div>
    <div class="box"><span class="mut">Xona kodi</span><div class="code">${esc(S.room)}</div></div>
    <div class="pl">${S.players.map(p => `<button disabled>${esc(p.nick)}<small>#${p.pid}${S.me && p.pid === S.me.pid ? ' · siz' : ''}${p.pid === S.hostPid ? ' · boshlovchi' : ''}</small></button>`).join('')}</div>
    <p>${ok ? 'Boshlash mumkin.' : 'Kamida ' + CFG.MIN + " o'yinchi kerak."} Rollar tunda yashirin beriladi.</p>
    ${host ? `<button class="pri" id="st" ${ok ? '' : 'disabled'}>O'yinni boshlash</button>` : "<p>Boshlovchi o'yinni boshlashini kuting…</p>"}
    <button id="lv">Chiqish</button></div>`;
  const st = document.getElementById('st'); if (st) st.onclick = () => Net.send('start', {});
  document.getElementById('lv').onclick = () => { Net.send('leave', {}); stopVoice(); go('home'); };
}

function drawChat() {
  const c = document.getElementById('chat'); if (!c) return;
  c.innerHTML = S.chat.map(m => `<div class="m ${m.cls || ''}">${m.who ? `<b>${esc(m.who)}:</b> ` : ''}${esc(m.text)}</div>`).join('');
  c.scrollTop = c.scrollHeight;
}

function chatBox(title) {
  const r = S.role && ROLES[S.role];
  const can = iAmAlive() && (S.phase === 'day' || (S.phase === 'night' && S.day >= 1 && r && r.team === 'mafia'));
  return `<h2 style="margin:12px 0 6px">${title}</h2><div class="box" id="chat"></div>
    <div class="row" style="margin-top:8px"><input id="ci" maxlength="200" placeholder="${can ? 'Xabar yozing' : "Hozir yozib bo'lmaydi"}" ${can ? '' : 'disabled'}><button class="pri" id="cs" ${can ? '' : 'disabled'}>Yuborish</button></div>`;
}

function players(selectable) {
  return `<div class="pl">${S.players.map(p => {
    const self = S.me && p.pid === S.me.pid;
    const dis = !p.alive || !selectable || (self && S.role !== 'shifokor');
    return `<button data-pid="${p.pid}" class="${p.alive ? '' : 'dead'} ${S.sel === p.pid ? 'sel' : ''} ${S.talking[p.pid] ? 'talk' : ''}" ${dis ? 'disabled' : ''}>${esc(p.nick)}<small>#${p.pid}${self ? ' · siz' : ''}</small></button>`;
  }).join('')}</div>`;
}

function game() {
  const r = S.role && ROLES[S.role], ph = S.phase, me = iAmAlive();
  let body = '';
  if (ph === 'night') {
    const deal = S.day === 0;
    const canAct = r && r.act && !deal && me && !S.acted;
    body += `<div class="sleep"><div class="moon"></div><h2>${deal ? 'Hamma uxlayapti' : 'Shahar uxlayapti'}</h2>
      <p>${deal ? "Rolingizni faqat siz ko'rasiz. Ekranni boshqalarga ko'rsatmang." : "Ko'zlaringizni yuming. Mikrofon o'chiq."}</p></div>`;
    body += r
      ? `<div class="box role" id="rc">${S.revealed ? `<div style="font-size:44px">${r.e}</div><div class="big">${r.n}</div><p>${r.d}</p>${S.mates.length ? `<p>Jamoa: <b>${S.mates.map(esc).join(', ')}</b></p>` : ''}` : `<div style="font-size:44px">🂠</div><p>Rolingizni ko'rish uchun bosib turing</p>`}</div>`
      : `<div class="box role"><p>Rol yuborilmoqda…</p></div>`;
    if (canAct) body += `<h2 style="margin-top:12px">${r.act}</h2>${players(true)}<button class="pri" id="ok" ${S.sel ? '' : 'disabled'} style="margin-top:10px">Tasdiqlash</button>`;
    else if (!deal && r && r.act && S.acted) body += `<p style="margin-top:12px;text-align:center">Tanlov qabul qilindi.</p>`;
    if (S.mode === 'chat' && r && r.team === 'mafia' && !deal && me) body += chatBox('Mafiya yopiq chati');
  } else {
    body += players(ph === 'vote' && me);
    if (ph === 'vote') body += `<button class="red" id="ok" ${S.sel ? '' : 'disabled'} style="margin-top:10px">${S.voted ? "Ovoz berildi" : 'Ovoz berish'}</button>`;
    if (S.mode === 'chat') body += chatBox(ph === 'day' ? 'Muhokama' : 'Chat');
    else body += `<div class="box row" style="margin-top:10px"><button class="mic ${S.mic ? 'live' : ''}" id="mic" ${micAllowed() ? '' : 'disabled'}>${S.mic ? '🎙' : '🔇'}</button><span class="mut grow">${micAllowed() ? (S.mic ? 'Mikrofon yoqiq. Gapiring.' : 'Gapirish uchun mikrofonni bosing.') : ph === 'vote' ? 'Ovoz berish vaqtida jim.' : "Siz o'yinda emassiz."}</span></div>`;
  }
  $app.innerHTML = `<div class="top"><div><h2>${ph === 'night' ? (S.day === 0 ? 'Tanishuv kechasi' : 'Tun ' + S.day) : ph === 'day' ? 'Kun ' + S.day : 'Ovoz berish'}</h2><span class="mut">${r && ph !== 'night' ? r.e + ' ' + r.n : ''}${me ? '' : " · chetlatildingiz"}</span></div><div class="timer" id="tm">${left()}</div></div>${body}`;
  bindGame(); drawChat();
}

function bindGame() {
  document.querySelectorAll('.pl button[data-pid]').forEach(b => b.onclick = () => { S.sel = Number(b.dataset.pid); render(); });
  const ok = document.getElementById('ok');
  if (ok) ok.onclick = () => {
    if (S.phase === 'vote') { S.voted = S.sel; Net.send('vote', {target: S.sel}); }
    else { S.acted = true; Net.send('action', {target: S.sel}); }
    S.sel = null; render();
  };
  const rc = document.getElementById('rc');
  if (rc) {
    const show = v => e => { e.preventDefault(); if (S.revealed !== v) { S.revealed = v; render(); } };
    rc.onpointerdown = show(true); rc.onpointerup = show(false); rc.onpointerleave = show(false); rc.onpointercancel = show(false);
    rc.oncontextmenu = e => e.preventDefault();
  }
  const mic = document.getElementById('mic'); if (mic) mic.onclick = () => { S.mic = !S.mic; applyMic(); render(); };
  const cs = document.getElementById('cs'), ci = document.getElementById('ci');
  if (cs) {
    const send = () => { const t = ci.value.trim(); if (t) { Net.send('chat', {text: t}); ci.value = ''; } };
    cs.onclick = send; ci.onkeydown = e => { if (e.key === 'Enter') send(); };
  }
}

function end() {
  const e = S.end || {};
  $app.innerHTML = `<div class="stack" style="margin:auto 0"><h1>${esc(e.winner || "O'yin tugadi")}</h1>
    <div class="box stack">${(e.roles || []).map(x => `<div class="row"><span class="grow">${esc(x.nick)}</span><span>${ROLES[x.role] ? ROLES[x.role].e + ' ' + ROLES[x.role].n : ''}</span></div>`).join('')}</div>
    <button class="pri" id="again">Yana o'ynash</button></div>`;
  document.getElementById('again').onclick = () => { S.chat = []; S.role = null; S.end = null; go('home'); };
}

/* ================= ISHGA TUSHIRISH ================= */
(async function init() {
  render();
  if (!(tg && tg.initData)) return;
  try { 
    await Net.connect(); 
    go('home'); 
  } catch (e) { 
    $app.innerHTML = `<div class="stack" style="margin:auto 0"><h2>Ulanib bo'lmadi</h2><p>Telegram akkaunt tasdiqlanmadi yoki server ishlamayapti. Mini App'ni qayta oching.</p></div>`; 
  }
})();