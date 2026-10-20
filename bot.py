"""
Mafiya Telegram Mini App serveri.
Ishga tushirish: python server.py
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import random
import re
import time
from collections import Counter
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Tokeningiz ulandi
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8825986464:AAEx4CHxaYeE7xhzrTpGYpJOx8K_Ol4Lf0w")
SECRET = hashlib.sha256(("mafia-token:" + BOT_TOKEN).encode()).digest()

# Sinov paytida o'yinni 2 kishi bilan boshlash uchun MIN_P = 2 qilingan (xohlasangiz 5 ga o'zgartirasiz)
MIN_P, MAX_P = 2, 12
T_DEAL, T_NIGHT, T_DAY, T_VOTE = 10, 30, 60, 25   # sekund
MAFIA = {"mafiya", "don"}
ACTORS = {"mafiya", "don", "komissar", "shifokor", "maniak"}

app = FastAPI()

# Har qanday manzildan keladigan ulanishlarni qabul qilish (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- Telegram autentifikatsiya ----------------
def verify_init_data(init_data: str) -> dict:
    if not init_data:
        raise ValueError("initData bo'sh")
    data = dict(parse_qsl(init_data, keep_blank_values=True))
    got = data.pop("hash", None)
    if not got:
        raise ValueError("hash yo'q")
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, got):
        raise ValueError("imzo noto'g'ri")
    if time.time() - int(data.get("auth_date", "0")) > 86400:
        raise ValueError("muddati o'tgan")
    user = json.loads(data["user"])
    if user.get("is_bot"):
        raise ValueError("bot")
    return user


def make_token(uid: int) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"u": uid, "e": int(time.time()) + 86400}).encode()).decode()
    sig = hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()
    return body + "." + sig


def read_token(tok: str) -> int:
    try:
        body, sig = tok.rsplit(".", 1)
        good = hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(good, sig):
            raise ValueError
        d = json.loads(base64.urlsafe_b64decode(body))
        if d["e"] < time.time():
            raise ValueError
        return int(d["u"])
    except Exception:
        raise ValueError("Token xato")


class AuthIn(BaseModel):
    initData: str


@app.post("/api/auth")
async def auth(a: AuthIn):
    try:
        u = verify_init_data(a.initData)
    except Exception as e:
        raise HTTPException(401, f"Telegram tasdiqlanmadi: {str(e)}")
    return {"token": make_token(u["id"]), "name": u.get("first_name", "O'yinchi")}


# ---------------- O'yin Mantiqi ----------------
class Player:
    def __init__(self, uid, pid, nick):
        self.uid, self.pid, self.nick = uid, pid, nick
        self.ws = None
        self.alive = True
        self.role = None
        self.last_chat = 0.0


def assign_roles(n):
    if n <= 3:
        roles = ["mafiya", "komissar"] if n == 2 else ["mafiya", "komissar", "mirny"]
        random.shuffle(roles)
        return roles

    m = max(1, n // 3)
    roles = ["don"] + ["mafiya"] * (m - 1) if n >= 7 else ["mafiya"] * m
    roles += ["komissar", "shifokor"]
    if n >= 8:
        roles.append("maniak")
    roles += ["mirny"] * (n - len(roles))
    random.shuffle(roles)
    return roles


rooms: dict = {}
user_room: dict = {}
conns: dict = {}


class Room:
    def __init__(self, code, mode):
        self.code, self.mode = code, mode
        self.players = {}
        self.by_pid = {}
        self.next_pid = 1
        self.host = None
        self.phase, self.day = "lobby", 0
        self.deadline = 0.0
        self.task = None
        self.acts, self.votes = {}, {}
        self.last_heal = None

    def pub(self):
        return [{"pid": p.pid, "nick": p.nick, "alive": p.alive} for p in self.players.values()]

    async def send(self, p, typ, data=None):
        if p.ws:
            try:
                await p.ws.send_text(json.dumps({"type": typ, "data": data or {}}))
            except Exception:
                pass

    async def bcast(self, typ, data=None, pred=None):
        await asyncio.gather(*[self.send(p, typ, data) for p in self.players.values() if not pred or pred(p)])

    def lobby_msg(self):
        h = self.players[self.host].pid if self.host in self.players else None
        return {"players": self.pub(), "host": h, "mode": self.mode, "room": self.code}

    def phase_msg(self):
        return {
            "name": self.phase,
            "day": self.day,
            "ms": max(0, int((self.deadline - time.time()) * 1000)),
            "players": self.pub(),
            "mode": self.mode
        }

    async def snapshot(self, p):
        await self.send(p, "me", {"pid": p.pid, "nick": p.nick})
        if self.phase == "lobby":
            await self.send(p, "lobby", self.lobby_msg())
        else:
            await self.send(p, "phase", self.phase_msg())
            mates = [q.nick for q in self.players.values() if q.role in MAFIA and q is not p] if p.role in MAFIA else []
            await self.send(p, "role", {"role": p.role, "mates": mates})

    def remove(self, uid):
        p = self.players.pop(uid, None)
        user_room.pop(uid, None)
        if p:
            self.by_pid.pop(p.pid, None)
        if not self.players:
            self.cleanup()
        elif self.host == uid and self.players:
            self.host = next(iter(self.players))
        return p

    def cleanup(self):
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()
        for uid in list(self.players):
            user_room.pop(uid, None)
        if rooms.get(self.code) is self:
            rooms.pop(self.code, None)

    async def disconnected(self, uid):
        p = self.players.get(uid)
        if not p:
            return
        p.ws = None
        if self.phase == "lobby":
            self.remove(uid)
            if self.code in rooms:
                await self.bcast("lobby", self.lobby_msg())
        elif not any(q.ws for q in self.players.values()):
            self.cleanup()

    async def start(self):
        roles = assign_roles(len(self.players))
        for p, r in zip(self.players.values(), roles):
            p.role, p.alive = r, True
        self.last_heal = None
        await self.set_phase("night", 0, T_DEAL)
        for p in self.players.values():
            mates = [q.nick for q in self.players.values() if q.role in MAFIA and q is not p] if p.role in MAFIA else []
            await self.send(p, "role", {"role": p.role, "mates": mates})

    async def set_phase(self, name, day, secs):
        self.phase, self.day = name, day
        self.deadline = time.time() + secs
        self.acts.clear()
        self.votes.clear()
        await self.bcast("phase", self.phase_msg())
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()
        self.task = asyncio.create_task(self._timer(secs))

    async def _timer(self, secs):
        try:
            await asyncio.sleep(secs)
        except asyncio.CancelledError:
            return
        await self.advance()

    async def advance(self):
        if self.phase == "night":
            if self.day == 0:
                return await self.set_phase("night", 1, T_NIGHT)
            await self.resolve_night()
            if await self.check_end():
                return
            return await self.set_phase("day", self.day, T_DAY)
        if self.phase == "day":
            return await self.set_phase("vote", self.day, T_VOTE)
        if self.phase == "vote":
            await self.resolve_vote()
            if await self.check_end():
                return
            return await self.set_phase("night", self.day + 1, T_NIGHT)

    async def act(self, p, target_pid):
        if self.phase != "night" or self.day < 1 or not p.alive or p.role not in ACTORS:
            return
        if p.pid in self.acts:
            return await self.send(p, "error", {"text": "Tanlov allaqachon qilingan"})
        t = self.by_pid.get(target_pid)
        if not t or not t.alive:
            return
        if p.role in MAFIA and t.role in MAFIA:
            return await self.send(p, "error", {"text": "Jamoadoshni tanlab bo'lmaydi"})
        if p.role in ("komissar", "maniak") and t is p:
            return await self.send(p, "error", {"text": "O'zingizni tanlab bo'lmaydi"})
        if p.role == "shifokor" and t.pid == self.last_heal:
            return await self.send(p, "error", {"text": "Ketma-ket bir odamni davolab bo'lmaydi"})
        self.acts[p.pid] = t.pid
        if p.role == "komissar":
            await self.send(p, "check", {"pid": t.pid, "team": "mafia" if t.role == "mafiya" else "city"})
        need = [q.pid for q in self.players.values() if q.alive and q.role in ACTORS]
        if all(x in self.acts for x in need):
            await self.advance()

    async def resolve_night(self):
        role_of = lambda pid: self.by_pid[pid].role
        maf = [t for pid, t in self.acts.items() if role_of(pid) in MAFIA]
        don = [t for pid, t in self.acts.items() if role_of(pid) == "don"]
        mt = None
        if don:
            mt = don[0]
        elif maf:
            c = Counter(maf)
            top = max(c.values())
            mt = random.choice([k for k, v in c.items() if v == top])
        heal = next((t for pid, t in self.acts.items() if role_of(pid) == "shifokor"), None)
        mk = next((t for pid, t in self.acts.items() if role_of(pid) == "maniak"), None)
        self.last_heal = heal
        dead = []
        for v in (mt, mk):
            if v is not None and v != heal and self.by_pid[v].alive and v not in dead:
                dead.append(v)
        for v in dead:
            self.by_pid[v].alive = False
        txt = "Tong otdi. " + (", ".join(self.by_pid[v].nick for v in dead) + " o'ldirildi." if dead else "Bu tunda hech kim o'lmadi.")
        await self.bcast("result", {"text": txt})

    async def vote(self, p, target_pid):
        if self.phase != "vote" or not p.alive:
            return
        t = self.by_pid.get(target_pid)
        if not t or not t.alive or t is p:
            return
        self.votes[p.pid] = t.pid
        await self.send(p, "result", {"text": "Ovozingiz qabul qilindi"})
        if all(q.pid in self.votes for q in self.players.values() if q.alive):
            await self.advance()

    async def resolve_vote(self):
        c = Counter(self.votes.values())
        out = None
        if c:
            top = max(c.values())
            lead = [k for k, v in c.items() if v == top]
            if len(lead) == 1:
                out = self.by_pid[lead[0]]
        if out:
            out.alive = False
            await self.bcast("result", {"text": f"{out.nick} ovoz bilan chetlatildi."})
        else:
            await self.bcast("result", {"text": "Ovozlar teng. Hech kim chetlatilmadi."})

    def winner(self):
        al = [p for p in self.players.values() if p.alive]
        maf = [p for p in al if p.role in MAFIA]
        man = [p for p in al if p.role == "maniak"]
        city = len(al) - len(maf) - len(man)
        if not maf and not man:
            return "Shahar ahli yutdi"
        if maf and len(maf) >= len(al) - len(maf):
            return "Mafiya yutdi"
        if man and not maf and city <= 1:
            return "Maniak yutdi"
        return None

    async def check_end(self):
        w = self.winner()
        if not w:
            return False
        await self.bcast("end", {"winner": w, "roles": [{"nick": p.nick, "role": p.role} for p in self.players.values()]})
        self.phase = "end"
        self.cleanup()
        return True

    async def chat(self, p, text):
        if self.mode != "chat" or not p.alive:
            return
        text = str(text).strip()[:200]
        now = time.time()
        if not text or now - p.last_chat < 0.7:
            return
        p.last_chat = now
        if self.phase == "day":
            await self.bcast("chat", {"who": p.nick, "text": text, "scope": "all"})
        elif self.phase == "night" and self.day >= 1 and p.role in MAFIA:
            await self.bcast("chat", {"who": p.nick, "text": text, "scope": "mafia"}, lambda q: q.role in MAFIA and q.alive)


# ---------------- WebSocket ----------------
NICK_BAD = re.compile(r"[<>&\"'`\x00-\x1f]")
CODE_OK = re.compile(r"[A-Za-z0-9_-]{1,20}")


async def err(ws, text):
    try:
        await ws.send_text(json.dumps({"type": "error", "data": {"text": text}}))
    except Exception:
        pass


async def do_join(uid, ws, d):
    nick = NICK_BAD.sub("", str(d.get("nick", ""))).strip()
    code = str(d.get("room") or "main")
    mode = d.get("mode")
    if not 2 <= len(nick) <= 16:
        return await err(ws, "Taxallus 2 dan 16 belgigacha bo'lsin")
    if not CODE_OK.fullmatch(code) or mode not in ("chat", "voice"):
        return await err(ws, "Xona kodi yoki rejim noto'g'ri")
    cur = user_room.get(uid)
    if cur and cur.code != code:
        if cur.phase != "lobby":
            return await err(ws, "Siz boshqa o'yindasiz")
        cur.remove(uid)
        if cur.code in rooms:
            await cur.bcast("lobby", cur.lobby_msg())
    room = rooms.get(code)
    if not room:
        room = rooms[code] = Room(code, mode)
    elif room.mode != mode:
        return await err(ws, f"Bu xona '{room.mode}' rejimida")
    p = room.players.get(uid)
    if p:
        if room.phase != "lobby":
            p.ws = ws
            return await room.snapshot(p)
    elif room.phase != "lobby":
        return await err(ws, "O'yin allaqachon boshlangan")
    elif len(room.players) >= MAX_P:
        return await err(ws, "Xona to'la")
    if any(q.nick.lower() == nick.lower() and q.uid != uid for q in room.players.values()):
        return await err(ws, "Bu taxallus band")
    if not p:
        p = Player(uid, room.next_pid, nick)
        room.next_pid += 1
        room.players[uid] = p
        room.by_pid[p.pid] = p
        user_room[uid] = room
        if room.host is None:
            room.host = uid
    p.nick, p.ws = nick, ws
    await room.send(p, "me", {"pid": p.pid, "nick": p.nick})
    await room.bcast("lobby", room.lobby_msg())


async def on_msg(uid, ws, m):
    t, d = m.get("type"), m.get("data") or {}
    if t == "join":
        return await do_join(uid, ws, d)
    room = user_room.get(uid)
    if not room:
        return
    p = room.players.get(uid)
    if not p:
        return
    if t == "leave" and room.phase == "lobby":
        room.remove(uid)
        if room.code in rooms:
            await room.bcast("lobby", room.lobby_msg())
    elif t == "start" and room.phase == "lobby" and room.host == uid:
        if len(room.players) < MIN_P:
            return await err(ws, f"Kamida {MIN_P} o'yinchi kerak")
        await room.start()
    elif t == "action":
        await room.act(p, d.get("target"))
    elif t == "vote":
        await room.vote(p, d.get("target"))
    elif t == "chat":
        await room.chat(p, d.get("text", ""))
    elif t == "speaking" and room.mode == "voice":
        on = bool(d.get("on")) and room.phase == "day" and p.alive
        await room.bcast("speaking", {"pid": p.pid, "on": on})
    elif t == "rtc" and room.mode == "voice":
        q = room.by_pid.get(d.get("to"))
        if q and q is not p:
            await room.send(q, "rtc", {"from": p.pid, "kind": d.get("kind"), "payload": d.get("payload")})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    try:
        uid = read_token(ws.query_params.get("token", ""))
    except Exception:
        await ws.close(4001)
        return
    await ws.accept()
    old = conns.get(uid)
    if old:
        try:
            await old.close(4000)
        except Exception:
            pass
    conns[uid] = ws
    room = user_room.get(uid)
    if room and uid in room.players:
        p = room.players[uid]
        p.ws = ws
        await room.snapshot(p)
    try:
        while True:
            m = json.loads(await ws.receive_text())
            try:
                await on_msg(uid, ws, m)
            except Exception as e:
                print("xato:", repr(e))
    except (WebSocketDisconnect, json.JSONDecodeError):
        pass
    except Exception:
        pass
    finally:
        if conns.get(uid) is ws:
            conns.pop(uid, None)
            r = user_room.get(uid)
            if r:
                await r.disconnected(uid)


# Static fayllarni ulash
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=8000, reload=True)