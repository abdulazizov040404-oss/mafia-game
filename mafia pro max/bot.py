import os
import asyncio
import random
import html
from typing import Dict, List, Optional
from collections import Counter
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import httpx

# ==========================================================
# .ENV YUKLOVCHI VA SOZLAMALAR
# ==========================================================
def load_env(filepath=".env"):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            print(f"⚠️ .env yuklashda xatolik: {e}")

load_env()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
# Agar .env bo'sh bo'lsa yoki eski kod bo'lsa:
if TG_BOT_TOKEN == "SIZNING_BOT_TOKENINGIZ":
    TG_BOT_TOKEN = ""

CHANNEL_ID = os.getenv("CHANNEL_ID", "@durbeh").strip()
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/durbeh").strip()
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://SIZNING_RENDER_URL.onrender.com").strip()
REQUIRE_SUB = os.getenv("REQUIRE_SUB", "false").lower() in ["true", "1", "yes"]

app = FastAPI()

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "index.html topilmadi."}

stats_db: Dict[str, dict] = {}

@app.get("/api/profile/{user_id}")
async def get_profile(user_id: str):
    data = stats_db.get(user_id, {"games": 0, "wins": 0, "mafia_games": 0})
    return JSONResponse(data)

class Player:
    def __init__(self, user_id: str, name: str, avatar: str, ws: Optional[WebSocket]):
        self.id = user_id
        self.name = name
        self.avatar = avatar
        self.ws = ws
        self.role = "citizen"
        self.is_alive = True

class GameRoom:
    def __init__(self, room_id: str, name: str, time_sec: int, host_name: str, host_avatar: str):
        self.id = room_id
        self.name = name
        self.host_id: Optional[str] = None
        self.host_name = host_name
        self.host_avatar = host_avatar
        self.players: Dict[str, Player] = {}
        self.phase: str = "lobby"
        self.discussion_time: int = time_sec
        self.remaining_time: int = time_sec
        self.votes: Dict[str, str] = {}
        self.night_actions: Dict[str, str] = {}
        self.chat_history: List[dict] = []
        self.last_word_speaker_id: Optional[str] = None
        self.last_healed_id: Optional[str] = None
        self.winner: Optional[str] = None
        self.task: Optional[asyncio.Task] = None

rooms: Dict[str, GameRoom] = {}

class CreateRoomRequest(BaseModel):
    name: str
    time_sec: int = 60
    host_name: str = "Host"
    host_avatar: str = ""

@app.post("/api/create_room")
async def create_room_api(payload: CreateRoomRequest):
    room_id = str(random.randint(1000, 9999))
    while room_id in rooms:
        room_id = str(random.randint(1000, 9999))
    rooms[room_id] = GameRoom(room_id, payload.name, payload.time_sec, payload.host_name, payload.host_avatar)
    return JSONResponse({"room_id": room_id})

