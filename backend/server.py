from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

from auth import build_auth_router, seed_admin, decode_ws_token
from table_manager import TableManager


mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Will Poker API")

auth_router, get_current_user = build_auth_router(db)
app.include_router(auth_router)

api_router = APIRouter(prefix="/api")
table_manager = TableManager(db)


@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("username", unique=True)
    await db.hands.create_index("table_id")
    await db.hands.create_index("played_at")
    await db.login_attempts.create_index("identifier")
    await seed_admin(db)
    await table_manager.bootstrap_default_tables()


@app.on_event("shutdown")
async def on_shutdown():
    # in-memory seats are lost on restart: return stacks to bankrolls first
    try:
        await table_manager.cash_out_everyone()
    except Exception as e:
        logging.exception("cash out on shutdown failed: %s", e)
    client.close()


# ---------- API ----------
@api_router.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@api_router.get("/tables")
async def list_tables():
    return table_manager.list_tables()


class JoinTableIn(BaseModel):
    buy_in: int = Field(gt=0)
    seat: Optional[int] = None


@api_router.post("/tables/{table_id}/join")
async def join_table(table_id: str, body: JoinTableIn, user: dict = Depends(get_current_user)):
    table = table_manager.get(table_id)
    if not table:
        raise HTTPException(404, "Table not found")
    meta = table.meta
    if body.buy_in < meta["buy_in_min"] or body.buy_in > meta["buy_in_max"]:
        raise HTTPException(400, f"Buy-in must be between {meta['buy_in_min']} and {meta['buy_in_max']}")
    if user["bankroll"] < body.buy_in:
        raise HTTPException(400, "Insufficient bankroll")
    # find seat
    async with table.lock:
        if any(p.user_id == user["id"] for p in table.game.seats.values()):
            raise HTTPException(400, "Already seated at this table")
        used = set(table.game.seats.keys())
        seat = body.seat
        if seat is None or seat in used:
            for s in range(meta["max_seats"]):
                if s not in used:
                    seat = s
                    break
        if seat is None or seat in used:
            raise HTTPException(400, "No available seats")
        table.game.sit(user["id"], user["username"], seat, body.buy_in)
        # deduct bankroll
        await db.users.update_one({"id": user["id"]}, {"$inc": {"bankroll": -body.buy_in}})
        await table.maybe_start_hand()
        await table.broadcast()
    return {"ok": True, "seat": seat}


@api_router.post("/tables/{table_id}/leave")
async def leave_table(table_id: str, user: dict = Depends(get_current_user)):
    table = table_manager.get(table_id)
    if not table:
        raise HTTPException(404, "Table not found")
    async with table.lock:
        seat = None
        for s, p in table.game.seats.items():
            if p.user_id == user["id"]:
                seat = s
                break
        if seat is None:
            raise HTTPException(400, "Not seated")
        # If in an active hand, mark folded first, else refund immediately
        p = table.game.seats[seat]
        stack_return = p.stack
        # In-hand refund: the chips in current pot are lost; only stack returns.
        if table.game.hand and not table.game.hand.ended and not p.folded:
            try:
                if table.game.hand.to_act == seat:
                    table.game.act(user["id"], "fold")
                else:
                    p.folded = True
            except Exception:
                pass
        table.game.seats.pop(seat, None)
        forfeited = p.total_committed if (table.game.hand and not table.game.hand.ended) else 0
        await db.users.update_one({"id": user["id"]}, {"$inc": {"bankroll": stack_return}})
        await table.broadcast()
    return {"ok": True, "returned": stack_return, "forfeited_to_pot": forfeited}


@api_router.get("/hands/mine")
async def my_hands(user: dict = Depends(get_current_user), limit: int = 50):
    cursor = db.hands.find(
        {"players.user_id": user["id"]}, {"_id": 0}
    ).sort("played_at", -1).limit(limit)
    return await cursor.to_list(limit)


@api_router.get("/admin/stats")
async def admin_stats(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    users_count = await db.users.count_documents({})
    hands_count = await db.hands.count_documents({})
    tables = table_manager.list_tables()
    active_players = sum(t["seated"] for t in tables)
    return {
        "users": users_count,
        "hands": hands_count,
        "tables": len(tables),
        "active_players": active_players,
    }


@api_router.get("/admin/users")
async def admin_users(user: dict = Depends(get_current_user), limit: int = 100):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    cursor = db.users.find({}, {"_id": 0, "password_hash": 0}).limit(limit)
    return await cursor.to_list(limit)


class BankrollAdjustIn(BaseModel):
    user_id: str
    delta: int
    reason: str = ""


@api_router.post("/admin/bankroll")
async def admin_bankroll(body: BankrollAdjustIn, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    target = await db.users.find_one({"id": body.user_id})
    if not target:
        raise HTTPException(404, "User not found")
    await db.users.update_one({"id": body.user_id}, {"$inc": {"bankroll": body.delta}})
    await db.audit_log.insert_one({
        "at": datetime.now(timezone.utc).isoformat(),
        "actor": user["id"], "target": body.user_id,
        "delta": body.delta, "reason": body.reason,
    })
    return {"ok": True}


app.include_router(api_router)


# ---------- WebSocket ----------
@app.websocket("/api/ws/table/{table_id}")
async def ws_table(websocket: WebSocket, table_id: str, token: str = Query(...)):
    await websocket.accept()
    user = await decode_ws_token(token, db)
    if not user:
        await websocket.send_json({"type": "error", "message": "auth failed"})
        await websocket.close()
        return
    table = table_manager.get(table_id)
    if not table:
        await websocket.send_json({"type": "error", "message": "table not found"})
        await websocket.close()
        return
    await table.add_client(user["id"], websocket)
    # mark connected if seated
    for p in table.game.seats.values():
        if p.user_id == user["id"]:
            p.connected = True
    await websocket.send_json({"type": "state", "state": table.snapshot(user["id"])})
    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")
            if mtype == "action":
                action = msg.get("action")
                amount = int(msg.get("amount", 0) or 0)
                async with table.lock:
                    try:
                        table.game.act(user["id"], action, amount)
                    except Exception as e:
                        await websocket.send_json({"type": "error", "message": str(e)})
                        continue
                    await table._post_action_flow()
            elif mtype == "chat":
                text = str(msg.get("text", ""))[:200].strip()
                if text:
                    table.chat.append({
                        "user_id": user["id"],
                        "username": user["username"],
                        "text": text,
                        "at": datetime.now(timezone.utc).isoformat(),
                    })
                    await table.broadcast()
            elif mtype == "ping":
                await websocket.send_json({"type": "pong"})
            elif mtype == "sit_out":
                async with table.lock:
                    for p in table.game.seats.values():
                        if p.user_id == user["id"]:
                            p.sitting_out = bool(msg.get("value", True))
                    await table.broadcast()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.exception("ws error: %s", e)
    finally:
        await table.remove_client(user["id"], websocket)
        # mark disconnected
        for p in table.game.seats.values():
            if p.user_id == user["id"]:
                p.connected = False


# ---------- CORS ----------
_cors_origins = os.environ['CORS_ORIGINS']
if _cors_origins.strip() == '*':
    # credentialed requests cannot use a literal '*' origin: echo the caller instead
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origin_regex=".*",
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=[o.strip() for o in _cors_origins.split(',') if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
