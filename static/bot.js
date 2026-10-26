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

// Telegram foydalanuvchi ma'lumotlarini avtomatik to'ldirish
if (tg?.initDataUnsafe?.user) {
    const u = tg.initDataUnsafe.user;
    if (!userName && u.first_name) {
        userName = u.first_name.slice(0, 6);
        localStorage.setItem("mafia_username", userName);
    }
    if (!localStorage.getItem("mafia_avatar") && u.photo_url) {
        userAvatar = u.photo_url;
        localStorage.setItem("mafia_avatar", userAvatar);
    }
}

function syncUserProfile() {
    if (!userId) return;
    const sendAvatar = (userAvatar && userAvatar.startsWith("data:")) ? "" : (userAvatar || "");
    fetch("/api/sync_profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            user_id: userId,
            name: userName || "O'yinchi",
            avatar: sendAvatar
        })
    }).catch(() => {});
}

if (userName) {
    syncUserProfile();
}

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
    rais: {
        title: "👑 RAIS",
        img: "/static/roles/rais.jpg",
        desc: "Siz qishloq raisisiz (Tinch aholi tomoni)! O'yinda 1 marta kunduzi o'z rolingizni ochiqlashingiz mumkin. Shundan keyin ovozingiz 2 barobar kuchga ega bo'ladi!"
    },
    mafiaboshi: {
        title: "👑 MAFIABOSHI",
        img: "/static/roles/mafiaboshi.jpg",
        desc: "Siz shahar mafialarining boshlig'isiz! Jamoadoshlaringiz bilan birgalikda begunohlarni yo'q qiling. Eng asosiysi: Izquvar tekshirganida siz «Tinch aholi» bo'lib ko'rinasiz!"
    },
    mirshab: {
        title: "👮 MIRSHAB",
        img: "/static/roles/mirshab.jpg",
        desc: "Siz qurolli mirshabsiz (Tinch aholi tomoni)! 2 ta o'qingiz bor, 1-kechadan otishingiz mumkin. 2-kechadan Izquvar tekshiruvlarini ko'rasiz. Ehtiyot bo'ling: begunohni otsangiz ishdan bo'shatilasiz!"
    },
    xufya: {
        title: "🕵️ XUFYA",
        img: "/static/roles/xufya.jpg",
        desc: "Siz mafiyaning maxfiy josusisiz! Hech kimni o'ldirmaysiz, lekin har kecha bitta odamning aniq rolini bilib olasiz. Izquvarga Mafia bo'lib ko'rinasiz."
    },
    mafia: {
        title: "🔫 MAFIA",
        img: "/static/roles/mafia.jpg",
        desc: "Siz shafqatsiz mafiasiz! Tunda jamoadoshlaringiz bilan birgalikda begunohlarni yo'q qiling. Kunduzi o'zingizni oddiy fuqarodek tuting."
    },
    doctor: {
        title: "💉 DOKTOR (SHIFOKOR)",
        img: "/static/roles/doktor.jpg",
        desc: "Siz shahar shifokorisisiz! Tunda kimnidir davolang va uni tungi suiqasddan asrab qoling. Bir odamni ketma-ket ikki kecha davolay olmaysiz."
    },
    commissar: {
        title: "🔍 IZQUVAR (TERGOVCHI)",
        img: "/static/roles/izquvar.jpg",
        desc: "Siz shahar tergovchisisiz! Har kecha bitta odamni tekshirib, uning mafia yoki tinch fuqaro ekanini aniqlaysiz. (Mafiaboshi fuqaro bo'lib ko'rinadi)."
    },
    citizen: {
        title: "👤 TINCH AHOLI",
        img: "/static/roles/aholi.jpg",
        desc: "Siz tinch aholi vakilisiz. Muhokamada qatnashib, haqiqiy mafialarni topib osishga ovoz bering!"
    }
};

function toggleTheme() {
    document.body.classList.toggle("light-theme");
    const isLight = document.body.classList.contains("light-theme");
    document.getElementById("theme-toggle-btn").innerText = isLight ? "☀️" : "🌓";
}

