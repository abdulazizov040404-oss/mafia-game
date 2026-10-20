import os
import asyncio
import random
from typing import Dict, List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

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
    data = stats_db.get(user_id, {"games": 0, "wins": 0})
    return JSONResponse(data)

class Player:
    def __init__(self, user_id: str, name: str, ws: WebSocket):
        self.id = user_id
        self.name = name
        self.ws = ws
        self.role = "citizen"
        self.is_alive = True
        self.last_healed = False

class GameRoom:
    def __init__(self, room_id: str, name: str):
        self.id = room_id
        self.name = name
        self.host_id: Optional[str] = None
        self.players: Dict[str, Player] = {}
        self.phase: str = "lobby"
        self.discussion_time: int = 60  # Kunduzgi muhokama vaqti (1, 2, 3 min)
        self.voting_time: int = 30      # Ovoz berish qat'iy 30 soniya
        self.remaining_time: int = 60
        self.votes: Dict[str, str] = {} # {voter_name: target_id}
        self.night_actions: Dict[str, str] = {}
        self.chat_history: List[dict] = [] # Muhokama tarixi saqlanadi
        self.task: Optional[asyncio.Task] = None

rooms: Dict[str, GameRoom] = {}

class CreateRoomRequest(BaseModel):
    name: str

@app.post("/api/create_room")
async def create_room_api(payload: CreateRoomRequest):
    room_id = str(random.randint(1000, 9999))
    while room_id in rooms:
        room_id = str(random.randint(1000, 9999))
    rooms[room_id] = GameRoom(room_id, payload.name)
    return JSONResponse({"room_id": room_id, "name": payload.name})

