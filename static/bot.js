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

// Mahalliy saqlangan ism yoki standart 6+ belgili ism
let userName = localStorage.getItem("mafia_username") || 
    (tg?.initDataUnsafe?.user?.first_name && tg.initDataUnsafe.user.first_name.length >= 6 
        ? tg.initDataUnsafe.user.first_name 
        : "Player" + userId.slice(-4));

if (userName.length < 6) {
    userName = "Fuqaro_" + userId.slice(-4);
}

const defaultAvatars = [
    "https://api.dicebear.com/7.x/bottts/svg?seed=Shadow",
    "https://api.dicebear.com/7.x/bottts/svg?seed=Ghost",
    "https://api.dicebear.com/7.x/bottts/svg?seed=Agent",
    "https://api.dicebear.com/7.x/bottts/svg?seed=Viper"
];

let userAvatar = localStorage.getItem("mafia_avatar") || defaultAvatars[0];
let userFrame = "frame-none";

const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
let ws = null;
let currentRoomId = null;
let isHost = false;
let myRole = "citizen";
let isAlive = true;
let currentPlayersData = [];
let currentVotesData = {};

// Haqiqiy rollar tasvirlari
const rolesInfo = {
    mafia: {
        title: "🔫 SIZNING ROLINGIZ: MAFIA",
        image: "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=600&auto=format&fit=crop&q=80",
        desc: "Siz shahar dushmanisiz! Vazifangiz: Tunda boshqa mafialar bilan bitta odamni kelishib o'ldirish. Kunduzi o'zingizni shubhasiz begunoh ko'rsatib, ovoz berishda tirik qoling."
    },
    doctor: {
        title: "💉 SIZNING ROLINGIZ: DOKTOR",
        image: "https://images.unsplash.com/photo-1579684385127-1ef15d508118?w=600&auto=format&fit=crop&q=80",
        desc: "Siz shahar shifokorisisiz! Vazifangiz: Har kecha bir fuqaroni davolaysiz. Agar siz tanlagan shaxsga mafia o'sha tunda hujum qilsa, u omon qoladi."
    },
    commissar: {
        title: "🔍 SIZNING ROLINGIZ: KOMISSAR",
        image: "https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=600&auto=format&fit=crop&q=80",
        desc: "Siz maxfiy tergovchisiz! Vazifangiz: Har kecha bir odamning kimligini tekshirasiz va tizim sizga uning MAFIA yoki FUQARO ekanini ochib beradi."
    },
    citizen: {
        title: "👤 SIZNING ROLINGIZ: TINCH FUQARO",
        image: "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=600&auto=format&fit=crop&q=80",
        desc: "Siz tinch aholi vakilisiz! Tungi kushingiz yo'q. Muhokama vaqtida kim o'zini g'alati tutayotganini tahlil qiling va ovoz berish orqali shaharni mafialardan tozalang!"
    }
};

function updateHeaderInfo() {
    document.getElementById("header-user-name").innerText = userName;
    document.getElementById("header-user-id").innerText = `ID: #${userId}`;
    const box = document.getElementById("header-avatar");
    box.className = `avatar-box ${userFrame}`;
    document.getElementById("header-avatar-img").src = userAvatar;
}

function showRoleModal(role) {
    const info = rolesInfo[role] || rolesInfo.citizen;
    document.getElementById("role-title").innerText = info.title;
    document.getElementById("role-image").src = info.image;
    document.getElementById("role-desc").innerText = info.desc;
    document.getElementById("role-modal").style.display = "flex";
    haptic("heavy");
}

function closeRoleModal() {
    document.getElementById("role-modal").style.display = "none";
}