// Rasmni avtomatik siqish (Canvas orqali 120x120 JPEG ga aylantirish)
function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
        alert("Rasm hajmi juda katta! Iltimos, 5MB dan kichik rasm tanlang.");
        return;
    }

    const reader = new FileReader();
    reader.onload = function(e) {
        const img = new Image();
        img.onload = function() {
            const canvas = document.createElement("canvas");
            const maxDim = 120;
            let w = img.width, h = img.height;
            if (w > h) {
                h = (h / w) * maxDim;
                w = maxDim;
            } else {
                w = (w / h) * maxDim;
                h = maxDim;
            }
            canvas.width = w;
            canvas.height = h;
            const ctx = canvas.getContext("2d");
            ctx.drawImage(img, 0, 0, w, h);
            userAvatar = canvas.toDataURL("image/jpeg", 0.75);
            document.getElementById("prof-preview-avatar").src = userAvatar;
        };
        img.src = e.target.result;
    };
    reader.readAsDataURL(file);
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
        })
        .catch(() => {});

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

    syncUserProfile();

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: "update_profile",
            name: userName,
            avatar: userAvatar
        }));
    }
}

if (!userName || userName.length > 6) {
    openProfile(true);
}

function selectTime(sec) {
    selectedTimerMinutes = sec;
    document.querySelectorAll(".time-tab-btn").forEach(b => b.classList.remove("active"));
    document.getElementById(`tab-${sec}`).classList.add("active");
}

// ==========================================
// KANAL OBUNASI VA TEKSHIRISH
// ==========================================
let isSubscribed = false;
let channelUrl = "https://t.me/durbeh";
let channelId = "@durbeh";
let requireSub = true;

function checkInitialSubscription() {
    fetch("/api/channel_info")
        .then(r => r.json())
        .then(info => {
            if (info.channel_url) channelUrl = info.channel_url;
            if (info.channel_id) channelId = info.channel_id;
            requireSub = info.require_sub;
            const handleEl = document.getElementById("sub-channel-handle");
            if (handleEl) handleEl.innerText = channelId;

            if (!requireSub) {
                isSubscribed = true;
                return;
            }

            fetch(`/api/check_sub?user_id=${userId}`)
                .then(r => r.json())
                .then(d => {
                    isSubscribed = d.subscribed;
                    if (!isSubscribed) {
                        document.getElementById("modal-channel-sub").style.display = "flex";
                    }
                })
                .catch(() => {});
        })
        .catch(() => {});
}

function openChannelLink() {
    if (tg && tg.openTelegramLink) {
        tg.openTelegramLink(channelUrl);
    } else {
        window.open(channelUrl, "_blank");
    }
}

function verifySubscription(isManual = false) {
    const btn = document.getElementById("btn-check-sub");
    if (btn) btn.innerText = "⏳ Tekshirilmoqda...";

    fetch(`/api/check_sub?user_id=${userId}`)
        .then(r => r.json())
        .then(d => {
            if (btn) btn.innerText = "✅ A'zo bo'ldim (Tekshirish)";
            if (d.subscribed) {
                isSubscribed = true;
                document.getElementById("sub-error-msg").style.display = "none";
                document.getElementById("sub-success-msg").style.display = "block";
                setTimeout(() => {
                    document.getElementById("modal-channel-sub").style.display = "none";
                    document.getElementById("sub-success-msg").style.display = "none";
                }, 800);
            } else {
                isSubscribed = false;
                document.getElementById("sub-success-msg").style.display = "none";
                document.getElementById("sub-error-msg").style.display = "block";
                if (isManual) {
                    alert("❌ Siz hali " + channelId + " kanaliga a'zo bo'lmadingiz! Iltimos, oldin kanalga a'zo bo'ling.");
                }
            }
        })
        .catch(() => {
            if (btn) btn.innerText = "✅ A'zo bo'ldim (Tekshirish)";
        });
}

// ==========================================
// REYTING VA TOP O'YINCHILAR (FAQAT HAQIQIY O'YINCHILAR)
// ==========================================
let currentLeaderboardTab = "top";

function openLeaderboardModal() {
    syncUserProfile();
    document.getElementById("modal-leaderboard").style.display = "flex";
    switchLeaderboardTab(currentLeaderboardTab);
}

function closeLeaderboardModal() {
    document.getElementById("modal-leaderboard").style.display = "none";
}