@app.get("/api/rooms")
async def list_rooms():
    active = []
    for r_id, r in rooms.items():
        if len(r.players) > 0 and r.phase == "lobby":
            active.append({
                "id": r_id,
                "name": r.name,
                "count": len([p for p in r.players.values() if p.ws is not None]),
                "time_min": max(1, r.discussion_time // 60),
                "host_name": r.host_name,
                "host_avatar": r.host_avatar
            })
    return JSONResponse({"rooms": active})

@app.get("/api/quick_join")
async def quick_join_api():
    candidates = [r for r in rooms.values() if r.phase == "lobby" and len(r.players) > 0]
    if candidates:
        chosen = random.choice(candidates)
        return JSONResponse({"room_id": chosen.id})
    return JSONResponse({"room_id": None})

async def broadcast(room: GameRoom, data: dict):
    if data.get("type") == "chat":
        room.chat_history.append(data)
    disconnected = []
    for pid, p in list(room.players.items()):
        if p.ws:
            try:
                send_data = dict(data)
                if send_data.get("type") == "chat":
                    send_data["is_self"] = (send_data.get("sender_id") == pid)
                await p.ws.send_json(send_data)
            except Exception:
                disconnected.append(pid)
    for pid in disconnected:
        if pid in room.players:
            room.players[pid].ws = None

def get_public_players(room: GameRoom):
    return [{
        "id": p.id,
        "name": p.name,
        "avatar": p.avatar,
        "is_alive": p.is_alive
    } for p in room.players.values()]

async def trigger_last_word(room: GameRoom, victim: Player):
    room.phase = "last_word"
    room.last_word_speaker_id = victim.id
    room.remaining_time = 15
    await broadcast(room, {
        "type": "phase_change",
        "phase": "last_word",
        "time": 15,
        "speaker_id": victim.id
    })
    await broadcast(room, {
        "type": "chat",
        "text": f"🎤 {victim.name} uchun oxirgi so'z! (15 soniya)",
        "is_system": True
    })

    while room.remaining_time > 0 and room.phase == "last_word":
        await broadcast(room, {"type": "timer", "time": room.remaining_time})
        await asyncio.sleep(1)
        room.remaining_time -= 1

    victim.is_alive = False
    room.last_word_speaker_id = None
    await broadcast(room, {"type": "players_update", "players": get_public_players(room)})

def evaluate_game_status(room: GameRoom) -> bool:
    mafias = [p for p in room.players.values() if p.role == "mafia" and p.is_alive]
    citizens = [p for p in room.players.values() if p.role != "mafia" and p.is_alive]

    winner = None
    if len(mafias) == 0:
        winner = "citizens"
        win_txt = "🏆 G'ALABA! Shahar mafialardan tozalandi, Tinch fuqarolar g'alaba qozondi!"
    elif len(mafias) >= len(citizens):
        winner = "mafia"
        win_txt = "🏆 G'ALABA! Mafia shaharni butunlay egalladi!"

    if winner:
        room.phase = "game_over"
        room.winner = winner
        for p in room.players.values():
            if (winner == "mafia" and p.role == "mafia") or (winner == "citizens" and p.role != "mafia"):
                if p.id in stats_db:
                    stats_db[p.id]["wins"] += 1
        asyncio.create_task(broadcast(room, {"type": "phase_change", "phase": "game_over", "winner": winner}))
        asyncio.create_task(broadcast(room, {"type": "chat", "text": win_txt, "is_system": True}))
        return True
    return False

async def game_loop(room: GameRoom):
    # Statistika yozish
    for pid, p in room.players.items():
        if pid not in stats_db:
            stats_db[pid] = {"games": 0, "wins": 0, "mafia_games": 0}
        stats_db[pid]["games"] += 1
        if p.role == "mafia":
            stats_db[pid]["mafia_games"] = stats_db[pid].get("mafia_games", 0) + 1

    while room.phase not in ["lobby", "game_over"]:
        # 1. KUNDUZGI MUHOKAMA
        room.phase = "discussion"
        room.remaining_time = room.discussion_time
        await broadcast(room, {"type": "phase_change", "phase": "discussion", "time": room.remaining_time})
        await broadcast(room, {"type": "chat", "text": "☀️ Kunduzgi muhokama boshlandi! Shahardagi gumonlanuvchilarni aniqlang.", "is_system": True})

        while room.remaining_time > 0 and room.phase == "discussion":
            await broadcast(room, {"type": "timer", "time": room.remaining_time})
            await asyncio.sleep(1)
            room.remaining_time -= 1

        if evaluate_game_status(room):
            break

        # 2. OVOZ BERISH
        room.phase = "voting"
        room.votes.clear()
        room.remaining_time = 30
        cands = [{"id": p.id, "name": p.name} for p in room.players.values() if p.is_alive]
        await broadcast(room, {"type": "phase_change", "phase": "voting", "time": 30, "candidates": cands})
        await broadcast(room, {"type": "chat", "text": "🗳 Ovoz berish boshlandi! O'yindan chiqarmoqchi bo'lgan odamingizni tanlang.", "is_system": True})

        while room.remaining_time > 0 and room.phase == "voting":
            await broadcast(room, {"type": "timer", "time": room.remaining_time})
            await asyncio.sleep(1)
            room.remaining_time -= 1

        tally: Dict[str, int] = {}
        for target in room.votes.values():
            if target in room.players and room.players[target].is_alive:
                tally[target] = tally.get(target, 0) + 1

        eliminated_id = None
        if tally:
            max_v = max(tally.values())
            top = [tid for tid, c in tally.items() if c == max_v]
            if len(top) == 1:
                eliminated_id = top[0]

        if eliminated_id:
            victim = room.players.get(eliminated_id)
            if victim and victim.is_alive:
                await broadcast(room, {"type": "chat", "text": f"⚖️ Ovoz berish natijasida ko'pchilik ovoz bilan {victim.name} osilishga hukm qilindi!", "is_system": True})
                await trigger_last_word(room, victim)
        else:
            await broadcast(room, {"type": "chat", "text": "⚖️ Ovozlar teng bo'ldi yoki yetarli ovoz to'planmadi. Bugun hech kim osilmadi!", "is_system": True})

        if evaluate_game_status(room):
            break

        # 3. TUN
        room.phase = "night"
        room.night_actions.clear()
        room.remaining_time = 35
        targets = [{"id": p.id, "name": p.name} for p in room.players.values() if p.is_alive]
        await broadcast(room, {"type": "phase_change", "phase": "night", "time": 35, "targets": targets})
        await broadcast(room, {"type": "chat", "text": "🌙 Tun kirdi. Shahar ko'z yumdi... Maxfiy rollar o'z harakatini amalga oshirmoqda.", "is_system": True})

        while room.remaining_time > 0 and room.phase == "night":
            await broadcast(room, {"type": "timer", "time": room.remaining_time})
            await asyncio.sleep(1)
            room.remaining_time -= 1

        # Mafiya harakatini hisoblash
        alive_mafias = [p for p in room.players.values() if p.role == "mafia" and p.is_alive]
        mafia_shots = [
            room.night_actions[p.id] for p in alive_mafias 
            if p.id in room.night_actions and room.night_actions[p.id] in room.players and room.players[room.night_actions[p.id]].is_alive
        ]

        killed_id = None
        if mafia_shots:
            counts = Counter(mafia_shots)
            killed_id = counts.most_common(1)[0][0]

        # Doktor harakatini hisoblash
        doc = next((p for p in room.players.values() if p.role == "doctor" and p.is_alive), None)
        saved_id = None
        if doc and doc.id in room.night_actions:
            target_saved = room.night_actions[doc.id]
            if target_saved in room.players and room.players[target_saved].is_alive:
                if target_saved != room.last_healed_id:
                    saved_id = target_saved
                    room.last_healed_id = target_saved
                else:
                    room.last_healed_id = None
        else:
            room.last_healed_id = None

        # Komissar harakatini hisoblash va shaxsiy javob berish
        comm = next((p for p in room.players.values() if p.role == "commissar" and p.is_alive), None)
        if comm and comm.id in room.night_actions:
            checked_id = room.night_actions[comm.id]
            checked_player = room.players.get(checked_id)
            if checked_player and comm.ws:
                is_mafia = (checked_player.role == "mafia")
                res_txt = f"🚨 {checked_player.name} — MAFIA!" if is_mafia else f"👤 {checked_player.name} — TINCH FUQARO."
                try:
                    await comm.ws.send_json({
                        "type": "commissar_result",
                        "name": checked_player.name,
                        "is_mafia": is_mafia,
                        "text": res_txt
                    })
                    await comm.ws.send_json({
                        "type": "chat",
                        "text": f"🔍 Tergov xulosasi: {res_txt}",
                        "is_system": True
                    })
                except Exception:
                    pass

        # Tong natijalari
        if killed_id:
            if killed_id == saved_id:
                await broadcast(room, {"type": "chat", "text": "🌅 Tong otdi! Shifokor tunda yaradorni muvaffaqiyatli davoladi, hech kim o'lmadi!", "is_system": True})
            else:
                victim = room.players.get(killed_id)
                if victim and victim.is_alive:
                    await broadcast(room, {"type": "chat", "text": f"🌅 Tong otdi! Mafia tomonidan shafqatsizlarcha {victim.name} o'ldirildi!", "is_system": True})
                    await trigger_last_word(room, victim)
                else:
                    await broadcast(room, {"type": "chat", "text": "🌅 Tong otdi. Tunda hech kim o'lmadi.", "is_system": True})
        else:
            await broadcast(room, {"type": "chat", "text": "🌅 Tong otdi. Tunda hech kim o'lmadi.", "is_system": True})

        if evaluate_game_status(room):
            break

@app.websocket("/ws/{room_id}/{user_id}")
async def ws_handler(websocket: WebSocket, room_id: str, user_id: str, name: str = Query("O'yinchi"), avatar: str = Query("")):
    await websocket.accept()

    clean_name = name[:6] if name else "Player"

    if room_id not in rooms:
        rooms[room_id] = GameRoom(room_id, f"Xona #{room_id}", 60, clean_name, avatar)
    room = rooms[room_id]

    if not room.host_id or room.host_id not in room.players or room.players[room.host_id].ws is None:
        room.host_id = user_id

    if user_id not in room.players:
        room.players[user_id] = Player(user_id, clean_name, avatar, websocket)
    else:
        room.players[user_id].ws = websocket
        room.players[user_id].name = clean_name
        if avatar:
            room.players[user_id].avatar = avatar

    await websocket.send_json({"type": "room_info", "name": room.name})
    if room.host_id == user_id:
        await websocket.send_json({"type": "is_admin"})

    for old_msg in room.chat_history:
        await websocket.send_json(old_msg)

    await broadcast(room, {"type": "players_update", "players": get_public_players(room)})

    try:
        while True:
            data = await websocket.receive_json()
            act = data.get("action")
            player = room.players.get(user_id)

            if act == "leave":
                if room.host_id == user_id and room.phase == "lobby":
                    await broadcast(room, {"type": "room_closed"})
                    if room.id in rooms:
                        del rooms[room.id]
                    break
                else:
                    if room.phase == "lobby":
                        if user_id in room.players:
                            del room.players[user_id]
                    else:
                        if player:
                            player.ws = None
                            player.is_alive = False
                    await broadcast(room, {"type": "players_update", "players": get_public_players(room)})
                    break

            elif act == "update_profile" and player:
                new_n = data.get("name")
                new_a = data.get("avatar")
                if new_n:
                    player.name = new_n[:6]
                if new_a:
                    player.avatar = new_a
                await broadcast(room, {"type": "players_update", "players": get_public_players(room)})

            elif act == "start_game" and room.phase == "lobby" and room.host_id == user_id:
                active_players = [pid for pid, p in room.players.items() if p.ws is not None]
                if len(active_players) < 4:
                    continue

                p_ids = list(active_players)
                random.shuffle(p_ids)

                total_count = len(p_ids)
                if total_count >= 12:
                    roles = ["mafia", "mafia", "mafia", "commissar", "doctor"]
                elif total_count >= 8:
                    roles = ["mafia", "mafia", "commissar", "doctor"]
                else:
                    roles = ["mafia", "commissar", "doctor"]

                while len(roles) < total_count:
                    roles.append("citizen")

                random.shuffle(roles)

                for idx, pid in enumerate(p_ids):
                    p = room.players[pid]
                    p.role = roles[idx]
                    p.is_alive = True

                mafia_names = [room.players[pid].name for pid in p_ids if room.players[pid].role == "mafia"]

                for pid in p_ids:
                    p = room.players[pid]
                    if p.ws:
                        payload = {"type": "your_role", "role": p.role}
                        if p.role == "mafia":
                            payload["partners"] = [n for n in mafia_names if n != p.name]
                        await p.ws.send_json(payload)

                room.task = asyncio.create_task(game_loop(room))

            elif act == "restart_game" and room.host_id == user_id and room.phase == "game_over":
                room.phase = "lobby"
                room.winner = None
                room.votes.clear()
                room.night_actions.clear()
                room.last_healed_id = None
                for p in room.players.values():
                    p.role = "citizen"
                    p.is_alive = True
                await broadcast(room, {"type": "phase_change", "phase": "lobby"})
                await broadcast(room, {"type": "players_update", "players": get_public_players(room)})
                await broadcast(room, {"type": "chat", "text": "🔄 O'yin qayta yuklandi! Barcha o'yinchilar kutish zalida.", "is_system": True})
                if room.players.get(room.host_id) and room.players[room.host_id].ws:
                    await room.players[room.host_id].ws.send_json({"type": "is_admin"})

            elif act == "chat" and player:
                if room.phase == "last_word":
                    if room.last_word_speaker_id == user_id:
                        msg = data.get("text", "").strip()
                        if msg:
                            await broadcast(room, {
                                "type": "chat",
                                "sender": player.name,
                                "sender_id": player.id,
                                "avatar": player.avatar,
                                "text": msg,
                                "is_last_word": True
                            })
                elif player.is_alive and room.phase in ["lobby", "discussion"]:
                    msg = data.get("text", "").strip()
                    if msg:
                        await broadcast(room, {
                            "type": "chat",
                            "sender": player.name,
                            "sender_id": player.id,
                            "avatar": player.avatar,
                            "text": msg
                        })

            elif act == "vote" and player and player.is_alive:
                if room.phase in ["voting", "revoting"]:
                    target_id = data.get("target_id")
                    if target_id in room.players and room.players[target_id].is_alive:
                        room.votes[player.id] = target_id
                        await broadcast(room, {"type": "vote_update", "votes": room.votes})

            elif act == "night_action" and player and player.is_alive and room.phase == "night":
                target_id = data.get("target_id")
                if target_id in room.players and room.players[target_id].is_alive:
                    room.night_actions[user_id] = target_id

    except WebSocketDisconnect:
        if room.host_id == user_id:
            if room.phase == "lobby":
                await broadcast(room, {"type": "room_closed"})
                if room.id in rooms:
                    del rooms[room.id]
            else:
                if player:
                    player.ws = None
                remaining = [p.id for p in room.players.values() if p.ws is not None]
                if remaining:
                    room.host_id = remaining[0]
                    if room.players[room.host_id].ws:
                        await room.players[room.host_id].ws.send_json({"type": "is_admin"})
                else:
                    if room.id in rooms:
                        del rooms[room.id]
        else:
            if room.phase == "lobby":
                if user_id in room.players:
                    del room.players[user_id]
            else:
                if player:
                    player.ws = None
            await broadcast(room, {"type": "players_update", "players": get_public_players(room)})


# ==========================================================
# TELEGRAM BOT VA MAJBURIY OBUNA (Python 3.10+ / 3.14 ga mos)
# ==========================================================

def generate_welcome_text(user_name: str) -> str:
    safe_name = html.escape(user_name or "O'yinchi")
    return (
        f"🎭 <b>Mafia Cyber</b> olamiga xush kelibsiz, <b>{safe_name}</b>!\n\n"
        "🌙 Kechasi mafialar nishonni kelishadi, ☀️ kunduzi shahar ahli jinoyatchini qidiradi.\n"
        "👥 4–16 o'yinchi · 🕵️ Maxfiy rollar · 🗳 Ovoz berish · 🎤 Oxirgi so'z\n\n"
        "⚡️ Xona yarating yoki «Tezkor qo'shilish» orqali jangga kiring!\n"
        "🏆 O'ynang, g'alaba qozoning va tajribangizni oshiring.\n\n"
        "▶️ O'yinga kirish uchun quyidagi tugmani bosing!"
    )

def get_start_markup(is_subscribed: bool) -> dict:
    if REQUIRE_SUB and not is_subscribed and CHANNEL_ID:
        return {
            "inline_keyboard": [
                [{"text": "➕ Kanalga obuna bo'lish", "url": CHANNEL_URL}],
                [{"text": "✅ Obunani tekshirish", "callback_data": "check_sub"}]
            ]
        }

    buttons = []
    is_valid_https = WEB_APP_URL.startswith("https://") and "SIZNING_RENDER_URL" not in WEB_APP_URL
    if is_valid_https:
        buttons.append([{"text": "🎮 O'yinni boshlash (Mini App)", "web_app": {"url": WEB_APP_URL}}])
    elif WEB_APP_URL.startswith("http"):
        buttons.append([{"text": "🎮 O'yinga kirish (Havola)", "url": WEB_APP_URL}])
    else:
        buttons.append([{"text": "ℹ️ O'yinga kirish (Web App sozlanmagan)", "callback_data": "no_url"}])

    if CHANNEL_URL:
        buttons.append([{"text": "📢 Rasmiy kanal", "url": CHANNEL_URL}])

    return {"inline_keyboard": buttons}

async def check_telegram_subscription(client: httpx.AsyncClient, user_id: int) -> bool:
    if not REQUIRE_SUB or not CHANNEL_ID:
        return True
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getChatMember"
        resp = await client.get(url, params={"chat_id": CHANNEL_ID, "user_id": user_id})
        data = resp.json()
        if data.get("ok"):
            status = data.get("result", {}).get("status")
            return status in ["member", "administrator", "creator"]
        else:
            print(f"⚠️ Obuna tekshirishda xato (Bot kanalda admin bo'lmasligi mumkin): {data.get('description')}")
    except Exception as e:
        print(f"⚠️ Obuna tekshirish tarmog'ida xatolik: {e}")
    return False

async def run_telegram_bot_loop():
    if not TG_BOT_TOKEN:
        print("\n" + "="*55)
        print("⚠️ DIQQAT: TG_BOT_TOKEN kiritilmagan!")
        print("Telegram bot ishlashi uchun .env fayliga tokenni yozing:")
        print("TG_BOT_TOKEN=123456789:ABCDefgh...")
        print("="*55 + "\n")
        return

    offset = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Bot tokenini tekshirish
        try:
            me_resp = await client.get(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getMe")
            me_data = me_resp.json()
            if me_data.get("ok"):
                bot_user = me_data["result"].get("username")
                print(f"✅ Telegram bot muvaffaqiyatli ishga tushdi: @{bot_user}")
            else:
                print(f"❌ Telegram bot tokeni xato: {me_data.get('description')}")
                return
        except Exception as e:
            print(f"❌ Telegram API bilan bog'lanishda xato: {e}")
            return

        print("🚀 Telegram yangilanishlari (Updates) kutilmoqda...")

        while True:
            try:
                url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates"
                resp = await client.get(url, params={"offset": offset, "timeout": 20})
                data = resp.json()

                if not data.get("ok"):
                    await asyncio.sleep(3)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1

                    # 1. /start xabari
                    if "message" in update and "text" in update["message"]:
                        msg = update["message"]
                        text = msg.get("text", "")
                        if text.startswith("/start"):
                            user_id = msg["from"]["id"]
                            user_name = msg["from"].get("first_name", "O'yinchi")

                            is_sub = await check_telegram_subscription(client, user_id)
                            welcome_txt = generate_welcome_text(user_name)
                            markup = get_start_markup(is_sub)

                            send_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
                            send_res = await client.post(send_url, json={
                                "chat_id": user_id,
                                "text": welcome_txt,
                                "parse_mode": "HTML",
                                "reply_markup": markup
                            })
                            res_json = send_res.json()
                            if not res_json.get("ok"):
                                print(f"❌ /start yuborishda xatolik: {res_json.get('description')}")

                    # 2. Callback Query
                    elif "callback_query" in update:
                        cb = update["callback_query"]
                        cb_id = cb.get("id")
                        user_id = cb["from"]["id"]
                        user_name = cb["from"].get("first_name", "O'yinchi")
                        data_action = cb.get("data")
                        msg_id = cb.get("message", {}).get("message_id")

                        if data_action == "check_sub":
                            is_sub = await check_telegram_subscription(client, user_id)
                            if is_sub:
                                welcome_txt = generate_welcome_text(user_name)
                                markup = get_start_markup(True)
                                edit_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageText"
                                await client.post(edit_url, json={
                                    "chat_id": user_id,
                                    "message_id": msg_id,
                                    "text": welcome_txt,
                                    "parse_mode": "HTML",
                                    "reply_markup": markup
                                })
                                await client.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery", json={
                                    "callback_query_id": cb_id,
                                    "text": "✅ Rahmat! Obuna tasdiqlandi."
                                })
                            else:
                                await client.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery", json={
                                    "callback_query_id": cb_id,
                                    "text": f"❌ Siz hali kanalga a'zo bo'lmadingiz. Oldin {CHANNEL_ID} kanaliga obuna bo'ling!",
                                    "show_alert": True
                                })
                        elif data_action == "no_url":
                            await client.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery", json={
                                "callback_query_id": cb_id,
                                "text": "Web App havolasi hali sozlanmagan (.env faylida WEB_APP_URL ni to'g'rilang).",
                                "show_alert": True
                            })
            except Exception as e:
                print(f"❌ Telegram bot tsiklida xatolik: {e}")
                await asyncio.sleep(2)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(run_telegram_bot_loop())