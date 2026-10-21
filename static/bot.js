const tg = window.Telegram?.WebApp;
if (tg) {
    tg.expand();
    tg.ready();
}

const userId = tg?.initDataUnsafe?.user?.id 
    ? String(tg.initDataUnsafe.user.id) 
    : "id_" + Math.floor(Math.random() * 89999 + 10000);

const presetAvatars = [
    "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=120&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1570295999919-56ceb5ecca61?w=120&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=120&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1628157582853-a796fa650a6a?w=120&auto=format&fit=crop&q=80"
];

let userName = localStorage.getItem("mafia_username") || "";
let userAvatar = localStorage.getItem("mafia_avatar") || presetAvatars[0];

const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
let ws = null;
let currentRoomId = null;
let isHost = false;
let myRole = "citizen";
let isAlive = true;
let isLastWordPhase = false;
let lastWordSpeakerId = null;
let selectedTimerMinutes = 60;
let currentVotesData = {};
let currentPlayersData = [];

const roleAssets = {
    mafia: {
        title: "🔫 MAFIA",
        img: "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=600&auto=format&fit=crop&q=80",
        desc: "Siz shafqatsiz mafiasiz! Tunda sheriklaringiz bilan birgalikda begunohlarni yo'q qiling. Kunduzi o'zingizni oddiy fuqarodek tuting."
    },
    doctor: {
        title: "💉 SHIFOKOR",
        img: "https://images.unsplash.com/photo-1579684385127-1ef15d508118?w=600&auto=format&fit=crop&q=80",
        desc: "Siz shahar shifokorisisiz! Tunda kimnidir davolang va uni mafianing o'qidan asrab qoling."
    },
    commissar: {
        title: "🔍 KOMISSAR",
        img: "https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=600&auto=format&fit=crop&q=80",
        desc: "Siz tergovchisiz! Har kecha bitta odamni tekshirib, uning mafia ekanini aniqlang."
    },
    citizen: {
        title: "👤 TINCH FUQARO",
        img: "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=600&auto=format&fit=crop&q=80",
        desc: "Siz tinch aholi vakilisiz. Muhokamada qatnashib, haqiqiy mafialarni topib osishga ovoz bering!"
    }
};

function toggleTheme() {
    document.body.classList.toggle("light-theme");
    const isLight = document.body.classList.contains("light-theme");
    document.getElementById("theme-toggle-btn").innerText = isLight ? "☀️" : "🌓";
}

function handleFileUpload(event) {
    const file = event.target.files[0];
    if (file) {
        if (file.size > 2 * 1024 * 1024) {
            alert("Rasm hajmi 2MB dan kichik bo'lishi kerak!");
            return;
        }
        const reader = new FileReader();
        reader.onload = function(e) {
            userAvatar = e.target.result;
            document.getElementById("prof-preview-avatar").src = userAvatar;
        };
        reader.readAsDataURL(file);
    }
}

function renderPresetAvatars() {
    const box = document.getElementById("avatar-presets-box");
    box.innerHTML = "";
    presetAvatars.forEach(url => {
        const img = document.createElement("img");
        img.src = url;
        img.style = "width:34px; height:34px; border-radius:50%; object-fit:cover; cursor:pointer;";
        img.onclick = () => {
            userAvatar = url;
            document.getElementById("prof-preview-avatar").src = url;
        };
        box.appendChild(img);
    });
}

function openProfile(isMandatory = false) {
    renderPresetAvatars();
    document.getElementById("prof-preview-avatar").src = userAvatar;
    document.getElementById("prof-input-name").value = userName;
    
    document.getElementById("prof-modal-title").innerText = 
        isMandatory ? "👋 Xush kelibsiz! Ismingizni kiriting" : "👤 Profil ma'lumotlari";

    fetch(`/api/profile/${userId}`)
        .then(r => r.json())
        .then(d => {
            document.getElementById("prof-games").innerText = d.games || 0;
            document.getElementById("prof-wins").innerText = d.wins || 0;
            const rate = d.games ? Math.round((d.wins / d.games) * 100) : 0;
            const mafiaRate = d.games ? Math.round(((d.mafia_games || 0) / d.games) * 100) : 0;
            document.getElementById("prof-rate").innerText = rate + "%";
            document.getElementById("prof-mafia-rate").innerText = mafiaRate + "%";
        });

    document.getElementById("modal-profile").style.display = "flex";
}

function closeProfile() {
    if (!userName || userName.length === 0 || userName.length > 6) {
        alert("Ism 1 tadan 6 ta harfgacha bo'lishi shart!");
        return;
    }
    document.getElementById("modal-profile").style.display = "none";
}

function saveProfile() {
    const val = document.getElementById("prof-input-name").value.trim();
    if (!val) {
        alert("Iltimos, ismingizni kiriting!");
        return;
    }
    if (val.length > 6) {
        alert("Ism ko'pi bilan 6 ta harf bo'lishi kerak!");
        return;
    }
    userName = val;
    localStorage.setItem("mafia_username", userName);
    localStorage.setItem("mafia_avatar", userAvatar);
    document.getElementById("modal-profile").style.display = "none";
}