function switchLeaderboardTab(type) {
    currentLeaderboardTab = type;
    const tabTop = document.getElementById("lb-tab-top");
    const tabMafia = document.getElementById("lb-tab-mafia");
    if (tabTop) tabTop.classList.toggle("active", type === "top");
    if (tabMafia) tabMafia.classList.toggle("active", type === "mafia");
    loadLeaderboardData(type);
}

async function loadLeaderboardData(type) {
    const box = document.getElementById("lb-list-box");
    if (!box) return;
    box.innerHTML = `
        <div style="text-align:center; padding:30px 10px; color:var(--text-muted); font-size:0.8rem;">
            ⏳ Haqiqiy o'yinchilar reytingi yuklanmoqda...
        </div>
    `;

    try {
        const resp = await fetch(`/api/leaderboard?type=${encodeURIComponent(type)}&user_id=${encodeURIComponent(userId)}`);
        const data = await resp.json();
        const players = data.players || [];
        const myRank = data.my_rank || {};

        // Mening o'rnim bannerini yangilash
        const myNameEl = document.getElementById("lb-my-name");
        const myWinsEl = document.getElementById("lb-my-wins");
        if (myNameEl) {
            const rankLabel = myRank.rank ? ` (#${myRank.rank})` : "";
            myNameEl.innerText = (myRank.name || userName || "O'yinchi") + rankLabel;
        }
        if (myWinsEl) {
            myWinsEl.innerText = `${myRank.wins || 0} g'alaba`;
        }

        if (players.length === 0) {
            box.innerHTML = `
                <div style="text-align:center; padding:35px 15px; color:var(--text-muted); font-size:0.82rem;">
                    🏆 Hozircha reytingda o'yinlar ro'yxatga olinmagan.<br>
                    <span style="font-size:0.75rem; color:var(--gold); display:inline-block; margin-top:6px;">
                        O'yinga kiring va birinchi bo'lib g'alaba qozoning!
                    </span>
                </div>
            `;
            return;
        }

        box.innerHTML = "";
        players.forEach((p, idx) => {
            const isMe = (String(p.user_id) === String(userId));
            const item = document.createElement("div");
            item.className = `leaderboard-item ${idx === 0 ? 'top-1' : ''} ${isMe ? 'is-me' : ''}`;
            const avatarSrc = p.avatar || presetAvatars[idx % presetAvatars.length];

            item.innerHTML = `
                <span class="lb-rank-badge">${p.rank}</span>
                <img src="${avatarSrc}" class="lb-avatar" onerror="this.src='${presetAvatars[0]}'">
                <div class="lb-info">
                    <div class="lb-name">
                        ${p.name} ${isMe ? '<span class="lb-me-tag">Siz</span>' : ''}
                    </div>
                    <div class="lb-role-title">${p.role}</div>
                </div>
                <div class="lb-score">
                    ${p.score_text}<br>
                    <span style="font-size:0.65rem; color:var(--text-muted);">${p.rate}</span>
                </div>
            `;
            box.appendChild(item);
        });

    } catch (e) {
        box.innerHTML = `
            <div style="text-align:center; padding:30px; color:var(--text-muted); font-size:0.8rem;">
                ⚠️ Reytingni yuklashda xatolik yuz berdi.
            </div>
        `;
    }
}

function openCreateRoomModal() {
    if (!isSubscribed && requireSub) {
        document.getElementById("modal-channel-sub").style.display = "flex";
        alert("O'yin xonasini yaratish uchun avval rasmiy kanalimizga obuna bo'ling!");
        return;
    }
    if (!userName || userName.length > 6) {
        openProfile(true);
        return;
    }
    document.getElementById("modal-create-room").style.display = "flex";
}

function closeCreateRoomModal() {
    document.getElementById("modal-create-room").style.display = "none";
}

function openGuideModal(tabName = 'rules') {
    switchGuideTab(tabName);
    document.getElementById("modal-guide").style.display = "flex";
}

function closeGuideModal() {
    document.getElementById("modal-guide").style.display = "none";
}

function switchGuideTab(tabName) {
    const tabs = ['rules', 'about', 'roles'];
    tabs.forEach(t => {
        const btn = document.getElementById(`tab-btn-${t}`);
        const content = document.getElementById(`guide-tab-${t}`);
        if (btn) btn.classList.toggle('active', t === tabName);
        if (content) content.style.display = (t === tabName) ? 'block' : 'none';
    });
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
        })
        .catch(() => {});
}