function showProfile() {
    document.getElementById("prof-input-name").value = userName;
    document.getElementById("prof-modal-avatar-img").src = userAvatar;
    document.getElementById("prof-modal-avatar-box").className = `avatar-box ${userFrame}`;

    // Avatarlar tanlovini chiqarish
    const box = document.getElementById("avatar-options-box");
    box.innerHTML = "";
    defaultAvatars.forEach(av => {
        const img = document.createElement("img");
        img.src = av;
        img.className = `avatar-option ${av === userAvatar ? 'selected' : ''}`;
        img.onclick = () => {
            userAvatar = av;
            document.getElementById("prof-modal-avatar-img").src = av;
            document.querySelectorAll(".avatar-option").forEach(el => el.classList.remove("selected"));
            img.classList.add("selected");
        };
        box.appendChild(img);
    });

    fetch(`/api/profile/${userId}`)
        .then(res => res.json())
        .then(data => {
            const games = data.games || 0;
            const wins = data.wins || 0;
            const rate = games > 0 ? Math.round((wins / games) * 100) : 0;
            document.getElementById("stat-total-games").innerText = games;
            document.getElementById("stat-total-wins").innerText = wins;
            document.getElementById("stat-win-rate").innerText = rate + "%";

            // Yutuq foiziga qarab ramka berish
            if (games >= 15 && rate >= 60) userFrame = "frame-cyber";
            else if (games >= 10 && rate >= 50) userFrame = "frame-gold";
            else if (games >= 5 && rate >= 40) userFrame = "frame-silver";
            else if (games >= 2) userFrame = "frame-bronze";
            else userFrame = "frame-none";

            document.getElementById("prof-modal-avatar-box").className = `avatar-box ${userFrame}`;
            const mapNames = {
                "frame-none": "Standart",
                "frame-bronze": "Bronza",
                "frame-silver": "Kumush",
                "frame-gold": "Oltin",
                "frame-cyber": "Kiber Neon"
            };
            document.getElementById("prof-frame-name").innerText = `Ramka: ${mapNames[userFrame]}`;
            updateHeaderInfo();
        });

    document.getElementById("profile-modal").style.display = "flex";
    haptic("light");
}

function saveProfile() {
    const val = document.getElementById("prof-input-name").value.trim();
    if (val.length < 6) {
        alert("Ism kamida 6 ta harfdan iborat bo'lishi shart!");
        return;
    }
    userName = val;
    localStorage.setItem("mafia_username", userName);
    localStorage.setItem("mafia_avatar", userAvatar);
    updateHeaderInfo();
    closeProfile();
    haptic("success");
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
                    <div>
                        <strong style="font-size:0.95rem;">${r.name}</strong>
                        <div style="font-size:0.75rem; color:var(--text-muted);">ID: #${r.id} | O'yinchilar: ${r.count}</div>
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
            if (data.banned) {
                alert("Siz avvalgi o'yinni tashlab chiqqansiz! O'sha match tugamaguncha yangi o'yinga kira olmaysiz.");
                return;
            }
            if (data.room_id) {
                joinRoom(data.room_id);
            } else {
                alert("Bo'sh xona yo'q. Yangi xona yarating!");
            }
        });
}

function confirmCreateRoom() {
    const input = document.getElementById("new-room-name-input");
    const rName = input.value.trim() || `Xona_${Math.floor(Math.random() * 900 + 100)}`;
    fetch("/api/create_room", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: rName, user_id: userId })
    })
    .then(res => res.json())
    .then(data => {
        if (data.banned) {
            alert("Siz jazolangansiz! Avvalgi o'yiningiz hali tugamagan.");
            return;
        }
        closeCreateRoomModal();
        joinRoom(data.room_id);
    });
}

