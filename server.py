from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncpg
import jwt
import bcrypt
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET", "changeme")

# Serve frontend folder as the website
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

# ---------------------------
# Database Helper
# ---------------------------
async def db():
    return await asyncpg.connect(DATABASE_URL)

# ---------------------------
# Models
# ---------------------------
class Login(BaseModel):
    username: str
    password: str

class RO(BaseModel):
    ro: str
    customer: str
    vehicle: str
    advisor: str
    tech: str
    status: str

# ---------------------------
# Login
# ---------------------------
@app.post("/api/login")
async def login(credentials: Login):
    conn = await db()
    user = await conn.fetchrow(
        "SELECT * FROM users WHERE username=$1",
        credentials.username
    )
    await conn.close()

    if not user:
        return {"error": "User not found"}

    if not bcrypt.checkpw(credentials.password.encode(), user["password"].encode()):
        return {"error": "Invalid password"}

    token = jwt.encode(
        {"user": credentials.username, "role": user["role"]},
        JWT_SECRET,
        algorithm="HS256"
    )

    return {"token": token}

# ---------------------------
# Get Current User
# ---------------------------
@app.get("/api/user/me")
async def me(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        return {"error": "Unauthorized"}

    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    return payload

# ---------------------------
# Add Repair Order
# ---------------------------
@app.post("/api/ro/add")
async def add_ro(ro: RO):
    conn = await db()
    await conn.execute("""
        INSERT INTO repair_orders (ro, customer, vehicle, advisor, tech, status)
        VALUES ($1,$2,$3,$4,$5,$6)
    """, ro.ro, ro.customer, ro.vehicle, ro.advisor, ro.tech, ro.status)
    await conn.close()
    await notify()
    return {"success": True}

# ---------------------------
# Get All ROs
# ---------------------------
@app.get("/api/ro/all")
async def get_all():
    conn = await db()
    rows = await conn.fetch("SELECT * FROM repair_orders ORDER BY id DESC")
    await conn.close()
    return {"repairs": [dict(r) for r in rows]}

# ---------------------------
# Update RO Status
# ---------------------------
@app.post("/api/ro/status/{ro_id}")
async def update_status(ro_id: int, status: dict):
    conn = await db()
    await conn.execute(
        "UPDATE repair_orders SET status=$1 WHERE id=$2",
        status["status"], ro_id
    )
    await conn.close()
    await notify()
    return {"success": True}

# ---------------------------
# WebSockets (Live Updates)
# ---------------------------
clients = set()

@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except:
        clients.remove(ws)

async def notify():
    dead = []
    for ws in clients:
        try:
            await ws.send_text("update")
        except:
            dead.append(ws)
    for d in dead:
        clients.remove(d)