function quickJoin() {
    if (!isSubscribed && requireSub) {
        document.getElementById("modal-channel-sub").style.display = "flex";
        alert("Tezkor qo'shilish uchun avval rasmiy kanalimizga obuna bo'ling!");
        return;
    }
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
    if (!isSubscribed && requireSub) {
        document.getElementById("modal-channel-sub").style.display = "flex";
        alert("Xona yaratish uchun avval rasmiy kanalimizga obuna bo'ling!");
        return;
    }
    const rName = document.getElementById("cr-room-name").value.trim() || "Bordo xona";
    const hostAva = userAvatar.startsWith("data:") ? presetAvatars[0] : userAvatar;
    fetch("/api/create_room", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            name: rName,
            time_sec: selectedTimerMinutes,
            host_name: userName,
            host_avatar: hostAva
        })
    })
    .then(r => r.json())
    .then(d => {
        closeCreateRoomModal();
        joinRoom(d.room_id);
    });
}

function joinRoom(roomId) {
    if (!isSubscribed && requireSub) {
        document.getElementById("modal-channel-sub").style.display = "flex";
        alert("O'yinga kirish uchun avval rasmiy kanalimizga obuna bo'ling!");
        return;
    }
    currentRoomId = roomId;
    isAlive = true;
    document.getElementById("screen-home").style.display = "none";
    document.getElementById("screen-game").style.display = "flex";

    // URL parametriga faqat qisqa avatar qo'yish (414 xatoligini oldini olish)
    const initialAvatar = userAvatar.startsWith("data:") ? "" : userAvatar;
    const q = `name=${encodeURIComponent(userName)}&avatar=${encodeURIComponent(initialAvatar)}`;
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/${roomId}/${userId}?${q}`);

    ws.onopen = () => {
        // Agar o'ziga xos rasm yuklangan bo'lsa, uni websocket orqali yangilaymiz
        if (userAvatar) {
            ws.send(JSON.stringify({
                action: "update_profile",
                name: userName,
                avatar: userAvatar
            }));
        }
    };

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
            let desc = r.desc;
            if (["mafia", "mafiaboshi", "xufya"].includes(myRole) && d.partners && d.partners.length > 0) {
                desc += "\n\n👥 Sizning mafia sheriklaringiz: " + d.partners.join(", ");
            }
            if (myRole === "mirshab") {
                desc += "\n\n🎯 Sizda 2 ta o'q bor! Begunoh fuqaroni otsangiz, ishdan bo'shatilasiz.";
            }
            document.getElementById("role-desc-card").innerText = desc;
            document.getElementById("modal-role").style.display = "flex";
        }
        else if (d.type === "commissar_result") {
            appendChatBubble("Tergovchi", presetAvatars[0], "🔍 TERGOV NATIJASI: " + d.text, false, true, false);
            alert("🔍 TERGOV NATIJASI:\n" + d.text);
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
            
            // O'yinchi holatini (tirik/o'lik) aniqlash
            const me = d.players.find(p => p.id === userId);
            if (me) {
                isAlive = me.is_alive;
                if (!isAlive) {
                    document.getElementById("action-panel").style.display = "none";
                    const badge = document.getElementById("phase-badge");
                    if (badge && !badge.innerText.includes("KUZATUVCHI")) {
                        badge.innerText += " (Kuzatuvchi)";
                    }
                }
            }
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

    ws.onclose = () => {
        // Aloqa uzilsa
    };
}

function updateHostStartButtonVisibility() {
    const startBtn = document.getElementById("host-start-btn");
    const restartBtn = document.getElementById("host-restart-btn");
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
        restartBtn.style.display = "none";
        waitHint.style.display = "none";
    }
}

function handlePhaseChange(d) {
    const badge = document.getElementById("phase-badge");
    const actPanel = document.getElementById("action-panel");
    const actBox = document.getElementById("action-buttons-box");
    const restartBtn = document.getElementById("host-restart-btn");
    const startBtn = document.getElementById("host-start-btn");
    const raisBar = document.getElementById("rais-action-bar");
    const appWrapper = document.querySelector(".app-wrapper");
    
    actBox.innerHTML = "";
    currentVotesData = {};
    renderHorizontalPlayers();

    isLastWordPhase = (d.phase === "last_word");
    lastWordSpeakerId = d.speaker_id || null;

    // Orqa fonni kun/tun fazasiga qarab siljitish
    if (d.phase === "night") {
        if (appWrapper) {
            appWrapper.classList.remove("phase-day");
            appWrapper.classList.add("phase-night");
        }
    } else if (d.phase === "discussion" || d.phase === "voting") {
        if (appWrapper) {
            appWrapper.classList.remove("phase-night");
            appWrapper.classList.add("phase-day");
        }
    } else {
        if (appWrapper) {
            appWrapper.classList.remove("phase-night", "phase-day");
        }
    }

    if (d.phase === "lobby") {
        badge.innerText = "Kutish zali";
        badge.style.color = "var(--gold)";
        actPanel.style.display = "none";
        if (raisBar) raisBar.style.display = "none";
        if (restartBtn) restartBtn.style.display = "none";
        updateHostStartButtonVisibility();
    }
    else if (d.phase === "discussion") {
        badge.innerText = isAlive ? "☀️ Kunduzgi Muhokama" : "☀️ Kunduzgi Muhokama (Kuzatuvchi)";
        badge.style.color = "var(--gold)";
        actPanel.style.display = "none";
        if (startBtn) startBtn.style.display = "none";
        if (restartBtn) restartBtn.style.display = "none";

        // Rais ochiqlash tugmasi
        const me = currentPlayersData.find(p => p.id === userId);
        if (raisBar) {
            raisBar.style.display = (myRole === "rais" && isAlive && me && !me.rais_revealed) ? "block" : "none";
        }
    }
    else if (d.phase === "voting" || d.phase === "revoting") {
        badge.innerText = "🗳 Ovoz berish (30s)";
        badge.style.color = "var(--blue)";
        const me = currentPlayersData.find(p => p.id === userId);
        if (raisBar) {
            raisBar.style.display = (myRole === "rais" && isAlive && me && !me.rais_revealed) ? "block" : "none";
        }

        if (isAlive) {
            actPanel.style.display = "block";
            document.getElementById("action-title").innerText = "Gumonlanuvchini tanlang:";
            (d.candidates || []).forEach(c => {
                if (c.id !== userId) {
                    const b = document.createElement("button");
                    b.className = "time-tab-btn";
                    b.innerText = c.name;
                    b.onclick = () => {
                        ws.send(JSON.stringify({ action: "vote", target_id: c.id }));
                        actPanel.style.display = "none";
                    };
                    actBox.appendChild(b);
                }
            });
        }
    }
    else if (d.phase === "night") {
        badge.innerText = "🌙 Tun bosqichi";
        badge.style.color = "#a55eea";
        if (raisBar) raisBar.style.display = "none";

        const activeNightRoles = ["mafia", "mafiaboshi", "doctor", "commissar", "mirshab", "xufya"];
        if (isAlive && activeNightRoles.includes(myRole)) {
            // Agar Mirshab ishdan bo'shatilgan yoki o'qi tugagan bo'lsa
            if (myRole === "mirshab" && (d.disarmed || (d.bullets !== undefined && d.bullets <= 0))) {
                actPanel.style.display = "none";
                return;
            }

            actPanel.style.display = "block";
            let titleText = "Nishonni tanlang:";
            if (myRole === "mafia") {
                titleText = "🔫 Mafia nishoni (Qurbonni tanlang):";
            } else if (myRole === "mafiaboshi") {
                titleText = "👑 Mafiaboshi nishoni (Qurbonni tanlang):";
            } else if (myRole === "doctor") {
                titleText = "💉 Davolash: Kimni o'limdan qutqarasiz?";
            } else if (myRole === "commissar") {
                titleText = "🔍 Izquvar: Kimning kimligini tekshirasiz?";
            } else if (myRole === "mirshab") {
                const bCount = d.bullets !== undefined ? d.bullets : 2;
                titleText = `👮 Mirshab: Nishonga o'q uzish (${bCount} ta o'q):`;
            } else if (myRole === "xufya") {
                titleText = "🕵️ Xufya (Josus): Kimning aniq rolini bilmoqchisiz?";
            }

            document.getElementById("action-title").innerText = titleText;

            // Agar Mirshab bo'lsa va Izquvar ma'lumotlari bo'lsa, eslatma
            if (myRole === "mirshab" && d.izquvar_hints && Object.keys(d.izquvar_hints).length > 0) {
                const hintDiv = document.createElement("div");
                hintDiv.style.cssText = "font-size:0.72rem; color:var(--gold); margin-bottom:6px; background:rgba(245,176,65,0.1); padding:4px 8px; border-radius:6px; width:100%;";
                let hintsList = [];
                for (const h of Object.values(d.izquvar_hints)) {
                    hintsList.push(`${h.name} (${h.is_mafia ? '🚨 Mafia' : '👤 Fuqaro'})`);
                }
                hintDiv.innerHTML = `🔍 <b>Izquvar natijalari:</b> ${hintsList.join(", ")}`;
                actBox.appendChild(hintDiv);
            }

            (d.targets || []).forEach(t => {
                if (["mafia", "mafiaboshi", "commissar", "xufya"].includes(myRole) && t.id === userId) {
                    return;
                }
                const b = document.createElement("button");
                b.className = "time-tab-btn";
                b.innerText = t.name;
                b.onclick = () => {
                    ws.send(JSON.stringify({ action: "night_action", target_id: t.id }));
                    actPanel.style.display = "none";
                };
                actBox.appendChild(b);
            });

            // Mirshab uchun bu tunda otmaslik (skip)
            if (myRole === "mirshab") {
                const skipBtn = document.createElement("button");
                skipBtn.className = "time-tab-btn";
                skipBtn.style.color = "var(--text-muted)";
                skipBtn.innerText = "⏭ Bu kecha otmaslik";
                skipBtn.onclick = () => {
                    actPanel.style.display = "none";
                };
                actBox.appendChild(skipBtn);
            }
        }
    }
    else if (d.phase === "last_word") {
        badge.innerText = "🎤 OXIRGI SO'Z BOSQICHI";
        badge.style.color = "var(--red)";
        actPanel.style.display = "none";
        if (raisBar) raisBar.style.display = "none";
    }
    else if (d.phase === "game_over") {
        const isMafiaGroup = ["mafia", "mafiaboshi", "xufya"].includes(myRole);
        const isWin = (d.winner === "mafia" && isMafiaGroup) || (d.winner === "citizens" && !isMafiaGroup);
        badge.innerText = isWin ? "🏆 SIZ G'ALABA QOZONDINGIZ!" : "💀 O'YIN TUGADI";
        badge.style.color = isWin ? "var(--green)" : "var(--red)";
        actPanel.style.display = "none";
        if (raisBar) raisBar.style.display = "none";
        if (isHost && restartBtn) {
            restartBtn.style.display = "block";
        }
    }
}

function revealRais() {
    if (ws && myRole === "rais") {
        ws.send(JSON.stringify({ action: "reveal_rais" }));
        const rBar = document.getElementById("rais-action-bar");
        if (rBar) rBar.style.display = "none";
    }
}

function restartGame() {
    if (ws && isHost) {
        ws.send(JSON.stringify({ action: "restart_game" }));
    }
}

function renderHorizontalPlayers() {
    const box = document.getElementById("players-horizontal");
    if (!box) return;
    box.innerHTML = "";
    currentPlayersData.forEach(p => {
        const col = document.createElement("div");
        col.className = `player-bubble-col ${p.is_alive ? 'alive' : 'dead'}`;
        
        let voteCount = 0;
        for (const target of Object.values(currentVotesData)) {
            if (target === p.id) voteCount++;
        }

        col.innerHTML = `
            <div style="position:relative; display:inline-block;">
                <img src="${p.avatar || presetAvatars[0]}" class="player-avatar-circle">
                ${p.rais_revealed ? '<span style="position:absolute; bottom:-3px; right:-3px; font-size:0.75rem;" title="Rais (Ovozi 2x)">👑</span>' : ''}
            </div>
            <span class="player-bubble-name">${p.rais_revealed ? '👑 ' : ''}${p.name}</span>
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

    if (!isAlive && !isLastWordPhase) {
        alert("Siz o'yindan chiqqansiz, faqat kuzatuvchi sifatida qatnasha olasiz.");
        return;
    }

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
checkInitialSubscription();
