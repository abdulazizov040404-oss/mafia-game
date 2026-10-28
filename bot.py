import os
import sys
import asyncio
import random
import html
import json
import shutil
from typing import Dict, List, Optional
from collections import Counter

# ==========================================================
# ROLLAR RASMLARINI KO'CHIRISH VA TAYYORLASH
# ==========================================================
BRAIN_IMG_DIR = r"C:\Users\nout.plus\.gemini\antigravity-ide\brain\c2cbd35a-b059-42d5-a8a1-64c927d9cc0a"
ROLES_DIR = os.path.join("static", "roles")
os.makedirs(ROLES_DIR, exist_ok=True)

role_map = {
    "rais.jpg": "role_rais_1793030734449.jpg",
    "mafiaboshi.jpg": "role_mafiaboshi_1793030777678.jpg",
    "mirshab.jpg": "role_mirshab_1793030816175.jpg",
    "xufya.jpg": "role_xufya_1793030912799.jpg",
    "mafia.jpg": "role_mafia_1793030954223.jpg",
    "izquvar.jpg": "role_izquvar_1793030998288.jpg",
    "doktor.jpg": "role_doktor_1793031087456.jpg",
    "aholi.jpg": "role_aholi_1793031130529.jpg",
}

for dest, src in role_map.items():
    src_path = os.path.join(BRAIN_IMG_DIR, src)
    dest_path = os.path.join(ROLES_DIR, dest)
    if os.path.exists(src_path) and not os.path.exists(dest_path):
        try:
            shutil.copy2(src_path, dest_path)
        except Exception:
            pass

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

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
REQUIRE_SUB = os.getenv("REQUIRE_SUB", "true").lower() in ["true", "1", "yes"]

app = FastAPI()

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "index.html topilmadi."}

@app.get("/style.css")
async def get_style_css():
    return FileResponse("static/style.css")

@app.get("/bot.js")
async def get_bot_js():
    return FileResponse("static/bot.js")

@app.get("/bg.jpg")
async def get_bg_jpg():
    return FileResponse("static/bg.jpg")

@app.get("/api/channel_info")
async def get_channel_info():
    return JSONResponse({
        "channel_id": CHANNEL_ID,
        "channel_url": CHANNEL_URL,
        "require_sub": REQUIRE_SUB
    })

@app.get("/api/check_sub")
async def check_sub_endpoint(user_id: str = Query(...)):
    if not REQUIRE_SUB or not CHANNEL_ID or not TG_BOT_TOKEN:
        return JSONResponse({"subscribed": True, "required": False})

    clean_id = str(user_id).strip()
    if not clean_id.isdigit():
        return JSONResponse({
            "subscribed": False,
            "required": True,
            "channel_url": CHANNEL_URL,
            "channel_id": CHANNEL_ID,
            "is_test_id": True
        })

    async with httpx.AsyncClient(timeout=8.0) as client:
        is_sub = await check_telegram_subscription(client, int(clean_id))
        return JSONResponse({
            "subscribed": is_sub,
            "required": True,
            "channel_url": CHANNEL_URL,
            "channel_id": CHANNEL_ID
        })

# ==========================================================
# FOYDALANUVCHILAR VA STATISTIKA (HAQIQIY O'YINCHILAR)
# ==========================================================
USERS_DB_FILE = "users_db.json"

