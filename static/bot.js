const tg = window.Telegram?.WebApp;
if (tg) {
    tg.expand();
    tg.ready();
}

function haptic(type = "light") {
    if (tg?.HapticFeedback) {
        if (["error", "warning", "success"].includes(type)) {
            tg.HapticFeedback.notificationOccurred(type);
        } else {
            tg.HapticFeedback.impactOccurred(type);
        }
    }
}

const userId = tg?.initDataUnsafe?.user?.id 
    ? String(tg.initDataUnsafe.user.id) 
    : "player_" + Math.floor(Math.random() * 89999 + 10000);

const userName = tg?.initDataUnsafe?.user?.first_name || ("O'yinchi_" + userId.slice(-4));

const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
let ws = null;
let currentRoomId = null;
let isHost = false;
let myRole = "citizen";
let isAlive = true;

// Profilni yuklash
function showProfile() {
    document.getElementById("user-name-display").innerText = userName;
    document.getElementById("user-id-display").innerText = userId;
    fetch(`/api/profile/${userId}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById("stat-total-games").innerText = data.games || 0;
            document.getElementById("stat-total-wins").innerText = data.wins || 0;
            const rate = data.games ? Math.round((data.wins / data.games) * 100) : 0;
            document.getElementById("stat-win-rate").innerText = rate + "%";
        })
        .catch(() => {});
    document.getElementById("profile-modal").style.display = "flex";
    haptic("light");
}

function closeProfile() {
    document.getElementById("profile-modal").style.display = "none";
}

function openCreateRoomModal() {
    document.getElementById("create-room-modal").style.display = "flex";
    haptic("light");
}

function closeCreateRoomModal() {
    document.getElementById("create-room-modal").style.display = "none";
}

function refreshRooms() {
    fetch("/api/rooms")
        .then(res => res.json())
        .then(data => {
            const container = document.getElementById("rooms-container");
            if (!data.rooms || data.rooms.length === 0) {
                container.innerHTML = `<p style="text-align:center; color:var(--text-muted); padding:20px 0;">Faol xonalar topilmadi.</p>`;
                return;
            }
            container.innerHTML = "";
            data.rooms.forEach(r => {
                const div = document.createElement("div");
                div.className = "room-card";
                div.innerHTML = `
                    <div class="room-meta">
                        <span class="room-name">${r.name}</span>
                        <span class="room-sub">ID: #${r.id} | O'yinchilar: ${r.count} | ${r.status}</span>
                    </div>
                    <button class="btn-sm btn-primary" onclick="joinRoom('${r.id}')">Kirish</button>
                `;
                container.appendChild(div);
            });
        });
}

function quickJoin() {
    fetch("/api/quick_join")
        .then(res => res.json())
        .then(data => {
            if (data.room_id) {
                joinRoom(data.room_id);
            } else {
                alert("Hozirda bo'sh faol xona yo'q. Yangi xona yarating!");
            }
        });
}

function confirmCreateRoom() {
    const input = document.getElementById("new-room-name-input");
    const rName = input.value.trim() || `Xona_${Math.floor(Math.random() * 900 + 100)}`;
    fetch("/api/create_room", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: rName })
    })
    .then(res => res.json())
    .then(data => {
        closeCreateRoomModal();
        joinRoom(data.room_id);
    });
}

function joinRoom(roomId) {
    currentRoomId = roomId;
    document.getElementById("lobby-view").style.display = "none";
    document.getElementById("game-view").style.display = "block";

    ws = new WebSocket(`${protocol}//${window.location.host}/ws/${roomId}/${userId}?name=${encodeURIComponent(userName)}`);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === "room_info") {
            document.getElementById("room-display-name").innerText = data.name;
            document.getElementById("room-display-id").innerText = `ID: #${data.id}`;
        }
        else if (data.type === "is_admin") {
            isHost = true;
            document.getElementById("host-panel").style.display = "block";
        }
        else if (data.type === "kicked") {
            alert("Siz xona egasi tomonidan xonadan chiqarildingiz!");
            window.location.reload();
        }
        else if (data.type === "your_role") {
            myRole = data.role;
            const badge = document.getElementById("player-role-badge");
            badge.className = `badge badge-${myRole}`;
            const map = { mafia: "🔫 Mafia", citizen: "👤 Fuqaro", doctor: "💉 Doktor", commissar: "🔍 Komissar" };
            badge.innerText = map[myRole] || myRole;
            haptic("heavy");
        }
        else if (data.type === "phase_change") {
            handlePhaseChange(data);
        }
        else if (data.type === "timer") {
            const m = Math.floor(data.time / 60);
            const s = data.time % 60;
            const el = document.getElementById("timer-display");
            el.innerText = `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
            if (data.time <= 10) el.classList.add("urgent");
            else el.classList.remove("urgent");
        }
        else if (data.type === "players_update") {
            renderPlayers(data.players);
        }
        else if (data.type === "chat") {
            appendChat(data.sender, data.text, data.is_system);
        }
        else if (data.type === "eliminated") {
            if (data.target_id === userId) {
                isAlive = false;
                document.getElementById("chat-form").style.display = "none";
                document.getElementById("actions-panel").style.display = "none";
                haptic("error");
            }
        }
        else if (data.type === "commissar_alert") {
            alert(data.text);
            haptic("warning");
        }
    };
}

function handlePhaseChange(data) {
    const body = document.body;
    const title = document.getElementById("phase-title");
    const chatForm = document.getElementById("chat-form");
    const actionsPanel = document.getElementById("actions-panel");
    const actionBtns = document.getElementById("action-buttons-box");
    actionBtns.innerHTML = "";

    // MUHOKAMA (Chat faqat shu yerda ochiq)
    if (data.phase === "discussion") {
        body.className = "day-mode";
        title.innerText = "☀️ KUNDUZGI MUHOKAMA";
        chatForm.style.display = isAlive ? "flex" : "none";
        actionsPanel.style.display = "none";
        haptic("medium");
    }
    // OVOZ BERISH
    else if (data.phase === "voting" || data.phase === "revoting") {
        body.className = "day-mode";
        title.innerText = data.phase === "revoting" ? "⚖️ QAYTA OVOZ BERISH" : "🗳 OVOZ BERISH";
        chatForm.style.display = "none";

        if (isAlive) {
            actionsPanel.style.display = "block";
            document.getElementById("action-title").innerText = "Gumonlanuvchini tanlang:";
            data.candidates.forEach(c => {
                const btn = document.createElement("button");
                btn.innerText = c.name;
                btn.onclick = () => {
                    ws.send(JSON.stringify({ action: "vote", target_id: c.id }));
                    actionsPanel.style.display = "none";
                    haptic("light");
                };
                actionBtns.appendChild(btn);
            });
        }
    }
    // TUN
    else if (data.phase === "night") {
        body.className = "night-mode";
        title.innerText = "🌙 TUN BOSQICHI";
        chatForm.style.display = "none";
        haptic("medium");

        if (isAlive && ["mafia", "doctor", "commissar"].includes(myRole)) {
            actionsPanel.style.display = "block";
            document.getElementById("action-title").innerText = 
                myRole === "mafia" ? "Kimni yo'q qilamiz? (Konsensus)" :
                myRole === "doctor" ? "Kimni davolaysiz?" : "Kimni tekshirasiz?";

            data.targets.forEach(t => {
                const btn = document.createElement("button");
                btn.innerText = t.name;
                btn.onclick = () => {
                    ws.send(JSON.stringify({ action: "night_action", target_id: t.id }));
                    actionsPanel.style.display = "none";
                    haptic("light");
                };
                actionBtns.appendChild(btn);
            });
        }
    }
}

function renderPlayers(players) {
    const list = document.getElementById("players-list");
    list.innerHTML = "";
    players.forEach(p => {
        const div = document.createElement("div");
        div.className = `player-item ${p.is_alive ? 'alive' : 'dead'}`;
        
        let kickBtn = "";
        if (isHost && p.id !== userId && currentRoomId) {
            kickBtn = `<button class="btn-danger" onclick="kickPlayer('${p.id}')">Chiqarish</button>`;
        }

        div.innerHTML = `
            <span>${p.name} ${p.id === userId ? '<b>(Siz)</b>' : ''}</span>
            <div style="display:flex; align-items:center; gap:8px;">
                <span>${p.is_alive ? '🟢 Tirik' : '💀 O\'lgan'}</span>
                ${kickBtn}
            </div>
        `;
        list.appendChild(div);
    });
}

function kickPlayer(targetId) {
    if (confirm("Bu o'yinchini xonadan chiqarib yubormoqchimisiz?")) {
        ws.send(JSON.stringify({ action: "kick", target_id: targetId }));
        haptic("warning");
    }
}

function submitChat() {
    const input = document.getElementById("chat-text-input");
    if (!input.value.trim() || !isAlive) return;
    ws.send(JSON.stringify({ action: "chat", text: input.value.trim() }));
    input.value = "";
    haptic("light");
}

function appendChat(sender, text, isSystem = false) {
    const box = document.getElementById("chat-messages");
    const m = document.createElement("div");
    m.className = "chat-bubble" + (isSystem ? " system" : "");
    m.innerHTML = isSystem ? `📢 ${text}` : `<strong>${sender}:</strong> ${text}`;
    box.appendChild(m);
    box.scrollTop = box.scrollHeight;
}

function updateTimer(sec) {
    ws.send(JSON.stringify({ action: "set_timer", seconds: sec }));
    haptic("light");
}

function startGame() {
    ws.send(JSON.stringify({ action: "start_game" }));
    document.getElementById("host-panel").style.display = "none";
    haptic("success");
}

refreshRooms();
setInterval(refreshRooms, 5000);