if (!userName || userName.length > 6) {
    openProfile(true);
}

function selectTime(sec) {
    selectedTimerMinutes = sec;
    document.querySelectorAll(".time-tab-btn").forEach(b => b.classList.remove("active"));
    document.getElementById(`tab-${sec}`).classList.add("active");
}

function openCreateRoomModal() {
    if (!userName || userName.length > 6) {
        openProfile(true);
        return;
    }
    document.getElementById("modal-create-room").style.display = "flex";
}

function closeCreateRoomModal() {
    document.getElementById("modal-create-room").style.display = "none";
}

function refreshRooms() {
    fetch("/api/rooms")
        .then(r => r.json())
        .then(data => {
            const list = document.getElementById("rooms-list");
            document.getElementById("active-rooms-count").innerText = `${data.rooms.length} ta xona`;
            if (data.rooms.length === 0) {
                list.innerHTML = `<p style="text-align:center; color:var(--text-muted); padding:30px 0; font-size:0.85rem;">Ochiq xonalar mavjud emas.</p>`;
                return;
            }
            list.innerHTML = "";
            data.rooms.forEach(r => {
                const el = document.createElement("div");
                el.className = "room-card-modern";
                el.onclick = () => joinRoom(r.id);
                el.innerHTML = `
                    <div class="room-title-row">
                        <span class="room-title-name">${r.name}</span>
                        <span class="room-users-count">${r.count}/16</span>
                    </div>
                    <div class="room-author-row">
                        <img src="${r.host_avatar || presetAvatars[0]}" class="room-author-avatar">
                        <span class="room-author-name">${r.host_name}</span>
                    </div>
                    <div class="room-tags-row">
                        <span class="room-tag">👥 4+ kishi</span>
                        <span class="room-tag">⏱ ${r.time_min} daq muhokama</span>
                    </div>
                `;
                list.appendChild(el);
            });
        });
}

function quickJoin() {
    if (!userName || userName.length > 6) {
        openProfile(true);
        return;
    }
    fetch("/api/quick_join")
        .then(r => r.json())
        .then(d => {
            if (d.room_id) joinRoom(d.room_id);
            else alert("Hozircha bo'sh xona yo'q. Yangi xona oching!");
        });
}

function confirmCreateRoom() {
    const rName = document.getElementById("cr-room-name").value.trim() || "Bordo xona";
    fetch("/api/create_room", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            name: rName,
            time_sec: selectedTimerMinutes,
            host_name: userName,
            host_avatar: userAvatar
        })
    })
    .then(r => r.json())
    .then(d => {
        closeCreateRoomModal();
        joinRoom(d.room_id);
    });
}

function joinRoom(roomId) {
    currentRoomId = roomId;
    document.getElementById("screen-home").style.display = "none";
    document.getElementById("screen-game").style.display = "flex";

    const q = `name=${encodeURIComponent(userName)}&avatar=${encodeURIComponent(userAvatar)}`;
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/${roomId}/${userId}?${q}`);

    ws.onmessage = (event) => {
        const d = JSON.parse(event.data);

        if (d.type === "room_info") {
            document.getElementById("in-game-room-name").innerText = d.name;
        }
        else if (d.type === "is_admin") {
            isHost = true;
            updateHostStartButtonVisibility();
        }
        else if (d.type === "room_closed") {
            alert("Xona egasi chiqib ketganligi sababli xona yopildi!");
            leaveRoomLocally();
        }
        else if (d.type === "your_role") {
            myRole = d.role;
            const r = roleAssets[myRole] || roleAssets.citizen;
            document.getElementById("role-img-card").src = r.img;
            document.getElementById("role-title-card").innerText = r.title;
            document.getElementById("role-desc-card").innerText = r.desc;
            document.getElementById("modal-role").style.display = "flex";
        }
        else if (d.type === "phase_change") {
            handlePhaseChange(d);
        }
        else if (d.type === "timer") {
            const m = Math.floor(d.time / 60);
            const s = d.time % 60;
            document.getElementById("game-timer").innerText = `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
        }
        else if (d.type === "players_update") {
            currentPlayersData = d.players;
            document.getElementById("in-game-room-stats").innerText = `${d.players.length}/16 o'yinchi`;
            renderHorizontalPlayers();
            updateHostStartButtonVisibility();
        }
        else if (d.type === "vote_update") {
            currentVotesData = d.votes;
            renderHorizontalPlayers();
        }
        else if (d.type === "chat") {
            appendChatBubble(d.sender, d.avatar, d.text, d.is_self, d.is_system, d.is_last_word);
        }
    };
}

function updateHostStartButtonVisibility() {
    const startBtn = document.getElementById("host-start-btn");
    const waitHint = document.getElementById("players-wait-hint");

    if (isHost) {
        if (currentPlayersData.length >= 4) {
            startBtn.style.display = "block";
            waitHint.style.display = "none";
        } else {
            startBtn.style.display = "none";
            waitHint.style.display = "block";
            waitHint.innerText = `Kamida 4 kishi kerak (${currentPlayersData.length}/4)`;
        }
    } else {
        startBtn.style.display = "none";
        waitHint.style.display = "none";
    }
}

