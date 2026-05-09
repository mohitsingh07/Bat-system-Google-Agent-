import json
import jwt
import datetime

from fastapi import FastAPI
from fastapi import WebSocket
from fastapi import Form
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketDisconnect

from sqlalchemy import create_engine
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String

from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session

from passlib.context import CryptContext

from google.genai import types

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from agent import root_agent

# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI()

# =========================================================
# SECRET KEY
# =========================================================

SECRET_KEY = "SUPER_SECRET_KEY"

# =========================================================
# DATABASE
# =========================================================

DATABASE_URL = "sqlite:///./users.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

# =========================================================
# USER MODEL
# =========================================================

class User(Base):

    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    username = Column(
        String,
        unique=True,
        index=True,
    )

    password = Column(String)

# =========================================================
# CHAT MODEL
# =========================================================

class Chat(Base):

    __tablename__ = "chats"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(Integer)

    chat_id = Column(
        String,
        unique=True,
    )

    title = Column(String)

# =========================================================
# MESSAGE MODEL
# =========================================================

class Message(Base):

    __tablename__ = "messages"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    chat_id = Column(String)

    role = Column(String)

    content = Column(String)

# =========================================================
# CREATE TABLES
# =========================================================

Base.metadata.create_all(bind=engine)

# =========================================================
# PASSWORD HASHING
# =========================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

# =========================================================
# DATABASE SESSION
# =========================================================

def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()

# =========================================================
# STATIC FILES
# =========================================================

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)

# =========================================================
# ADK SETUP
# =========================================================

APP_NAME = "custom_chat_app"

session_service = InMemorySessionService()

runner = Runner(
    app_name=APP_NAME,
    agent=root_agent,
    session_service=session_service,
)

# =========================================================
# JWT FUNCTIONS
# =========================================================

def create_token(username):

    payload = {

        "username": username,

        "exp": datetime.datetime.utcnow()
        + datetime.timedelta(days=1),

    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm="HS256",
    )

    return token

def verify_token(token):

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256"],
        )

        return payload["username"]

    except:
        return None

# =========================================================
# GET CURRENT USER
# =========================================================

def get_current_user(request: Request):

    token = request.cookies.get("token")

    if not token:
        return None

    username = verify_token(token)

    return username

# =========================================================
# HOME ROUTE
# =========================================================

@app.get("/")
async def home(request: Request):

    token = request.cookies.get("token")

    if token:

        username = verify_token(token)

        if username:
            return RedirectResponse("/chat")

    return RedirectResponse("/login")

# =========================================================
# LOGIN PAGE
# =========================================================

@app.get("/login")
async def login_page(request: Request):

    token = request.cookies.get("token")

    if token:

        username = verify_token(token)

        if username:
            return RedirectResponse("/chat")

    return FileResponse("static/login.html")

# =========================================================
# SIGNUP PAGE
# =========================================================

@app.get("/signup")
async def signup_page(request: Request):

    token = request.cookies.get("token")

    if token:

        username = verify_token(token)

        if username:
            return RedirectResponse("/chat")

    return FileResponse("static/signup.html")

# =========================================================
# CHAT PAGE
# =========================================================

@app.get("/chat")
async def chat_page(request: Request):

    token = request.cookies.get("token")

    if not token:
        return RedirectResponse("/login")

    username = verify_token(token)

    if not username:
        return RedirectResponse("/login")

    html = open(
        "static/index.html",
        "r",
        encoding="utf-8"
    ).read()

    html = html.replace(
        "__USERNAME__",
        username
    )

    return HTMLResponse(content=html)

# =========================================================
# SIGNUP API
# =========================================================

@app.post("/signup")
async def signup(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):

    existing_user = db.query(User).filter(
        User.username == username
    ).first()

    if existing_user:

        return RedirectResponse(
            url="/login?error=user_exists",
            status_code=302,
        )

    hashed_password = pwd_context.hash(password)

    new_user = User(
        username=username,
        password=hashed_password,
    )

    db.add(new_user)

    db.commit()

    token = create_token(username)

    response = RedirectResponse(
        url="/chat",
        status_code=302,
    )

    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
    )

    return response

# =========================================================
# LOGIN API
# =========================================================

@app.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):

    user = db.query(User).filter(
        User.username == username
    ).first()

    if not user:

        return RedirectResponse(
            url="/login?error=invalid_credentials",
            status_code=302,
        )

    valid_password = pwd_context.verify(
        password,
        user.password,
    )

    if not valid_password:

        return RedirectResponse(
            url="/login?error=invalid_credentials",
            status_code=302,
        )

    token = create_token(username)

    response = RedirectResponse(
        url="/chat",
        status_code=302,
    )

    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
    )

    return response