def load_users_db() -> Dict[str, dict]:
    if os.path.exists(USERS_DB_FILE):
        try:
            with open(USERS_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ users_db.json yuklashda xatolik: {e}")
    return {}

def save_users_db():
    try:
        with open(USERS_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(stats_db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ users_db.json saqlashda xatolik: {e}")

stats_db: Dict[str, dict] = load_users_db()

class SyncProfileRequest(BaseModel):
    user_id: str
    name: str = "O'yinchi"
    avatar: str = ""

@app.post("/api/sync_profile")
async def sync_profile_api(payload: SyncProfileRequest):
    uid = str(payload.user_id).strip()
    if not uid:
        return JSONResponse({"error": "user_id required"}, status_code=400)
    clean_name = payload.name.strip()[:6] if payload.name else "Player"
    avatar = payload.avatar.strip()
    
    if uid not in stats_db:
        stats_db[uid] = {
            "name": clean_name,
            "avatar": avatar,
            "games": 0,
            "wins": 0,
            "mafia_games": 0,
            "mafia_wins": 0
        }
    else:
        stats_db[uid]["name"] = clean_name
        if avatar:
            stats_db[uid]["avatar"] = avatar
            
    save_users_db()
    return JSONResponse(stats_db[uid])

@app.get("/api/profile/{user_id}")
async def get_profile(user_id: str):
    uid = str(user_id).strip()
    data = stats_db.get(uid, {
        "name": "O'yinchi",
        "avatar": "",
        "games": 0, 
        "wins": 0, 
        "mafia_games": 0,
        "mafia_wins": 0
    })
    return JSONResponse(data)

@app.get("/api/leaderboard")
async def get_leaderboard(type: str = Query("top"), user_id: str = Query("")):
    # Faqat haqiqiy o'yinchilar ro'yxati (kamida 1 ta o'yin o'ynaganlar)
    players_list = []
    for uid, data in stats_db.items():
        games = data.get("games", 0)
        # Faqat o'yinda qatnashgan haqiqiy odamlar
        if games <= 0:
            continue

        name = data.get("name") or "O'yinchi"
        avatar = data.get("avatar") or ""
        wins = data.get("wins", 0)
        mafia_wins = data.get("mafia_wins", 0)
        mafia_games = data.get("mafia_games", 0)
        win_rate = int((wins / games) * 100) if games > 0 else 0
        mafia_rate = int((mafia_wins / mafia_games) * 100) if mafia_games > 0 else 0

        if type == "mafia":
            if mafia_wins >= 20:
                role_title = "👑 Don (Boss)"
            elif mafia_wins >= 10:
                role_title = "🔫 Snayper"
            elif mafia_wins >= 5:
                role_title = "🗡️ Shafqatsiz"
            elif mafia_wins >= 1:
                role_title = "🕶️ Qora Niqob"
            else:
                role_title = "👤 Yangi Mafioz"
            score_num = mafia_wins
            score_text = f"{mafia_wins} win"
            sub_rate = f"{mafia_rate}%"
            sort_tuple = (mafia_wins, mafia_rate, games)
        else:
            if wins >= 30:
                role_title = "👑 Afsona"
            elif wins >= 20:
                role_title = "🎖️ Shahar Faxri"
            elif wins >= 10:
                role_title = "🔍 Bosh Tergovchi"
            elif wins >= 5:
                role_title = "⚖️ Tajribali"
            elif wins >= 1:
                role_title = "🛡️ Faol Fuqaro"
            else:
                role_title = "🌱 Yangi O'yinchi"
            score_num = wins
            score_text = f"{wins} win"
            sub_rate = f"{win_rate}%"
            sort_tuple = (wins, win_rate, games)

        players_list.append({
            "user_id": uid,
            "name": name,
            "avatar": avatar,
            "wins": score_num,
            "games": mafia_games if type == "mafia" else games,
            "rate": sub_rate,
            "score_text": score_text,
            "role": role_title,
            "_sort": sort_tuple
        })

    # Saralash: g'alabalar, yutuq foizi va o'yinlar bo'yicha
    players_list.sort(key=lambda x: x["_sort"], reverse=True)

    ranks = ["🥇", "🥈", "🥉"]
    my_rank_info = None

    for idx, p in enumerate(players_list):
        del p["_sort"]
        p["rank"] = ranks[idx] if idx < 3 else str(idx + 1)
        p["rank_num"] = idx + 1
        if user_id and str(p["user_id"]) == str(user_id):
            my_rank_info = {
                "rank": p["rank"],
                "rank_num": p["rank_num"],
                "wins": p["wins"],
                "name": p["name"]
            }

    if user_id and not my_rank_info:
        curr_user = stats_db.get(str(user_id), {})
        curr_wins = curr_user.get("mafia_wins" if type == "mafia" else "wins", 0)
        curr_name = curr_user.get("name", "O'yinchi")
        my_rank_info = {
            "rank": str(len(players_list) + 1),
            "rank_num": len(players_list) + 1,
            "wins": curr_wins,
            "name": curr_name
        }

    return JSONResponse({
        "players": players_list,
        "my_rank": my_rank_info
    })

class Player:
    def __init__(self, user_id: str, name: str, avatar: str, ws: Optional[WebSocket]):
        self.id = user_id
        self.name = name
        self.avatar = avatar
        self.ws = ws
        self.role = "citizen"
        self.is_alive = True
        self.rais_revealed: bool = False
        self.bullets: int = 2
        self.disarmed: bool = False
        self.is_muted: bool = False
        self.is_speaking: bool = False

class GameRoom:
    def __init__(self, room_id: str, name: str, time_sec: int, host_name: str, host_avatar: str, mode: str = "voice", voice_type: str = "turn"):
        self.id = room_id
        self.name = name
        self.host_id: Optional[str] = None
        self.host_name = host_name
        self.host_avatar = host_avatar
        self.players: Dict[str, Player] = {}
        self.phase: str = "lobby"
        self.mode: str = mode  # "voice" yoki "chat"
        self.voice_type: str = voice_type  # "turn" (navbatma-navbat) yoki "free" (erkin)
        self.discussion_time: int = time_sec
        self.remaining_time: int = time_sec
        self.votes: Dict[str, str] = {}
        self.night_actions: Dict[str, str] = {}
        self.chat_history: List[dict] = []
        self.last_word_speaker_id: Optional[str] = None
        self.current_speaker_id: Optional[str] = None
        self.can_speak_ids: List[str] = []
        self.skip_turn_event: asyncio.Event = asyncio.Event()
        self.last_healed_id: Optional[str] = None
        self.winner: Optional[str] = None
        self.task: Optional[asyncio.Task] = None
        self.day_number: int = 0
        self.izquvar_history: Dict[str, dict] = {}

rooms: Dict[str, GameRoom] = {}

class CreateRoomRequest(BaseModel):
    name: str
    time_sec: int = 60
    host_name: str = "Host"
    host_avatar: str = ""
    mode: str = "voice"       # "voice" yoki "chat"
    voice_type: str = "turn"  # "turn" yoki "free"

@app.post("/api/create_room")
async def create_room_api(payload: CreateRoomRequest):
    room_id = str(random.randint(1000, 9999))
    while room_id in rooms:
        room_id = str(random.randint(1000, 9999))
    m = payload.mode if payload.mode in ["voice", "chat"] else "voice"
    vt = payload.voice_type if payload.voice_type in ["turn", "free"] else "turn"
    rooms[room_id] = GameRoom(room_id, payload.name, payload.time_sec, payload.host_name, payload.host_avatar, mode=m, voice_type=vt)
    return JSONResponse({"room_id": room_id})

@app.get("/api/rooms")
async def list_rooms(mode: Optional[str] = None):
    active = []
    for r_id, r in rooms.items():
        if len(r.players) > 0 and r.phase == "lobby":
            rmode = getattr(r, "mode", "voice")
            if mode and rmode != mode:
                continue
            active.append({
                "id": r_id,
                "name": r.name,
                "count": len([p for p in r.players.values() if p.ws is not None]),
                "time_min": max(1, r.discussion_time // 60),
                "host_name": r.host_name,
                "host_avatar": r.host_avatar,
                "mode": rmode,
                "voice_type": getattr(r, "voice_type", "turn")
            })
    return JSONResponse({"rooms": active})

@app.get("/api/quick_join")
async def quick_join_api(mode: Optional[str] = None):
    candidates = [
        r for r in rooms.values() 
        if r.phase == "lobby" and len(r.players) > 0 and (not mode or getattr(r, "mode", "voice") == mode)
    ]
    if not candidates:
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
        "is_alive": p.is_alive,
        "rais_revealed": getattr(p, "rais_revealed", False),
        "is_muted": getattr(p, "is_muted", False),
        "is_speaking": getattr(p, "is_speaking", False)
    } for p in room.players.values()]

async def trigger_last_word(room: GameRoom, victim: Player):
    room.phase = "last_word"
    room.last_word_speaker_id = victim.id
    room.current_speaker_id = victim.id
    room.can_speak_ids = [victim.id]
    room.remaining_time = 20
    await broadcast(room, {
        "type": "phase_change",
        "phase": "last_word",
        "time": 20,
        "speaker_id": victim.id,
        "speaker_name": victim.name
    })
    await broadcast(room, {
        "type": "chat",
        "text": f"🎤 {victim.name} uchun ovozli oxirgi so'z! (20 soniya)",
        "is_system": True
    })

    while room.remaining_time > 0 and room.phase == "last_word":
        await broadcast(room, {"type": "timer", "time": room.remaining_time})
        await asyncio.sleep(1)
        room.remaining_time -= 1

    victim.is_alive = False
    room.last_word_speaker_id = None
    room.current_speaker_id = None
    room.can_speak_ids = []
    await broadcast(room, {"type": "players_update", "players": get_public_players(room)})

def evaluate_game_status(room: GameRoom) -> bool:
    mafia_team = [p for p in room.players.values() if p.role in ["mafia", "mafiaboshi", "xufya"] and p.is_alive]
    citizens_team = [p for p in room.players.values() if p.role not in ["mafia", "mafiaboshi", "xufya"] and p.is_alive]

    winner = None
    if len(mafia_team) == 0:
        winner = "citizens"
        win_txt = "🏆 G'ALABA! Shahar mafialardan tozalandi, Tinch fuqarolar g'alaba qozondi!"
    elif len(mafia_team) >= len(citizens_team):
        winner = "mafia"
        win_txt = "🏆 G'ALABA! Mafia shaharni butunlay egalladi!"

    if winner:
        room.phase = "game_over"
        room.winner = winner
        for p in room.players.values():
            pid = str(p.id)
            if pid not in stats_db:
                stats_db[pid] = {
                    "name": p.name,
                    "avatar": p.avatar,
                    "games": 0,
                    "wins": 0,
                    "mafia_games": 0,
                    "mafia_wins": 0
                }
            is_mafia_side = p.role in ["mafia", "mafiaboshi", "xufya"]
            if (winner == "mafia" and is_mafia_side) or (winner == "citizens" and not is_mafia_side):
                stats_db[pid]["wins"] = stats_db[pid].get("wins", 0) + 1
                if is_mafia_side:
                    stats_db[pid]["mafia_wins"] = stats_db[pid].get("mafia_wins", 0) + 1
        save_users_db()
        asyncio.create_task(broadcast(room, {"type": "phase_change", "phase": "game_over", "winner": winner}))
        asyncio.create_task(broadcast(room, {"type": "chat", "text": win_txt, "is_system": True}))
        return True
    return False

async def game_loop(room: GameRoom):
    # Statistika yozish
    for pid, p in room.players.items():
        sid = str(pid)
        if sid not in stats_db:
            stats_db[sid] = {
                "name": p.name,
                "avatar": p.avatar,
                "games": 0,
                "wins": 0,
                "mafia_games": 0,
                "mafia_wins": 0
            }
        else:
            stats_db[sid]["name"] = p.name
            if p.avatar:
                stats_db[sid]["avatar"] = p.avatar
        stats_db[sid]["games"] = stats_db[sid].get("games", 0) + 1
        if p.role in ["mafia", "mafiaboshi", "xufya"]:
            stats_db[sid]["mafia_games"] = stats_db[sid].get("mafia_games", 0) + 1
    save_users_db()

    while room.phase not in ["lobby", "game_over"]:
        # 1. KUNDUZGI MUHOKAMA
        room.phase = "discussion"
        if getattr(room, "mode", "voice") == "voice" and getattr(room, "voice_type", "turn") == "turn":
            # Navbatma-navbat (Turn-based speech)
            alive_players = [p for p in room.players.values() if p.is_alive]
            turn_duration = 30
            for spk in alive_players:
                if not spk.is_alive or room.phase != "discussion":
                    continue
                room.current_speaker_id = spk.id
                room.can_speak_ids = [spk.id]
                room.skip_turn_event.clear()
                await broadcast(room, {
                    "type": "phase_change",
                    "phase": "discussion",
                    "time": turn_duration,
                    "speaker_id": spk.id,
                    "speaker_name": spk.name,
                    "is_free_talk": False
                })
                await broadcast(room, {
                    "type": "chat",
                    "text": f"🎙️ Nutq navbati: {spk.name} (30 soniya)!",
                    "is_system": True
                })
                for sec in range(turn_duration, 0, -1):
                    if room.skip_turn_event.is_set() or room.phase != "discussion":
                        break
                    await broadcast(room, {"type": "timer", "time": sec})
                    await asyncio.sleep(1)

            # Navbatlar yakunlangach, 45s umumiy erkin bahs
            room.current_speaker_id = "all"
            room.can_speak_ids = [p.id for p in room.players.values() if p.is_alive]
            free_time = 45
            await broadcast(room, {
                "type": "phase_change",
                "phase": "discussion",
                "time": free_time,
                "speaker_id": "all",
                "speaker_name": "Umumiy erkin bahs",
                "is_free_talk": True
            })
            await broadcast(room, {
                "type": "chat",
                "text": "📢 Umumiy erkin munozara (45 soniya)! Barcha o'yinchilar erkin bahslashishi mumkin.",
                "is_system": True
            })
            for sec in range(free_time, 0, -1):
                if room.phase != "discussion":
                    break
                await broadcast(room, {"type": "timer", "time": sec})
                await asyncio.sleep(1)
        else:
            # Erkin bahs (Voice Free) yoki Chatli Mafia
            is_voice = (getattr(room, "mode", "voice") == "voice")
            room.current_speaker_id = "all" if is_voice else None
            room.can_speak_ids = [p.id for p in room.players.values() if p.is_alive]
            room.remaining_time = room.discussion_time
            await broadcast(room, {
                "type": "phase_change",
                "phase": "discussion",
                "time": room.remaining_time,
                "speaker_id": "all" if is_voice else None,
                "is_free_talk": True
            })
            msg_text = "🎙️ Ovozli erkin munozara boshlandi! Hamma jonli suhbatlashishi mumkin." if is_voice else "☀️ Kunduzgi muhokama boshlandi! Shahardagi gumonlanuvchilarni aniqlang."
            await broadcast(room, {"type": "chat", "text": msg_text, "is_system": True})

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
        is_voice = (getattr(room, "mode", "voice") == "voice")
        room.current_speaker_id = "all" if is_voice else None
        room.can_speak_ids = [p.id for p in room.players.values() if p.is_alive]
        cands = [{"id": p.id, "name": p.name} for p in room.players.values() if p.is_alive]
        await broadcast(room, {"type": "phase_change", "phase": "voting", "time": 30, "candidates": cands, "speaker_id": "all" if is_voice else None})
        await broadcast(room, {"type": "chat", "text": "🗳 Ovoz berish boshlandi! O'yindan chiqarmoqchi bo'lgan odamingizni tanlang.", "is_system": True})

        while room.remaining_time > 0 and room.phase == "voting":
            await broadcast(room, {"type": "timer", "time": room.remaining_time})
            await asyncio.sleep(1)
            room.remaining_time -= 1

        # Ovozlar sonini hisoblash (Rais ochiqlagan bo'lsa ovozi 2x)
        tally: Dict[str, int] = {}
        for voter_id, target_id in room.votes.items():
            if target_id in room.players and room.players[target_id].is_alive:
                voter = room.players.get(voter_id)
                weight = 2 if (voter and voter.role == "rais" and voter.rais_revealed) else 1
                tally[target_id] = tally.get(target_id, 0) + weight

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

        # 3. TUN BOSQICHI
        room.day_number += 1
        room.phase = "night"
        room.current_speaker_id = None
        room.can_speak_ids = []
        room.night_actions.clear()
        room.remaining_time = 35
        targets = [{"id": p.id, "name": p.name} for p in room.players.values() if p.is_alive]

        # Har bir o'yinchiga shaxsiy ma'lumot uzatish
        for p in room.players.values():
            if p.ws and p.is_alive:
                p_payload = {
                    "type": "phase_change",
                    "phase": "night",
                    "time": 35,
                    "targets": targets,
                    "day_number": room.day_number
                }
                if p.role == "mirshab":
                    p_payload["bullets"] = getattr(p, "bullets", 2)
                    p_payload["disarmed"] = getattr(p, "disarmed", False)
                    if room.day_number >= 2:
                        p_payload["izquvar_hints"] = room.izquvar_history
                elif p.role == "xufya":
                    p_payload["is_xufya"] = True

                try:
                    await p.ws.send_json(p_payload)
                except Exception:
                    pass

        await broadcast(room, {"type": "chat", "text": "🌙 Tun kirdi. Shahar ko'z yumdi... Maxfiy rollar o'z harakatini amalga oshirmoqda.", "is_system": True})

        while room.remaining_time > 0 and room.phase == "night":
            await broadcast(room, {"type": "timer", "time": room.remaining_time})
            await asyncio.sleep(1)
            room.remaining_time -= 1

        # 1. Mafiya harakati (Mafia va Mafiaboshi - Xufya otmaydi)
        alive_shooters = [p for p in room.players.values() if p.role in ["mafia", "mafiaboshi"] and p.is_alive]
        mafia_shots = [
            room.night_actions[p.id] for p in alive_shooters
            if p.id in room.night_actions and room.night_actions[p.id] in room.players and room.players[room.night_actions[p.id]].is_alive
        ]

        killed_id = None
        if mafia_shots:
            # Agar Mafiaboshi ovoz bergan bo'lsa, uning ovozi hal qiluvchi bo'lishi mumkin
            boss = next((p for p in alive_shooters if p.role == "mafiaboshi"), None)
            if boss and boss.id in room.night_actions and room.night_actions[boss.id] in room.players and room.players[room.night_actions[boss.id]].is_alive:
                killed_id = room.night_actions[boss.id]
            else:
                counts = Counter(mafia_shots)
                killed_id = counts.most_common(1)[0][0]

        # 2. Doktor harakati
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

        # 3. Izquvar harakati
        comm = next((p for p in room.players.values() if p.role == "commissar" and p.is_alive), None)
        if comm and comm.id in room.night_actions:
            checked_id = room.night_actions[comm.id]
            checked_player = room.players.get(checked_id)
            if checked_player and comm.ws:
                # Mafiaboshi Izquvarga Tinch Aholi bo'lib ko'rinadi!
                is_mafia_detected = (checked_player.role in ["mafia", "xufya"])
                room.izquvar_history[checked_id] = {
                    "name": checked_player.name,
                    "is_mafia": is_mafia_detected
                }
                res_txt = f"🚨 {checked_player.name} — MAFIA!" if is_mafia_detected else f"👤 {checked_player.name} — TINCH AHOLI (Mafia emas)."
                try:
                    await comm.ws.send_json({
                        "type": "commissar_result",
                        "name": checked_player.name,
                        "is_mafia": is_mafia_detected,
                        "text": res_txt
                    })
                    await comm.ws.send_json({
                        "type": "chat",
                        "text": f"🔍 Tergov xulosasi: {res_txt}",
                        "is_system": True
                    })
                except Exception:
                    pass

        # 4. Mirshab harakati
        mirshab = next((p for p in room.players.values() if p.role == "mirshab" and p.is_alive and not getattr(p, "disarmed", False) and getattr(p, "bullets", 0) > 0), None)
        mirshab_killed_id = None
        mirshab_disarmed_alert = False
        if mirshab and mirshab.id in room.night_actions:
            m_target_id = room.night_actions[mirshab.id]
            m_target = room.players.get(m_target_id)
            if m_target and m_target.is_alive:
                mirshab.bullets -= 1
                if m_target_id != saved_id:
                    mirshab_killed_id = m_target_id
                
                # Agar begunoh fuqaroni otsa, ishdan bo'shatiladi
                if m_target.role not in ["mafia", "mafiaboshi", "xufya"]:
                    mirshab.disarmed = True
                    mirshab.bullets = 0
                    mirshab_disarmed_alert = True

        # 5. Xufya harakati
        xufya = next((p for p in room.players.values() if p.role == "xufya" and p.is_alive), None)
        if xufya and xufya.id in room.night_actions:
            x_target_id = room.night_actions[xufya.id]
            x_target = room.players.get(x_target_id)
            if x_target and xufya.ws:
                role_titles = {
                    "mafia": "🔫 Mafia",
                    "mafiaboshi": "👑 Mafiaboshi",
                    "xufya": "🕵️ Xufya",
                    "doctor": "💉 Doktor",
                    "commissar": "🔍 Izquvar",
                    "rais": "👑 Rais",
                    "mirshab": "👮 Mirshab",
                    "citizen": "👤 Tinch aholi"
                }
                role_str = role_titles.get(x_target.role, "👤 Tinch aholi")
                try:
                    await xufya.ws.send_json({
                        "type": "chat",
                        "text": f"🕵️ JOSUSLIK NATIJASI: {x_target.name} o'yinchisining roli — {role_str}!",
                        "is_system": True
                    })
                except Exception:
                    pass

        # Tong natijalari
        deaths = []
        if killed_id:
            if killed_id == saved_id:
                await broadcast(room, {"type": "chat", "text": "🌅 Tong otdi! Shifokor tunda yaradorni muvaffaqiyatli davoladi, mafia hujumi qaytarildi!", "is_system": True})
            else:
                vic = room.players.get(killed_id)
                if vic and vic.is_alive:
                    deaths.append((vic, "Mafia tomonidan shafqatsizlarcha o'ldirildi!"))

        if mirshab_killed_id and mirshab_killed_id != saved_id and mirshab_killed_id != killed_id:
            vic_m = room.players.get(mirshab_killed_id)
            if vic_m and vic_m.is_alive:
                deaths.append((vic_m, "Mirshab tomonidan otib o'ldirildi!"))

        if mirshab_disarmed_alert and mirshab:
            await broadcast(room, {"type": "chat", "text": f"⚠️ Mirshab begunoh fuqaroni otib qo'ydi va qonun oldida javobgarlikka tortilib, ishdan bo'shatildi!", "is_system": True})

        if not deaths and (not killed_id or killed_id == saved_id) and not mirshab_killed_id:
            await broadcast(room, {"type": "chat", "text": "🌅 Tong otdi. Tunda hech kim o'lmadi.", "is_system": True})
        else:
            for victim, reason in deaths:
                await broadcast(room, {"type": "chat", "text": f"🌅 Tong otdi! {victim.name} — {reason}", "is_system": True})
                await trigger_last_word(room, victim)

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

    uid = str(user_id)
    if uid not in stats_db:
        stats_db[uid] = {
            "name": clean_name,
            "avatar": avatar,
            "games": 0,
            "wins": 0,
            "mafia_games": 0,
            "mafia_wins": 0
        }
    else:
        stats_db[uid]["name"] = clean_name
        if avatar:
            stats_db[uid]["avatar"] = avatar
    save_users_db()

    await websocket.send_json({
        "type": "room_info",
        "name": room.name,
        "mode": getattr(room, "mode", "voice"),
        "voice_type": getattr(room, "voice_type", "turn"),
        "current_speaker_id": getattr(room, "current_speaker_id", None)
    })
    if room.host_id == user_id:
        await websocket.send_json({"type": "is_admin"})

    for old_msg in room.chat_history:
        await websocket.send_json(old_msg)

    await broadcast(room, {"type": "players_update", "players": get_public_players(room)})
    await broadcast(room, {"type": "peer_joined", "user_id": user_id, "name": clean_name})

    try:
        while True:
            data = await websocket.receive_json()
            act = data.get("action")
            player = room.players.get(user_id)

            if act == "leave":
                await broadcast(room, {"type": "peer_left", "user_id": user_id})
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
                uid = str(user_id)
                if uid in stats_db:
                    stats_db[uid]["name"] = player.name
                    if player.avatar:
                        stats_db[uid]["avatar"] = player.avatar
                    save_users_db()
                await broadcast(room, {"type": "players_update", "players": get_public_players(room)})

            elif act == "start_game" and room.phase == "lobby" and room.host_id == user_id:
                active_players = [pid for pid, p in room.players.items() if p.ws is not None]
                if len(active_players) < 4:
                    continue

                p_ids = list(active_players)
                random.shuffle(p_ids)

                total_count = len(p_ids)
                # Rasmlar va qoidalarga mos rollar taqsimoti:
                # 16 o'yinchi: 1 Mafiaboshi, 2 Mafia, 1 Xufya (4 mafia), 1 Izquvar, 1 Doktor, 1 Rais, 1 Mirshab, 8 Tinch aholi
                # 15 o'yinchi: 1 Mafiaboshi, 2 Mafia, 1 Izquvar, 1 Doktor, 1 Rais, 1 Mirshab, 8 Tinch aholi
                # 12-14 o'yinchi: 1 Mafiaboshi, 2 Mafia, 1 Izquvar, 1 Doktor, 1 Rais, qolganlar Tinch aholi
                # 10-11 o'yinchi: 1 Mafiaboshi, 1 Mafia, 1 Izquvar, 1 Doktor, 1 Rais, qolganlar Tinch aholi
                # 9 o'yinchi: 1 Mafiaboshi, 1 Mafia, 1 Izquvar, 1 Doktor, 5 Tinch aholi
                # 6-8 o'yinchi: 2 Mafia, 1 Izquvar, 1 Doktor, qolganlar Tinch aholi
                # 4-5 o'yinchi: 1 Mafia, 1 Izquvar, 1 Doktor, qolganlar Tinch aholi
                if total_count >= 16:
                    roles = ["mafiaboshi", "mafia", "mafia", "xufya", "commissar", "doctor", "rais", "mirshab"]
                elif total_count >= 15:
                    roles = ["mafiaboshi", "mafia", "mafia", "commissar", "doctor", "rais", "mirshab"]
                elif total_count >= 12:
                    roles = ["mafiaboshi", "mafia", "mafia", "commissar", "doctor", "rais"]
                elif total_count >= 10:
                    roles = ["mafiaboshi", "mafia", "commissar", "doctor", "rais"]
                elif total_count >= 9:
                    roles = ["mafiaboshi", "mafia", "commissar", "doctor"]
                elif total_count >= 6:
                    roles = ["mafia", "mafia", "commissar", "doctor"]
                else:
                    roles = ["mafia", "commissar", "doctor"]

                while len(roles) < total_count:
                    roles.append("citizen")

                random.shuffle(roles)

                room.day_number = 0
                room.izquvar_history.clear()

                for idx, pid in enumerate(p_ids):
                    p = room.players[pid]
                    p.role = roles[idx]
                    p.is_alive = True
                    p.rais_revealed = False
                    p.bullets = 2
                    p.disarmed = False

                mafia_team_members = [
                    f"{room.players[pid].name} ({'👑 Mafiaboshi' if room.players[pid].role == 'mafiaboshi' else ('🕵️ Xufya' if room.players[pid].role == 'xufya' else '🔫 Mafia')})"
                    for pid in p_ids if room.players[pid].role in ["mafia", "mafiaboshi", "xufya"]
                ]

                for pid in p_ids:
                    p = room.players[pid]
                    if p.ws:
                        payload = {"type": "your_role", "role": p.role}
                        if p.role in ["mafia", "mafiaboshi", "xufya"]:
                            payload["partners"] = [n for n in mafia_team_members if not n.startswith(p.name)]
                        if p.role == "mirshab":
                            payload["bullets"] = 2
                        await p.ws.send_json(payload)

                room.task = asyncio.create_task(game_loop(room))

            elif act == "reveal_rais" and player and player.is_alive and player.role == "rais":
                if not getattr(player, "rais_revealed", False) and room.phase in ["discussion", "voting"]:
                    player.rais_revealed = True
                    await broadcast(room, {
                        "type": "chat",
                        "text": f"👑 {player.name} o'zining RAIS ekanligini e'lon qildi! Endi uning ovozi 2 ga teng!",
                        "is_system": True
                    })
                    await broadcast(room, {"type": "players_update", "players": get_public_players(room)})

            elif act == "restart_game" and room.host_id == user_id and room.phase == "game_over":
                room.phase = "lobby"
                room.winner = None
                room.votes.clear()
                room.night_actions.clear()
                room.last_healed_id = None
                room.day_number = 0
                room.izquvar_history.clear()
                for p in room.players.values():
                    p.role = "citizen"
                    p.is_alive = True
                    p.rais_revealed = False
                    p.bullets = 2
                    p.disarmed = False
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

            elif act == "webrtc_signal":
                target_id = str(data.get("target_id", ""))
                sig = data.get("signal")
                if target_id in room.players and room.players[target_id].ws:
                    try:
                        await room.players[target_id].ws.send_json({
                            "type": "webrtc_signal",
                            "sender_id": user_id,
                            "signal": sig
                        })
                    except Exception:
                        pass

            elif act == "mic_status" and player:
                is_muted = bool(data.get("is_muted", False))
                is_speaking = bool(data.get("is_speaking", False))
                player.is_muted = is_muted
                player.is_speaking = is_speaking
                await broadcast(room, {
                    "type": "player_mic_status",
                    "user_id": user_id,
                    "is_muted": is_muted,
                    "is_speaking": is_speaking
                })

            elif act == "skip_turn" and (user_id == getattr(room, "current_speaker_id", None) or user_id == room.host_id):
                if hasattr(room, "skip_turn_event"):
                    room.skip_turn_event.set()

    except WebSocketDisconnect:
        await broadcast(room, {"type": "peer_left", "user_id": user_id})
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
        f"🎭 <b>Mafia Club</b> olamiga xush kelibsiz, <b>{safe_name}</b>!\n\n"
        "🎙️ <b>YANGILIK: Ovozli Mafia (Voice Mafia) rejimi ishga tushdi!</b>\n"
        "Endi real vaqtda mikrofon orqali xuddi haqiqiy klublardek jonli ovoz bilan o'ynashingiz mumkin!\n\n"
        "🌙 Kechasi mafialar nishonni kelishadi, ☀️ kunduzi shahar ahli jinoyatchini qidiradi.\n"
        "👥 4–16 o'yinchi · 🎙 Ovozli va 💬 Chatli xonalar · ⏱ Navbatma-navbat nutq · 🎤 Oxirgi so'z\n\n"
        "⚡️ Xona yarating yoki «Tezkor qo'shilish» orqali jangga kiring!\n"
        "🏆 O'ynang, g'alaba qozoning va reytingda yetakchi bo'ling.\n\n"
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
                print(f"[OK] Telegram bot muvaffaqiyatli ishga tushdi: @{bot_user}")
            else:
                print(f"[XATO] Telegram bot tokeni noto'g'ri: {me_data.get('description')}")
                return
        except Exception as e:
            print(f"[XATO] Telegram API bilan bog'lanishda xato: {e}")
            return

        print("[START] Telegram xabarlari (Updates) qabul qilinmoqda...")

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

                            uid_str = str(user_id)
                            if uid_str not in stats_db:
                                stats_db[uid_str] = {
                                    "name": (user_name or "Player")[:6],
                                    "avatar": "",
                                    "games": 0,
                                    "wins": 0,
                                    "mafia_games": 0,
                                    "mafia_wins": 0
                                }
                                save_users_db()
                            elif not stats_db[uid_str].get("name") and user_name:
                                stats_db[uid_str]["name"] = user_name[:6]
                                save_users_db()

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
                                print(f"[XATO] /start yuborishda xatolik: {res_json.get('description')}")

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
                print(f"[XATO] Telegram bot tsiklida xatolik: {e}")
                await asyncio.sleep(2)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(run_telegram_bot_loop())

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Server ishga tushmoqda: http://localhost:{port}")
    uvicorn.run("bot:app", host="0.0.0.0", port=port, reload=True)