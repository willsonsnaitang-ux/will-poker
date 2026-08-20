"""JWT authentication utilities and endpoints."""
import os
import uuid
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, EmailStr

JWT_ALGORITHM = "HS256"
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id, "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])


def _set_cookies(response: Response, access: str, refresh: str):
    response.set_cookie(
        "access_token", access, httponly=True, secure=True,
        samesite="none", max_age=60 * 60 * 24, path="/",
    )
    response.set_cookie(
        "refresh_token", refresh, httponly=True, secure=True,
        samesite="none", max_age=60 * 60 * 24 * 7, path="/",
    )


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    username: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _user_public(u: dict) -> dict:
    return {
        "id": u["id"],
        "email": u["email"],
        "username": u.get("username", ""),
        "bankroll": u.get("bankroll", 0),
        "role": u.get("role", "user"),
        "created_at": u.get("created_at"),
    }


def build_auth_router(db):
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    async def get_current_user(request: Request) -> dict:
        token = request.cookies.get("access_token")
        if not token:
            header = request.headers.get("Authorization", "")
            if header.startswith("Bearer "):
                token = header[7:]
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user.pop("password_hash", None)
        return user

    @router.post("/register")
    async def register(body: RegisterIn, response: Response):
        email = body.email.lower().strip()
        if len(body.password) < 6:
            raise HTTPException(status_code=400, detail="Password too short (min 6)")
        if len(body.username.strip()) < 3:
            raise HTTPException(status_code=400, detail="Username too short (min 3)")
        existing = await db.users.find_one({"email": email})
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        existing_uname = await db.users.find_one({"username": body.username.strip()})
        if existing_uname:
            raise HTTPException(status_code=400, detail="Username already taken")
        starting = int(os.environ.get("STARTING_BANKROLL", "10000"))
        user = {
            "id": str(uuid.uuid4()),
            "email": email,
            "username": body.username.strip(),
            "password_hash": hash_password(body.password),
            "bankroll": starting,
            "role": "user",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
        access = create_access_token(user["id"], user["email"])
        refresh = create_refresh_token(user["id"])
        _set_cookies(response, access, refresh)
        return _user_public(user)

    @router.post("/login")
    async def login(body: LoginIn, request: Request, response: Response):
        email = body.email.lower().strip()
        # key on email only: the ingress presents several client IPs per user
        identifier = email
        now = datetime.now(timezone.utc)

        record = await db.login_attempts.find_one({"identifier": identifier})
        if record and record.get("locked_until"):
            locked_until = datetime.fromisoformat(record["locked_until"])
            if locked_until > now:
                remaining = int((locked_until - now).total_seconds() // 60) + 1
                raise HTTPException(
                    status_code=423,
                    detail=f"Too many failed attempts. Try again in {remaining} minute(s).",
                )

        user = await db.users.find_one({"email": email})
        if not user or not verify_password(body.password, user["password_hash"]):
            fails = (record.get("fails", 0) if record else 0) + 1
            update = {"fails": fails, "last_at": now.isoformat()}
            if fails >= MAX_LOGIN_ATTEMPTS:
                update["locked_until"] = (
                    now + timedelta(minutes=LOCKOUT_MINUTES)
                ).isoformat()
                update["fails"] = 0
            await db.login_attempts.update_one(
                {"identifier": identifier}, {"$set": update}, upsert=True
            )
            raise HTTPException(status_code=401, detail="Invalid email or password")

        await db.login_attempts.delete_one({"identifier": identifier})
        access = create_access_token(user["id"], user["email"])
        refresh = create_refresh_token(user["id"])
        _set_cookies(response, access, refresh)
        return _user_public(user)

    @router.post("/logout")
    async def logout(response: Response):
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")
        return {"ok": True}

    @router.get("/me")
    async def me(user: dict = Depends(get_current_user)):
        return _user_public(user)

    @router.post("/ws-token")
    async def ws_token(user: dict = Depends(get_current_user)):
        # short-lived token embedded in WS query string
        token = create_access_token(user["id"], user["email"])
        return {"token": token}

    @router.post("/refresh")
    async def refresh(request: Request, response: Response):
        token = request.cookies.get("refresh_token")
        if not token:
            raise HTTPException(status_code=401, detail="No refresh token")
        try:
            payload = decode_token(token)
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Wrong token type")
        user = await db.users.find_one({"id": payload["sub"]})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access = create_access_token(user["id"], user["email"])
        response.set_cookie(
            "access_token", access, httponly=True, secure=True,
            samesite="none", max_age=60 * 60 * 24, path="/",
        )
        return {"ok": True}

    return router, get_current_user


async def seed_admin(db):
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@willpoker.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": admin_email,
            "username": "admin",
            "password_hash": hash_password(admin_password),
            "bankroll": 1_000_000,
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}},
        )


async def decode_ws_token(token: str, db) -> dict | None:
    """Decode token for WebSocket auth. Returns user dict or None."""
    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != "access":
        return None
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if user:
        user.pop("password_hash", None)
    return user