function joinRoom(roomId) {
    currentRoomId = roomId;
    document.getElementById("lobby-view").style.display = "none";
    document.getElementById("game-view").style.display = "block";

    const query = `name=${encodeURIComponent(userName)}&avatar=${encodeURIComponent(userAvatar)}&frame=${encodeURIComponent(userFrame)}`;
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/${roomId}/${userId}?${query}`);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === "banned_alert") {
            alert(data.text);
            leaveRoomLocally();
            return;
        }
        if (data.type === "room_closed") {
            alert("Xona egasi chiqib ketganligi sababli xona yopildi!");
            leaveRoomLocally();
            return;
        }
        if (data.type === "room_info") {
            document.getElementById("room-display-name").innerText = data.name;
            document.getElementById("room-display-id").innerText = `ID: #${data.id}`;
        }
        else if (data.type === "is_admin") {
            isHost = true;
            document.getElementById("host-panel").style.display = "block";
        }
        else if (data.type === "kicked") {
            alert("Siz xonadan chetlatildingiz!");
            leaveRoomLocally();
        }
        else if (data.type === "your_role") {
            myRole = data.role;
            const badge = document.getElementById("player-role-badge");
            badge.className = `badge badge-${myRole}`;
            const map = { mafia: "🔫 Mafia", citizen: "👤 Fuqaro", doctor: "💉 Doktor", commissar: "🔍 Komissar" };
            badge.innerText = map[myRole] || myRole;
            showRoleModal(myRole);
        }
        else if (data.type === "phase_change") {
            currentVotesData = {};
            renderPlayersList();
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
            currentPlayersData = data.players;
            renderPlayersList();
        }
        else if (data.type === "vote_update") {
            currentVotesData = data.votes;
            renderPlayersList();
            appendChat("SUD", `${data.voter_name} ➔ ${data.target_name} ga ovoz berdi!`, false, true);
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

    if (data.phase === "discussion") {
        body.className = "day-mode";
        title.innerText = "☀️ KUNDUZGI MUHOKAMA";
        chatForm.style.display = isAlive ? "flex" : "none";
        actionsPanel.style.display = "none";
        haptic("medium");
    }
    else if (data.phase === "voting" || data.phase === "revoting") {
        body.className = "day-mode";
        title.innerText = data.phase === "revoting" ? "⚖️ QAYTA OVOZ BERISH (30s)" : "🗳 OVOZ BERISH (30s)";
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
    else if (data.phase === "night") {
        body.className = "night-mode";
        title.innerText = "🌙 TUN BOSQICHI";
        chatForm.style.display = "none";
        haptic("medium");

        if (isAlive && ["mafia", "doctor", "commissar"].includes(myRole)) {
            actionsPanel.style.display = "block";
            document.getElementById("action-title").innerText = 
                myRole === "mafia" ? "Mafia: Nishonni tanlang:" :
                myRole === "doctor" ? "Doktor: Kimni davolaysiz?" : "Komissar: Kimni tekshirasiz?";

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

function renderPlayersList() {
    const list = document.getElementById("players-list");
    list.innerHTML = "";

    currentPlayersData.forEach(p => {
        const div = document.createElement("div");
        div.className = `player-item ${p.is_alive ? 'alive' : 'dead'}`;
        
        let kickBtn = "";
        if (isHost && p.id !== userId && currentRoomId) {
            kickBtn = `<button class="btn-sm btn-danger" onclick="kickPlayer('${p.id}')">Chiqarish</button>`;
        }

        const voters = [];
        for (const [voterName, targetId] of Object.entries(currentVotesData)) {
            if (targetId === p.id) voters.push(voterName);
        }

        let votesDisplay = "";
        if (voters.length > 0) {
            votesDisplay = `<div class="votes-sub-row">🗳 Ovozlar (${voters.length}): ${voters.join(", ")}</div>`;
        }

        div.innerHTML = `
            <div class="player-top-row">
                <div class="player-meta">
                    <div class="avatar-box ${p.frame || 'frame-none'}">
                        <img class="avatar-img" src="${p.avatar || defaultAvatars[0]}" alt="avatar">
                    </div>
                    <span><strong>${p.name}</strong> ${p.id === userId ? '<b>(Siz)</b>' : ''}</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span>${p.is_alive ? '🟢 Tirik' : '💀 O\'lgan'}</span>
                    ${kickBtn}
                </div>
            </div>
            ${votesDisplay}
        `;
        list.appendChild(div);
    });
}

function kickPlayer(targetId) {
    if (confirm("Bu o'yinchini chiqarib yubormoqchimisiz?")) {
        ws.send(JSON.stringify({ action: "kick", target_id: targetId }));
        haptic("warning");
    }
}

function leaveRoom() {
    if (confirm("Haqiqatan ham xonadan chiqib asosiy menyuga qaytmoqchimisiz?")) {
        if (ws) {
            ws.send(JSON.stringify({ action: "leave" }));
            ws.close();
        }
        leaveRoomLocally();
    }
}

function leaveRoomLocally() {
    currentRoomId = null;
    isHost = false;
    document.getElementById("game-view").style.display = "none";
    document.getElementById("lobby-view").style.display = "block";
    refreshRooms();
    haptic("light");
}

function submitChat() {
    const input = document.getElementById("chat-text-input");
    const text = input.value.trim();
    if (!text || !isAlive) return;

    if (!ws || ws.readyState !== WebSocket.OPEN) {
        alert("Server bilan aloqa yo'q!");
        return;
    }

    ws.send(JSON.stringify({ action: "chat", text: text }));
    input.value = "";
    haptic("light");
}

function appendChat(sender, text, isSystem = false, isVote = false) {
    const box = document.getElementById("chat-messages");
    const m = document.createElement("div");
    m.className = "chat-bubble" + (isSystem ? " system" : "") + (isVote ? " vote-event" : "");
    m.innerHTML = isSystem ? `📢 ${text}` : `<strong>${sender}:</strong> ${text}`;
    box.appendChild(m);
    box.scrollTop = box.scrollHeight;
}

function updateTimer(sec) {
    ws.send(JSON.stringify({ action: "set_timer", seconds: sec }));
}

function startGame() {
    ws.send(JSON.stringify({ action: "start_game" }));
    document.getElementById("host-panel").style.display = "none";
}

updateHeaderInfo();
refreshRooms();
setInterval(refreshRooms, 5000);