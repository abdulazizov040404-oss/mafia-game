import os
import asyncio
import random
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "Mini App ishlamoqda. static/index.html topilmadi."}

class Player:
    def __init__(self, user_id: str, name: str, ws: WebSocket):
        self.id = user_id
        self.name = name
        self.ws = ws
        self.role = "citizen"
        self.is_alive = True
        self.last_healed = False

class GameRoom:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.phase: str = "lobby"
        self.timer_seconds: int = 60
        self.remaining_time: int = 60
        self.votes: Dict[str, str] = {}
        self.night_actions: Dict[str, str] = {}
        self.task: Optional[asyncio.Task] = None

room = GameRoom()

async def broadcast(data: dict, mafia_only: bool = False):
    disconnected = []
    for pid, p in room.players.items():
        if mafia_only and p.role != "mafia":
            continue
        if p.ws:
            try:
                await p.ws.send_json(data)
            except Exception:
                disconnected.append(pid)
    for pid in disconnected:
        room.players[pid].ws = None

def get_public_players():
    return [{"id": p.id, "name": p.name, "is_alive": p.is_alive} for p in room.players.values()]

async def run_game_loop():
    while room.phase != "lobby" and room.phase != "game_over":
        # 1. KUNDUZGI MUHOKAMA
        room.phase = "discussion"
        room.remaining_time = room.timer_seconds
        await broadcast({
            "type": "phase_change",
            "phase": "discussion",
            "time": room.remaining_time
        })
        await broadcast({"type": "chat", "text": "Kunduzgi muhokama boshlandi. Gumonlanuvchilarni aniqlang!", "is_system": True})

        while room.remaining_time > 0 and room.phase == "discussion":
            await asyncio.sleep(1)
            room.remaining_time -= 1
            await broadcast({"type": "timer", "time": room.remaining_time})

        # 2. OVOZ BERISH
        room.phase = "voting"
        room.votes.clear()
        room.remaining_time = room.timer_seconds
        candidates = [{"id": p.id, "name": p.name} for p in room.players.values() if p.is_alive]
        await broadcast({
            "type": "phase_change",
            "phase": "voting",
            "time": room.remaining_time,
            "candidates": candidates
        })

        while room.remaining_time > 0 and room.phase == "voting":
            await asyncio.sleep(1)
            room.remaining_time -= 1
            await broadcast({"type": "timer", "time": room.remaining_time})

        # Hisoblash va tenglik tekshiruvi
        tally: Dict[str, int] = {}
        for target in room.votes.values():
            tally[target] = tally.get(target, 0) + 1

        eliminated_id = None
        if tally:
            max_v = max(tally.values())
            top = [tid for tid, c in tally.items() if c == max_v]

            if len(top) > 1:
                # Ovozlar teng: Qayta ovoz berish
                room.phase = "revoting"
                room.votes.clear()
                room.remaining_time = room.timer_seconds
                revote_cands = [{"id": tid, "name": room.players[tid].name} for tid in top]
                await broadcast({
                    "type": "phase_change",
                    "phase": "revoting",
                    "time": room.remaining_time,
                    "candidates": revote_cands
                })
                await broadcast({"type": "chat", "text": "Ovozlar teng! Faqat teng chiqqan nomzodlarga qayta ovoz beriladi.", "is_system": True})

                while room.remaining_time > 0 and room.phase == "revoting":
                    await asyncio.sleep(1)
                    room.remaining_time -= 1
                    await broadcast({"type": "timer", "time": room.remaining_time})

                retally: Dict[str, int] = {}
                for target in room.votes.values():
                    if target in top:
                        retally[target] = retally.get(target, 0) + 1
                if retally:
                    rmax = max(retally.values())
                    rtop = [tid for tid, c in retally.items() if c == rmax]
                    if len(rtop) == 1:
                        eliminated_id = rtop[0]
                    else:
                        await broadcast({"type": "chat", "text": "Qayta ovoz berishda ham tenglik! Bugun hech kim osilmadi.", "is_system": True})
            else:
                eliminated_id = top[0]

        if eliminated_id:
            target_p = room.players[eliminated_id]
            target_p.is_alive = False
            await broadcast({"type": "eliminated", "target_id": eliminated_id})
            await broadcast({"type": "chat", "text": f"Sud hukmi bilan {target_p.name} ({target_p.role.upper()}) o'yindan chetlatildi!", "is_system": True})
            await broadcast({"type": "players_update", "players": get_public_players()})

        if check_victory():
            break

        # 3. TUN BOSQICHI
        room.phase = "night"
        room.night_actions.clear()
        room.remaining_time = room.timer_seconds

        alive_targets = [{"id": p.id, "name": p.name} for p in room.players.values() if p.is_alive]
        await broadcast({
            "type": "phase_change",
            "phase": "night",
            "time": room.remaining_time,
            "targets": alive_targets
        })
        await broadcast({"type": "chat", "text": "Tun tushdi. Shahar ahli ko'z yumdi, faol rollar uyg'ondi...", "is_system": True})
        await broadcast({"type": "chat", "text": "Mafialar, o'zaro kelishib bitta nishonni tanlang!", "is_system": True}, mafia_only=True)

        while room.remaining_time > 0 and room.phase == "night":
            await asyncio.sleep(1)
            room.remaining_time -= 1
            await broadcast({"type": "timer", "time": room.remaining_time})

        # Tungi natijalar
        alive_mafias = [p.id for p in room.players.values() if p.role == "mafia" and p.is_alive]
        mafia_shots = [room.night_actions[mid] for mid in alive_mafias if mid in room.night_actions]

        # Mafia konsensusi: Barcha tirik mafialar bitta odamni tanlagan bo'lishi kerak
        killed_target = None
        if len(mafia_shots) == len(alive_mafias) and len(set(mafia_shots)) == 1:
            killed_target = mafia_shots[0]

        # Doktor davolagan o'yinchi
        doctor_p = next((p for p in room.players.values() if p.role == "doctor" and p.is_alive), None)
        saved_target = room.night_actions.get(doctor_p.id) if doctor_p else None

        if doctor_p:
            doctor_p.last_healed = (saved_target == doctor_p.id)

        if killed_target:
            if killed_target == saved_target:
                await broadcast({"type": "chat", "text": "Tong otdi. Tunda hujum bo'ldi, ammo mohir shifokor yaradorni saqlab qoldi!", "is_system": True})
            else:
                victim = room.players[killed_target]
                victim.is_alive = False
                await broadcast({"type": "eliminated", "target_id": killed_target})
                await broadcast({"type": "chat", "text": f"Tong otdi. Tunda shafqatsiz mafia tomonidan {victim.name} o'ldirildi!", "is_system": True})
                await broadcast({"type": "players_update", "players": get_public_players()})
        else:
            await broadcast({"type": "chat", "text": "Tong otdi. Mafialar bir fikrga kela olmadi. Tunda hech kim jabrlanmadi.", "is_system": True})

        if check_victory():
            break

