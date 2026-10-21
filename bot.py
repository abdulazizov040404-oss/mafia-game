import os
import html
import asyncio
import random
from typing import Dict, List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# Telegram bot kutubxonalari
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.exceptions import MessageNotModified, CantParseEntities

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
    def __init__(self, user_id: str, name: str, avatar: str, ws: WebSocket):
        self.id = user_id
        self.name = name
        self.avatar = avatar
        self.ws = ws
        self.role = "citizen"
        self.is_alive = True
        self.last_healed = False

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
                "count": len(r.players),
                "time_min": r.discussion_time // 60,
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
    for pid, p in room.players.items():
        if p.ws:
            try:
                send_data = dict(data)
                if send_data.get("type") == "chat":
                    send_data["is_self"] = (send_data.get("sender_id") == pid)
                await p.ws.send_json(send_data)
            except Exception:
                disconnected.append(pid)
    for pid in disconnected:
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

async def game_loop(room: GameRoom):
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
        await broadcast(room, {"type": "chat", "text": "☀️ Kunduzgi muhokama boshlandi!", "is_system": True})

        while room.remaining_time > 0 and room.phase == "discussion":
            await broadcast(room, {"type": "timer", "time": room.remaining_time})
            await asyncio.sleep(1)
            room.remaining_time -= 1

        # 2. OVOZ BERISH
        room.phase = "voting"
        room.votes.clear()
        room.remaining_time = 30
        cands = [{"id": p.id, "name": p.name} for p in room.players.values() if p.is_alive]
        await broadcast(room, {"type": "phase_change", "phase": "voting", "time": 30, "candidates": cands})

        while room.remaining_time > 0 and room.phase == "voting":
            await broadcast(room, {"type": "timer", "time": room.remaining_time})
            await asyncio.sleep(1)
            room.remaining_time -= 1

        tally: Dict[str, int] = {}
        for target in room.votes.values():
            tally[target] = tally.get(target, 0) + 1

        eliminated_id = None
        if tally:
            max_v = max(tally.values())
            top = [tid for tid, c in tally.items() if c == max_v]
            if len(top) == 1:
                eliminated_id = top[0]

        if eliminated_id:
            victim = room.players[eliminated_id]
            await broadcast(room, {"type": "chat", "text": f"Ovoz berish natijasida {victim.name} osilishga hukm qilindi!", "is_system": True})
            await trigger_last_word(room, victim)

        if evaluate_game_status(room):
            break

        # 3. TUN
        room.phase = "night"
        room.night_actions.clear()
        room.remaining_time = 35
        targets = [{"id": p.id, "name": p.name} for p in room.players.values() if p.is_alive]
        await broadcast(room, {"type": "phase_change", "phase": "night", "time": 35, "targets": targets})
        await broadcast(room, {"type": "chat", "text": "🌙 Tun kirdi. Shahar ko'z yumdi...", "is_system": True})

        while room.remaining_time > 0 and room.phase == "night":
            await broadcast(room, {"type": "timer", "time": room.remaining_time})
            await asyncio.sleep(1)
            room.remaining_time -= 1

        alive_mafias = [p.id for p in room.players.values() if p.role == "mafia" and p.is_alive]
        mafia_shots = [room.night_actions[mid] for mid in alive_mafias if mid in room.night_actions]

        killed_id = None
        if len(mafia_shots) == len(alive_mafias) and len(set(mafia_shots)) == 1:
            killed_id = mafia_shots[0]

        doc = next((p for p in room.players.values() if p.role == "doctor" and p.is_alive), None)
        saved_id = room.night_actions.get(doc.id) if doc else None

        if killed_id:
            if killed_id == saved_id:
                await broadcast(room, {"type": "chat", "text": "Tong otdi. Shifokor tunda yaradorni qutqarib qoldi!", "is_system": True})
            else:
                victim = room.players[killed_id]
                await broadcast(room, {"type": "chat", "text": f"Tong otdi. Mafia tomonidan {victim.name} o'ldirildi!", "is_system": True})
                await trigger_last_word(room, victim)
        else:
            await broadcast(room, {"type": "chat", "text": "Tong otdi. Tunda hech kim o'lmadi.", "is_system": True})

        if evaluate_game_status(room):
            break

def evaluate_game_status(room: GameRoom) -> bool:
    mafias = [p for p in room.players.values() if p.role == "mafia" and p.is_alive]
    citizens = [p for p in room.players.values() if p.role != "mafia" and p.is_alive]

    winner = None
    if len(mafias) == 0:
        winner = "citizens"
        asyncio.create_task(broadcast(room, {"type": "chat", "text": "🏆 G'ALABA! Shahar mafialardan tozalandi, Fuqarolar yutdi!", "is_system": True}))
    elif len(mafias) >= len(citizens):
        winner = "mafia"
        asyncio.create_task(broadcast(room, {"type": "chat", "text": "🏆 G'ALABA! Mafia shaharni to'liq egalladi!", "is_system": True}))

    if winner:
        room.phase = "game_over"
        for p in room.players.values():
            if (winner == "mafia" and p.role == "mafia") or (winner == "citizens" and p.role != "mafia"):
                if p.id in stats_db:
                    stats_db[p.id]["wins"] += 1
        return True
    return False