@app.get("/api/rooms")
async def list_rooms():
    active = []
    for r_id, r in rooms.items():
        if len(r.players) > 0 and r.phase == "lobby":
            active.append({
                "id": r_id,
                "name": r.name,
                "count": len(r.players),
                "status": "Kutilmoqda"
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
    # Chat xabari bo'lsa tarixga qo'shamiz
    if data.get("type") == "chat":
        room.chat_history.append(data)

    disconnected = []
    for pid, p in room.players.items():
        if p.ws:
            try:
                await p.ws.send_json(data)
            except Exception:
                disconnected.append(pid)
    for pid in disconnected:
        room.players[pid].ws = None

def get_public_players(room: GameRoom):
    return [{"id": p.id, "name": p.name, "is_alive": p.is_alive} for p in room.players.values()]

async def game_loop(room: GameRoom):
    for pid in room.players.keys():
        if pid not in stats_db:
            stats_db[pid] = {"games": 0, "wins": 0}
        stats_db[pid]["games"] += 1

    while room.phase not in ["lobby", "game_over"]:
        # 1. KUNDUZGI MUHOKAMA
        room.phase = "discussion"
        room.remaining_time = room.discussion_time
        await broadcast(room, {
            "type": "phase_change",
            "phase": "discussion",
            "time": room.remaining_time
        })
        await broadcast(room, {"type": "chat", "text": "☀️ Kunduzgi muhokama boshlandi! Chatda fikr almashing.", "is_system": True})

        while room.remaining_time > 0 and room.phase == "discussion":
            await broadcast(room, {"type": "timer", "time": room.remaining_time})
            await asyncio.sleep(1)
            room.remaining_time -= 1

        # 2. OVOZ BERISH BOSQICHI (ANIQ 30 SONIYA)
        room.phase = "voting"
        room.votes.clear()
        room.remaining_time = room.voting_time
        cands = [{"id": p.id, "name": p.name} for p in room.players.values() if p.is_alive]
        await broadcast(room, {
            "type": "phase_change",
            "phase": "voting",
            "time": room.remaining_time,
            "candidates": cands
        })
        await broadcast(room, {"type": "chat", "text": "🗳 Ovoz berish boshlandi! Sizda 30 soniya bor.", "is_system": True})

        while room.remaining_time > 0 and room.phase == "voting":
            await broadcast(room, {"type": "timer", "time": room.remaining_time})
            await asyncio.sleep(1)
            room.remaining_time -= 1

        # OVOZLARNI HISOBLASH
        tally: Dict[str, int] = {}
        for target in room.votes.values():
            tally[target] = tally.get(target, 0) + 1

        eliminated_id = None
        if tally:
            max_v = max(tally.values())
            top = [tid for tid, count in tally.items() if count == max_v]
            if len(top) > 1:
                # Qayta ovoz berish (yana 30 soniya)
                room.phase = "revoting"
                room.votes.clear()
                room.remaining_time = room.voting_time
                revote_cands = [{"id": tid, "name": room.players[tid].name} for tid in top]
                await broadcast(room, {
                    "type": "phase_change",
                    "phase": "revoting",
                    "time": room.remaining_time,
                    "candidates": revote_cands
                })
                await broadcast(room, {"type": "chat", "text": "⚖️ Ovozlar teng! Faqat teng chiqqan nomzodlar uchun 30 soniyalik qayta ovoz berish!", "is_system": True})

                while room.remaining_time > 0 and room.phase == "revoting":
                    await broadcast(room, {"type": "timer", "time": room.remaining_time})
                    await asyncio.sleep(1)
                    room.remaining_time -= 1

                retally: Dict[str, int] = {}
                for target in room.votes.values():
                    if target in top:
                        retally[target] = retally.get(target, 0) + 1
                if retally:
                    rmax = max(retally.values())
                    rtop = [tid for tid, count in retally.items() if count == rmax]
                    if len(rtop) == 1:
                        eliminated_id = rtop[0]
                    else:
                        await broadcast(room, {"type": "chat", "text": "Qayta ovoz berishda ham tenglik! Bugun hech kim osilmadi.", "is_system": True})
            else:
                eliminated_id = top[0]

        if eliminated_id:
            victim = room.players[eliminated_id]
            victim.is_alive = False
            await broadcast(room, {"type": "eliminated", "target_id": eliminated_id})
            await broadcast(room, {"type": "chat", "text": f"Ovoz berish natijasida {victim.name} o'yindan chetlatildi!", "is_system": True})
            await broadcast(room, {"type": "players_update", "players": get_public_players(room)})

        if evaluate_game_status(room):
            break

        # 3. TUN BOSQICHI
        room.phase = "night"
        room.night_actions.clear()
        room.remaining_time = 40 # Tun bosqichi 40 soniya
        targets = [{"id": p.id, "name": p.name} for p in room.players.values() if p.is_alive]
        await broadcast(room, {
            "type": "phase_change",
            "phase": "night",
            "time": room.remaining_time,
            "targets": targets
        })
        await broadcast(room, {"type": "chat", "text": "🌙 Tun kirdi, shahar ahli ko'z yumdi...", "is_system": True})

        while room.remaining_time > 0 and room.phase == "night":
            await broadcast(room, {"type": "timer", "time": room.remaining_time})
            await asyncio.sleep(1)
            room.remaining_time -= 1

        # Tungi natijalar
        alive_mafias = [p.id for p in room.players.values() if p.role == "mafia" and p.is_alive]
        mafia_choices = [room.night_actions[mid] for mid in alive_mafias if mid in room.night_actions]

        killed_id = None
        if len(mafia_choices) == len(alive_mafias) and len(set(mafia_choices)) == 1:
            killed_id = mafia_choices[0]

        doc = next((p for p in room.players.values() if p.role == "doctor" and p.is_alive), None)
        saved_id = room.night_actions.get(doc.id) if doc else None
        if doc:
            doc.last_healed = (saved_id == doc.id)

        if killed_id:
            if killed_id == saved_id:
                await broadcast(room, {"type": "chat", "text": "Tong otdi. Shifokor yaradorni davolab saqlab qoldi! Hech kim o'lmadi.", "is_system": True})
            else:
                dead_p = room.players[killed_id]
                dead_p.is_alive = False
                await broadcast(room, {"type": "eliminated", "target_id": killed_id})
                await broadcast(room, {"type": "chat", "text": f"Tong otdi. Tunda Mafia tomonidan {dead_p.name} o'ldirildi!", "is_system": True})
                await broadcast(room, {"type": "players_update", "players": get_public_players(room)})
        else:
            await broadcast(room, {"type": "chat", "text": "Tong otdi. Mafialar bir to'xtamga kela olmadi. Tunda hech kim o'lmadi.", "is_system": True})

        if evaluate_game_status(room):
            break

def evaluate_game_status(room: GameRoom) -> bool:
    mafias = [p for p in room.players.values() if p.role == "mafia" and p.is_alive]
    citizens = [p for p in room.players.values() if p.role != "mafia" and p.is_alive]

    winner = None
    if len(mafias) == 0:
        winner = "citizens"
        asyncio.create_task(broadcast(room, {"type": "chat", "text": "🏆 G'ALABA! Shahar mafialardan tozalandi! Tinch fuqarolar g'alaba qozondi!", "is_system": True}))
    elif len(mafias) >= len(citizens):
        winner = "mafia"
        asyncio.create_task(broadcast(room, {"type": "chat", "text": "🏆 G'ALABA! Shahar mafia nazoratiga o'tdi! Mafia g'alaba qozondi!", "is_system": True}))

    if winner:
        room.phase = "game_over"
        for p in room.players.values():
            if (winner == "mafia" and p.role == "mafia") or (winner == "citizens" and p.role != "mafia"):
                if p.id in stats_db:
                    stats_db[p.id]["wins"] += 1
        return True
    return False

@app.websocket("/ws/{room_id}/{user_id}")
async def ws_handler(websocket: WebSocket, room_id: str, user_id: str, name: str = Query("O'yinchi")):
    await websocket.accept()

    if room_id not in rooms:
        rooms[room_id] = GameRoom(room_id, f"Xona #{room_id}")
    room = rooms[room_id]

    if not room.host_id or room.host_id not in room.players:
        room.host_id = user_id

    if user_id not in room.players:
        room.players[user_id] = Player(user_id, name, websocket)
    else:
        room.players[user_id].ws = websocket
        room.players[user_id].name = name

    await websocket.send_json({"type": "room_info", "id": room.id, "name": room.name})

    if room.host_id == user_id and room.phase == "lobby":
        await websocket.send_json({"type": "is_admin"})

    # Xonaga kirganda eski chat tarixini qayta yuborish
    for old_msg in room.chat_history:
        await websocket.send_json(old_msg)

    await broadcast(room, {"type": "players_update", "players": get_public_players(room)})

    try:
        while True:
            data = await websocket.receive_json()
            act = data.get("action")
            player = room.players.get(user_id)

            if act == "kick" and room.host_id == user_id:
                target_id = data.get("target_id")
                if target_id in room.players and target_id != user_id:
                    kicked_p = room.players[target_id]
                    if kicked_p.ws:
                        try:
                            await kicked_p.ws.send_json({"type": "kicked"})
                            await kicked_p.ws.close()
                        except Exception:
                            pass
                    del room.players[target_id]
                    await broadcast(room, {"type": "chat", "text": f"{kicked_p.name} xonadan chiqarildi.", "is_system": True})
                    await broadcast(room, {"type": "players_update", "players": get_public_players(room)})

            elif act == "set_timer" and room.host_id == user_id:
                room.discussion_time = int(data.get("seconds", 60))
                room.remaining_time = room.discussion_time
                await broadcast(room, {"type": "timer", "time": room.remaining_time})
                await broadcast(room, {"type": "chat", "text": f"Muhokama vaqti {room.discussion_time // 60} minutga sozlandi.", "is_system": True})

            elif act == "start_game" and room.phase == "lobby" and room.host_id == user_id:
                p_ids = list(room.players.keys())
                random.shuffle(p_ids)

                roles = ["mafia", "mafia", "mafia", "commissar", "doctor"]
                while len(roles) < len(p_ids):
                    roles.append("citizen")
                roles = roles[:len(p_ids)]
                random.shuffle(roles)

                for idx, pid in enumerate(p_ids):
                    p = room.players[pid]
                    p.role = roles[idx]
                    p.is_alive = True
                    if p.ws:
                        await p.ws.send_json({"type": "your_role", "role": p.role})

                room.task = asyncio.create_task(game_loop(room))

            elif act == "chat" and player and player.is_alive:
                if room.phase in ["lobby", "discussion"]:
                    msg = data.get("text", "").strip()
                    if msg:
                        await broadcast(room, {"type": "chat", "sender": player.name, "text": msg})

            elif act == "vote" and player and player.is_alive:
                if room.phase in ["voting", "revoting"]:
                    target_id = data.get("target_id")
                    target_player = room.players.get(target_id)
                    target_name = target_player.name if target_player else "Noma'lum"
                    room.votes[player.name] = target_id

                    # Kim kimga ovoz berganini hammaga tarqatish (Chat va profillar tagiga)
                    await broadcast(room, {
                        "type": "vote_update",
                        "voter_name": player.name,
                        "target_name": target_name,
                        "votes": room.votes
                    })

            elif act == "night_action" and player and player.is_alive and room.phase == "night":
                target_id = data.get("target_id")
                if player.role == "commissar":
                    if target_id != user_id:
                        room.night_actions[user_id] = target_id
                        verdict = "MAFIA 🔴" if room.players[target_id].role == "mafia" else "TINCH AHOLI 🟢"
                        await websocket.send_json({"type": "commissar_alert", "text": f"Tekshiruv natijasi: {room.players[target_id].name} — {verdict}"})
                elif player.role == "doctor":
                    if not (target_id == user_id and player.last_healed):
                        room.night_actions[user_id] = target_id
                elif player.role == "mafia":
                    room.night_actions[user_id] = target_id

    except WebSocketDisconnect:
        if user_id in room.players:
            room.players[user_id].ws = None