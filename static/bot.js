const tg = window.Telegram?.WebApp;
if (tg) {
    tg.expand();
    tg.ready();
}

function triggerHaptic(type = "light") {
    if (tg?.HapticFeedback) {
        if (type === "error" || type === "warning" || type === "success") {
            tg.HapticFeedback.notificationOccurred(type);
        } else {
            tg.HapticFeedback.impactOccurred(type);
        }
    }
}

const userId = tg?.initDataUnsafe?.user?.id 
    ? String(tg.initDataUnsafe.user.id) 
    : "user_" + Math.floor(Math.random() * 9000 + 1000);

const userName = tg?.initDataUnsafe?.user?.first_name || ("O'yinchi " + userId.slice(-4));

const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
const ws = new WebSocket(`${protocol}//${window.location.host}/ws/${userId}?name=${encodeURIComponent(userName)}`);

let myRole = "citizen";
let isAlive = true;
let currentPhase = "lobby";

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "your_role") {
        myRole = data.role;
        const badge = document.getElementById("role-badge");
        badge.className = `role-badge role-${myRole}`;
        const titles = {
            mafia: "🔫 MAFIA",
            doctor: "💉 DOKTOR",
            commissar: "🔍 KOMISSAR",
            citizen: "👤 TINCH AHOLI"
        };
        badge.innerText = titles[myRole] || myRole;
        triggerHaptic("heavy");
    }

    else if (data.type === "phase_change") {
        currentPhase = data.phase;
        updatePhaseUI(data);
    }

    else if (data.type === "timer") {
        const timerEl = document.getElementById("timer");
        const m = Math.floor(data.time / 60);
        const s = data.time % 60;
        timerEl.innerText = `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
        if (data.time <= 10) {
            timerEl.classList.add("urgent");
        } else {
            timerEl.classList.remove("urgent");
        }
    }

    else if (data.type === "players_update") {
        renderPlayers(data.players);
    }

    else if (data.type === "chat") {
        appendMessage(data.sender, data.text, data.is_system, data.is_mafia);
    }

    else if (data.type === "eliminated") {
        if (data.target_id === userId) {
            isAlive = false;
            triggerHaptic("error");
            document.getElementById("chat-controls").style.display = "none";
            document.getElementById("action-panel").style.display = "none";
        }
    }

    else if (data.type === "commissar_alert") {
        triggerHaptic("warning");
        alert(data.text);
    }
};

function updatePhaseUI(data) {
    const body = document.body;
    const phaseTitle = document.getElementById("phase-title");
    const actPanel = document.getElementById("action-panel");
    const actBtns = document.getElementById("action-buttons");
    const chatHeader = document.getElementById("chat-header");
    const chatControls = document.getElementById("chat-controls");

    actBtns.innerHTML = "";

    if (data.phase === "night") {
        body.className = "night-mode";
        phaseTitle.innerText = "🌙 TUN BOSQICHI";
        triggerHaptic("medium");

        if (myRole === "mafia") {
            chatHeader.innerText = "🔴 Yashirin Mafia Chati";
            chatControls.style.display = isAlive ? "flex" : "none";
        } else {
            chatHeader.innerText = "💬 Shahar uxlamoqda...";
            chatControls.style.display = "none";
        }

        if (isAlive && ["mafia", "doctor", "commissar"].includes(myRole)) {
            actPanel.style.display = "block";
            document.getElementById("action-heading").innerText = 
                myRole === "mafia" ? "Kimni yo'q qilamiz? (Konsensus)" :
                myRole === "doctor" ? "Kimni davolaysiz?" : "Kimni tekshirasiz?";

            data.targets.forEach(t => {
                const b = document.createElement("button");
                b.innerText = t.name;
                b.onclick = () => {
                    ws.send(JSON.stringify({ action: "night_action", target_id: t.id }));
                    actPanel.style.display = "none";
                    triggerHaptic("light");
                };
                actBtns.appendChild(b);
            });
        } else {
            actPanel.style.display = "none";
        }
    } 
    else if (data.phase === "discussion") {
        body.className = "day-mode";
        phaseTitle.innerText = "☀️ MUHOKAMA VAQTI";
        chatHeader.innerText = "💬 Shahar Chati";
        chatControls.style.display = isAlive ? "flex" : "none";
        actPanel.style.display = "none";
        triggerHaptic("medium");
    } 
    else if (data.phase === "voting" || data.phase === "revoting") {
        body.className = "day-mode";
        phaseTitle.innerText = data.phase === "revoting" ? "⚖️ QAYTA OVOZ BERISH" : "🗳 OVOZ BERISH";
        chatControls.style.display = "none";

        if (isAlive) {
            actPanel.style.display = "block";
            document.getElementById("action-heading").innerText = "Gumonlanuvchiga ovoz bering:";
            data.candidates.forEach(cand => {
                const b = document.createElement("button");
                b.innerText = cand.name;
                b.onclick = () => {
                    ws.send(JSON.stringify({ action: "vote", target_id: cand.id }));
                    actPanel.style.display = "none";
                    triggerHaptic("light");
                };
                actBtns.appendChild(b);
            });
        }
    }
}

function renderPlayers(players) {
    const grid = document.getElementById("players-grid");
    grid.innerHTML = "";
    players.forEach(p => {
        const div = document.createElement("div");
        div.className = `player-card ${p.is_alive ? 'alive' : 'dead'}`;
        div.innerHTML = `<span>${p.name} ${p.id === userId ? '<b>(Siz)</b>' : ''}</span> <span>${p.is_alive ? '🟢' : '💀'}</span>`;
        grid.appendChild(div);
    });
}

function appendMessage(sender, text, isSystem = false, isMafia = false) {
    const box = document.getElementById("chat-box");
    const m = document.createElement("div");
    m.className = "chat-msg" + (isSystem ? " system" : "") + (isMafia ? " mafia-secret" : "");
    m.innerHTML = isSystem ? `📢 ${text}` : `<strong>${sender}:</strong> ${text}`;
    box.appendChild(m);
    box.scrollTop = box.scrollHeight;
}

function sendChat() {
    const inp = document.getElementById("chat-input");
    if (!inp.value.trim() || !isAlive) return;

    ws.send(JSON.stringify({ action: "chat", text: inp.value.trim() }));
    inp.value = "";
    triggerHaptic("light");
}

function changeTimer(sec) {
    ws.send(JSON.stringify({ action: "set_timer", seconds: sec }));
    triggerHaptic("light");
}

function requestStartGame() {
    ws.send(JSON.stringify({ action: "start_game" }));
    document.getElementById("admin-panel").style.display = "none";
    triggerHaptic("success");
}