function handlePhaseChange(d) {
    const badge = document.getElementById("phase-badge");
    const actPanel = document.getElementById("action-panel");
    const actBox = document.getElementById("action-buttons-box");
    actBox.innerHTML = "";
    currentVotesData = {};
    renderHorizontalPlayers();

    isLastWordPhase = (d.phase === "last_word");
    lastWordSpeakerId = d.speaker_id || null;

    if (d.phase === "discussion") {
        badge.innerText = "☀️ Kunduzgi Muhokama";
        actPanel.style.display = "none";
    }
    else if (d.phase === "voting" || d.phase === "revoting") {
        badge.innerText = "🗳 Ovoz berish (30s)";
        if (isAlive) {
            actPanel.style.display = "block";
            document.getElementById("action-title").innerText = "Gumonlanuvchini tanlang:";
            d.candidates.forEach(c => {
                const b = document.createElement("button");
                b.className = "time-tab-btn";
                b.innerText = c.name;
                b.onclick = () => {
                    ws.send(JSON.stringify({ action: "vote", target_id: c.id }));
                    actPanel.style.display = "none";
                };
                actBox.appendChild(b);
            });
        }
    }
    else if (d.phase === "night") {
        badge.innerText = "🌙 Tun bosqichi";
        if (isAlive && ["mafia", "doctor", "commissar"].includes(myRole)) {
            actPanel.style.display = "block";
            document.getElementById("action-title").innerText = 
                myRole === "mafia" ? "Mafia nishoni:" : (myRole === "doctor" ? "Davolash:" : "Tekshirish:");
            d.targets.forEach(t => {
                const b = document.createElement("button");
                b.className = "time-tab-btn";
                b.innerText = t.name;
                b.onclick = () => {
                    ws.send(JSON.stringify({ action: "night_action", target_id: t.id }));
                    actPanel.style.display = "none";
                };
                actBox.appendChild(b);
            });
        }
    }
    else if (d.phase === "last_word") {
        badge.innerText = "🎤 OXIRGI SO'Z BOSQICHI";
        actPanel.style.display = "none";
    }
}

function renderHorizontalPlayers() {
    const box = document.getElementById("players-horizontal");
    box.innerHTML = "";
    currentPlayersData.forEach(p => {
        const col = document.createElement("div");
        col.className = `player-bubble-col ${p.is_alive ? 'alive' : 'dead'}`;
        
        let voteCount = 0;
        for (const target of Object.values(currentVotesData)) {
            if (target === p.id) voteCount++;
        }

        col.innerHTML = `
            <img src="${p.avatar || presetAvatars[0]}" class="player-avatar-circle">
            <span class="player-bubble-name">${p.name}</span>
            ${voteCount > 0 ? `<span class="vote-badge-count">${voteCount}</span>` : ''}
        `;
        box.appendChild(col);
    });
}

function sendChat() {
    const inp = document.getElementById("chat-input");
    const val = inp.value.trim();
    if (!val) return;

    if (isLastWordPhase && lastWordSpeakerId !== userId) {
        alert("Hozir faqat o'yindan chiqayotgan odamning oxirgi so'zi eshitiladi!");
        return;
    }

    if (!isAlive && !isLastWordPhase) return;

    ws.send(JSON.stringify({ action: "chat", text: val }));
    inp.value = "";
}

function appendChatBubble(sender, avatar, text, isSelf, isSystem, isLastWord) {
    const box = document.getElementById("chat-messages");
    if (isSystem) {
        const s = document.createElement("div");
        s.className = "tg-msg-system";
        s.innerText = `📢 ${text}`;
        box.appendChild(s);
    } else {
        const row = document.createElement("div");
        row.className = `tg-msg-row ${isSelf ? 'self' : ''} ${isLastWord ? 'last-word-msg' : ''}`;
        row.innerHTML = `
            <img src="${avatar || presetAvatars[0]}" class="tg-msg-avatar">
            <div class="tg-msg-bubble">
                <div class="tg-sender-name">${sender} ${isLastWord ? '(Oxirgi so\'z)' : ''}</div>
                <div class="tg-msg-text">${text}</div>
            </div>
        `;
        box.appendChild(row);
    }
    box.scrollTop = box.scrollHeight;
}

function startGame() {
    if (userName.length > 6) {
        alert("Ismingiz 6 ta harfdan ko'p bo'lsa o'yinni boshlay olmaysiz!");
        return;
    }
    if (currentPlayersData.length < 4) {
        alert("O'yinni boshlash uchun kamida 4 nafar o'yinchi kerak!");
        return;
    }
    ws.send(JSON.stringify({ action: "start_game" }));
    document.getElementById("host-start-btn").style.display = "none";
}

function leaveRoom() {
    if (confirm("Xonadan chiqmoqchimisiz?")) {
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
    document.getElementById("screen-game").style.display = "none";
    document.getElementById("screen-home").style.display = "block";
    refreshRooms();
}

refreshRooms();
setInterval(refreshRooms, 4000);