@app.websocket("/ws/{room_id}/{user_id}")
async def ws_handler(websocket: WebSocket, room_id: str, user_id: str, name: str = Query("O'yinchi"), avatar: str = Query("")):
    await websocket.accept()

    clean_name = name[:6] if name else "Player"

    if room_id not in rooms:
        rooms[room_id] = GameRoom(room_id, f"Xona #{room_id}", 60, clean_name, avatar)
    room = rooms[room_id]

    if not room.host_id or room.host_id not in room.players:
        room.host_id = user_id

    if user_id not in room.players:
        room.players[user_id] = Player(user_id, clean_name, avatar, websocket)
    else:
        room.players[user_id].ws = websocket
        room.players[user_id].name = clean_name
        room.players[user_id].avatar = avatar

    await websocket.send_json({"type": "room_info", "name": room.name})
    if room.host_id == user_id and room.phase == "lobby":
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
                if room.host_id == user_id:
                    await broadcast(room, {"type": "room_closed"})
                    if room.id in rooms:
                        del rooms[room.id]
                    break
                else:
                    if user_id in room.players:
                        del room.players[user_id]
                    await broadcast(room, {"type": "players_update", "players": get_public_players(room)})
                    break

            elif act == "start_game" and room.phase == "lobby" and room.host_id == user_id:
                if len(room.players) < 4:
                    continue

                p_ids = list(room.players.keys())
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
                    if p.ws:
                        await p.ws.send_json({"type": "your_role", "role": p.role})

                room.task = asyncio.create_task(game_loop(room))

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
                    room.votes[player.id] = data.get("target_id")
                    await broadcast(room, {"type": "vote_update", "votes": room.votes})

            elif act == "night_action" and player and player.is_alive and room.phase == "night":
                room.night_actions[user_id] = data.get("target_id")

    except WebSocketDisconnect:
        if room.host_id == user_id:
            await broadcast(room, {"type": "room_closed"})
            if room.id in rooms:
                del rooms[room.id]
        else:
            if user_id in room.players:
                del room.players[user_id]
            await broadcast(room, {"type": "players_update", "players": get_public_players(room)})


# ==========================================
# TELEGRAM BOT VA MAJBURIY OBUNA QISMI
# ==========================================

TG_BOT_TOKEN = "SIZNING_BOT_TOKENINGIZ"       # BotFather tokeni
CHANNEL_ID = "@durbeh"
CHANNEL_URL = "https://t.me/durbeh"
WEB_APP_URL = "https://SIZNING_RENDER_URL.onrender.com"  # Render havolangiz

tg_bot = Bot(token=TG_BOT_TOKEN)
tg_dp = Dispatcher(tg_bot)

async def is_subscribed(user_id: int) -> bool:
    try:
        member = await tg_bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

def generate_welcome_text(user_name: str) -> str:
    return (
        f"🎭 <b>Mafia Cyber</b> olamiga xush kelibsiz, <b>{user_name}</b>!\n\n"
        "🌙 Kechasi mafialar nishonni kelishadi, ☀️ kunduzi shahar ahli jinoyatchini qidiradi.\n"
        "👥 4–16 o'yinchi · 🕵️ Maxfiy rollar · 🗳 Ovoz berish · 🎤 Oxirgi so'z\n\n"
        "⚡️ Xona yarating yoki «Tezkor qo'shilish» orqali jangga kiring!\n"
        "🏆 O'ynang, g'alaba qozoning va profilingiz uchun yangi ramkalarni oching.\n\n"
        "▶️ O'yinga kirish uchun quyidagi tugmani bosing!\n\n"
        "👥 Do'stlaringizni taklif qiling va guruhimizda birgalikda o'ynang!\n\n"
        f"📢 Yangiliklar va rasmiy kanal: {CHANNEL_ID}\n\n"
        "👉 <i>Yagona kanalga qo'shiling va o'yinni boshlang!</i>"
    )

def get_main_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🎮 O'yinni boshlash (Mini App)", web_app=WebAppInfo(url=WEB_APP_URL)),
        InlineKeyboardButton("📢 Rasmiy kanal (@durbeh)", url=CHANNEL_URL)
    )
    return kb

def get_check_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("➕ Kanalga obuna bo'lish", url=CHANNEL_URL),
        InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")
    )
    return kb

@tg_dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    raw_name = message.from_user.first_name or "Foydalanuvchi"
    user_name = html.escape(raw_name[:6])
    text = generate_welcome_text(user_name)
    
    if await is_subscribed(message.from_user.id):
        await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=get_check_keyboard(), parse_mode="HTML")

@tg_dp.callback_query_handler(lambda c: c.data == "check_sub")
async def check_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    raw_name = callback_query.from_user.first_name or "Foydalanuvchi"
    user_name = html.escape(raw_name[:6])

    if await is_subscribed(user_id):
        text = generate_welcome_text(user_name)
        try:
            await callback_query.message.edit_text(text, reply_markup=get_main_keyboard(), parse_mode="HTML")
        except MessageNotModified:
            pass
        await callback_query.answer("Obuna tasdiqlandi! O'yinni boshlashingiz mumkin 🎉")
    else:
        await callback_query.answer("❌ Siz hali kanalga a'zo bo'lmadingiz. Oldin @durbeh kanaliga obuna bo'ling!", show_alert=True)

# FastAPI ishga tushganda botni polling rejimida ishga tushirish
@app.on_event("startup")
async def on_startup():
    asyncio.create_task(tg_dp.start_polling())