def check_victory() -> bool:
    mafias = [p for p in room.players.values() if p.role == "mafia" and p.is_alive]
    peacefuls = [p for p in room.players.values() if p.role != "mafia" and p.is_alive]

    if len(mafias) == 0:
        room.phase = "game_over"
        asyncio.create_task(broadcast({"type": "chat", "text": "🏆 G'ALABA! Shahar barcha mafiyalardan tozalandi! Tinch aholi yutdi!", "is_system": True}))
        return True
    if len(mafias) >= len(peacefuls):
        room.phase = "game_over"
        asyncio.create_task(broadcast({"type": "chat", "text": "🏆 G'ALABA! Mafialar shaharni to'liq nazoratga oldi! Mafia yutdi!", "is_system": True}))
        return True
    return False

@app.websocket("/ws/{user_id}")
async def ws_endpoint(websocket: WebSocket, user_id: str, name: str = Query("O'yinchi")):
    await websocket.accept()

    if user_id not in room.players:
        room.players[user_id] = Player(user_id, name, websocket)
    else:
        room.players[user_id].ws = websocket
        room.players[user_id].name = name

    await broadcast({"type": "players_update", "players": get_public_players()})

    try:
        while True:
            data = await websocket.receive_json()
            act = data.get("action")
            player = room.players.get(user_id)

            if act == "set_timer":
                room.timer_seconds = int(data.get("seconds", 60))
                await broadcast({"type": "chat", "text": f"Vaqt {room.timer_seconds // 60} minutga o'zgartirildi.", "is_system": True})

            elif act == "start_game" and room.phase == "lobby":
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
                    p.last_healed = False
                    if p.ws:
                        await p.ws.send_json({"type": "your_role", "role": p.role})

                room.task = asyncio.create_task(run_game_loop())

            elif act == "chat" and player and player.is_alive:
                msg = data.get("text", "").strip()
                if not msg:
                    continue

                if room.phase == "discussion":
                    await broadcast({"type": "chat", "sender": player.name, "text": msg})
                elif room.phase == "night" and player.role == "mafia":
                    await broadcast({"type": "chat", "sender": f"🕶 {player.name}", "text": msg, "is_mafia": True}, mafia_only=True)

            elif act == "vote" and player and player.is_alive:
                if room.phase in ["voting", "revoting"]:
                    room.votes[user_id] = data.get("target_id")
                    await broadcast({"type": "chat", "text": f"{player.name} o'z tanlovini qildi.", "is_system": True})

            elif act == "night_action" and player and player.is_alive and room.phase == "night":
                target_id = data.get("target_id")

                # Komissar o'zini tekshira olmaydi
                if player.role == "commissar":
                    if target_id == user_id:
                        continue
                    room.night_actions[user_id] = target_id
                    target_role = room.players[target_id].role
                    verdict = "MAFIA 🔴" if target_role == "mafia" else "TINCH AHOLI 🟢"
                    await websocket.send_json({"type": "commissar_alert", "text": f"Tekshiruv natijasi: {room.players[target_id].name} — {verdict}"})

                # Doktor ketma-ket 2 marta o'zini saqlay olmaydi
                elif player.role == "doctor":
                    if target_id == user_id and player.last_healed:
                        await websocket.send_json({"type": "commissar_alert", "text": "Siz ketma-ket ikki marta o'zingizni davolay olmaysiz!"})
                        continue
                    room.night_actions[user_id] = target_id

                elif player.role == "mafia":
                    room.night_actions[user_id] = target_id
                    await broadcast({"type": "chat", "text": f"Mafia a'zosi {player.name} nishon tanladi.", "is_system": True}, mafia_only=True)

    except WebSocketDisconnect:
        if user_id in room.players:
            room.players[user_id].ws = None