# =========================================================
# LOGOUT
# =========================================================

@app.get("/logout")
async def logout():

    response = RedirectResponse(
        url="/login",
        status_code=302,
    )

    response.delete_cookie("token")

    return response

# =========================================================
# CREATE CHAT
# =========================================================

@app.post("/create-chat")
async def create_chat(
    request: Request,
    db: Session = Depends(get_db),
):

    username = get_current_user(request)

    if not username:

        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )

    user = db.query(User).filter(
        User.username == username
    ).first()

    chat_id = str(
        datetime.datetime.utcnow().timestamp()
    )

    new_chat = Chat(
        user_id=user.id,
        chat_id=chat_id,
        title="New Chat",
    )

    db.add(new_chat)

    db.commit()

    return {
        "chat_id": chat_id,
        "title": "New Chat",
    }

# =========================================================
# GET USER CHATS
# =========================================================

@app.get("/get-chats")
async def get_chats(
    request: Request,
    db: Session = Depends(get_db),
):

    username = get_current_user(request)

    if not username:

        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )

    user = db.query(User).filter(
        User.username == username
    ).first()

    chats = db.query(Chat).filter(
        Chat.user_id == user.id
    ).all()

    result = []

    for chat in chats:

        result.append({

            "chat_id": chat.chat_id,
            "title": chat.title,

        })

    return result

# =========================================================
# GET CHAT MESSAGES
# =========================================================

@app.get("/get-messages/{chat_id}")
async def get_messages(
    chat_id: str,
    request: Request,
    db: Session = Depends(get_db),
):

    username = get_current_user(request)

    if not username:

        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )

    messages = db.query(Message).filter(
        Message.chat_id == chat_id
    ).all()

    result = []

    for msg in messages:

        result.append({

            "role": msg.role,
            "content": msg.content,

        })

    return result

# =========================================================
# DELETE CHAT
# =========================================================

@app.delete("/delete-chat/{chat_id}")
async def delete_chat(
    chat_id: str,
    request: Request,
    db: Session = Depends(get_db),
):

    username = get_current_user(request)

    if not username:

        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )

    db.query(Message).filter(
        Message.chat_id == chat_id
    ).delete()

    db.query(Chat).filter(
        Chat.chat_id == chat_id
    ).delete()

    db.commit()

    return {
        "success": True,
    }

# =========================================================
# WEBSOCKET CHAT
# =========================================================

@app.websocket("/ws/{user_id}/{chat_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    chat_id: str,
):

    await websocket.accept()

    print(f"Connected: {user_id}")

    session_id = chat_id

    try:

        await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )

        print(f"Session Created: {session_id}")

    except Exception as e:

        print(f"Session Exists: {e}")

    try:

        while True:

            user_text = await websocket.receive_text()

            print(f"User: {user_text}")

            await websocket.send_text(
                json.dumps({
                    "type": "start"
                })
            )

            message = types.Content(
                role="user",
                parts=[
                    types.Part(text=user_text)
                ]
            )

            full_response = ""

            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message,
            ):

                if not event.content:
                    continue

                for part in event.content.parts:

                    if (
                        hasattr(part, "text")
                        and part.text
                    ):

                        chunk = part.text

                        full_response += chunk

                        await websocket.send_text(
                            json.dumps({
                                "type": "chunk",
                                "content": chunk,
                            })
                        )

            await websocket.send_text(
                json.dumps({
                    "type": "done",
                    "content": full_response,
                })
            )

            # SAVE USER MESSAGE

            db = SessionLocal()

            user_message = Message(
                chat_id=session_id,
                role="user",
                content=user_text,
            )

            db.add(user_message)

            # SAVE BOT MESSAGE

            bot_message = Message(
                chat_id=session_id,
                role="assistant",
                content=full_response,
            )

            db.add(bot_message)

            db.commit()

            db.close()

            print("Response Complete")

    except WebSocketDisconnect:

        print(f"Disconnected: {user_id}")

    except Exception as e:

        print("WebSocket Error:", str(e))

        try:

            await websocket.send_text(
                json.dumps({
                    "type": "error",
                    "message": str(e),
                })
            )

        except:
            pass

        try:
            await websocket.close()

        except:
            pass