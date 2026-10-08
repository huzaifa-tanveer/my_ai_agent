import os

import re

import json

import uuid

import jwt

import bcrypt

import secrets

import hashlib

import hmac

import smtplib

import shutil
import io
import math
import time
import threading
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

import json

from typing import Optional
from collections import defaultdict, deque

from fastapi import Header, HTTPException

from fastapi.responses import StreamingResponse


from datetime import datetime, timedelta

from typing import Optional

from email.message import EmailMessage



import pandas as pd

from ddgs import DDGS



from fastapi import (

    FastAPI,
    Request,

    UploadFile,

    File,

    Header,

    HTTPException,

)



from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import FileResponse, StreamingResponse, JSONResponse



from pydantic import BaseModel



from openai import OpenAI

from pypdf import PdfReader

from dotenv import load_dotenv

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from xml.sax.saxutils import escape



from sqlalchemy import (

    create_engine,

    Column,

    String,

    Integer,

    Text,

    DateTime,

    Boolean,

    ForeignKey,

    UniqueConstraint,

    text,

)



from sqlalchemy.orm import (

    declarative_base,

    sessionmaker,

    relationship,

)





# =========================================================

# ENVIRONMENT

# =========================================================



load_dotenv(override=True)



OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

JWT_SECRET = os.getenv(

    "JWT_SECRET",

    "change-this-secret",

)

DATABASE_URL = os.getenv("DATABASE_URL")



OPENROUTER_MODEL = os.getenv(

    "OPENROUTER_MODEL",

    "openrouter/free",

)



RAG_EMBEDDING_MODEL = os.getenv(
    "RAG_EMBEDDING_MODEL",
    "nvidia/llama-nemotron-embed-vl-1b-v2:free",
)




# =========================================================
# SECURITY SETTINGS
# =========================================================

MAX_UPLOAD_BYTES = int(
    os.getenv(
        "MAX_UPLOAD_BYTES",
        str(10 * 1024 * 1024),
    )
)

MAX_REQUEST_BYTES = int(
    os.getenv(
        "MAX_REQUEST_BYTES",
        str(12 * 1024 * 1024),
    )
)

ALLOWED_ORIGINS = [
    item.strip()
    for item in os.getenv(
        "ALLOWED_ORIGINS",
        (
            "https://myaiagent-production-649a.up.railway.app,"
            "http://127.0.0.1:8000,"
            "http://localhost:8000,"
            "http://127.0.0.1:5500,"
            "http://localhost:5500"
        ),
    ).split(",")
    if item.strip()
]


ADMIN_USERNAMES = {
    item.strip().lower()
    for item in os.getenv("ADMIN_USERNAMES", "").split(",")
    if item.strip()
}



SMTP_HOST = os.getenv("SMTP_HOST")

SMTP_PORT = int(

    os.getenv(

        "SMTP_PORT",

        "587",

    )

)

SMTP_USER = os.getenv("SMTP_USER")

SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

SMTP_FROM = os.getenv(

    "SMTP_FROM",

    SMTP_USER or "",

)



SMTP_USE_TLS = (

    os.getenv(

        "SMTP_USE_TLS",

        "true",

    ).lower()

    == "true"

)



SMTP_USE_SSL = (

    os.getenv(

        "SMTP_USE_SSL",

        "false",

    ).lower()

    == "true"

)





if not OPENROUTER_API_KEY:

    raise RuntimeError(

        "OPENROUTER_API_KEY missing"

    )





if not DATABASE_URL:

    raise RuntimeError(

        "DATABASE_URL missing"

    )





if DATABASE_URL.startswith(

    "postgres://"

):

    DATABASE_URL = DATABASE_URL.replace(

        "postgres://",

        "postgresql://",

        1,

    )





# =========================================================

# APP

# =========================================================



app = FastAPI(

    title="My AI Agent"

)





app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=False,

    allow_methods=["*"],

    allow_headers=["*"],

)







# =========================================================
# SECURITY MIDDLEWARE
# =========================================================

_rate_limit_store = defaultdict(deque)
_rate_limit_lock = threading.Lock()


def _security_client_key(request):
    authorization = (
        request.headers.get(
            "authorization",
            "",
        )
    )

    if authorization.startswith("Bearer "):
        digest = hashlib.sha256(
            authorization.encode()
        ).hexdigest()

        return "token:" + digest[:24]

    forwarded = (
        request.headers.get(
            "x-forwarded-for",
            ""
        )
        .split(",")[0]
        .strip()
    )

    if forwarded:
        return "ip:" + forwarded

    if request.client:
        return (
            "ip:"
            + request.client.host
        )

    return "ip:unknown"


def _rate_limit_for_path(path):

    auth_paths = {
        "/login",
        "/register",
        "/forgot-password",
        "/reset-password",
        "/verify-email",
        "/resend-verification-code",
    }

    if path in auth_paths:
        return 10, 60

    if path in {
        "/chat",
        "/chat/stream",
        "/rag/ask",
        "/rag/reindex",
        "/url/ask",
    }:
        return 30, 60

    if path in {
        "/upload",
        "/rag/upload",
    }:
        return 10, 60

    return None


def _is_rate_limited(
    key,
    path,
):
    limit_config = (
        _rate_limit_for_path(
            path
        )
    )

    if not limit_config:
        return False

    limit, window_seconds = (
        limit_config
    )

    now = time.time()

    store_key = (
        key,
        path,
    )

    with _rate_limit_lock:

        events = (
            _rate_limit_store[
                store_key
            ]
        )

        cutoff = (
            now
            - window_seconds
        )

        while (
            events
            and events[0] < cutoff
        ):
            events.popleft()

        if len(events) >= limit:
            return True

        events.append(now)

    return False


@app.middleware("http")
async def security_middleware(
    request: Request,
    call_next,
):

    # -----------------------------
    # Request-size protection
    # -----------------------------

    content_length = (
        request.headers.get(
            "content-length"
        )
    )

    if content_length:

        try:
            request_size = int(
                content_length
            )

            if (
                request_size
                > MAX_REQUEST_BYTES
            ):
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail":
                            "Request is too large."
                    },
                )

        except ValueError:
            pass


    # -----------------------------
    # Basic rate limiting
    # -----------------------------

    client_key = (
        _security_client_key(
            request
        )
    )

    if _is_rate_limited(
        client_key,
        request.url.path,
    ):
        return JSONResponse(
            status_code=429,
            content={
                "detail": (
                    "Too many requests. "
                    "Please try again shortly."
                )
            },
            headers={
                "Retry-After": "60"
            },
        )


    response = await call_next(
        request
    )


    # -----------------------------
    # Security headers
    # -----------------------------

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "DENY"

    response.headers[
        "Referrer-Policy"
    ] = "strict-origin-when-cross-origin"

    response.headers[
        "Permissions-Policy"
    ] = (
        "camera=(), "
        "geolocation=(), "
        "payment=()"
    )

    response.headers[
        "Cross-Origin-Opener-Policy"
    ] = "same-origin"

    return response


# =========================================================

# OPENROUTER

# =========================================================



client = OpenAI(

    base_url=(

        "https://openrouter.ai/api/v1"

    ),

    api_key=OPENROUTER_API_KEY.strip(),

)





# =========================================================

# DATABASE

# =========================================================



engine = create_engine(

    DATABASE_URL,

    pool_pre_ping=True,

)



SessionLocal = sessionmaker(

    autocommit=False,

    autoflush=False,

    bind=engine,

)



Base = declarative_base()





# =========================================================

# DATABASE MODELS

# =========================================================



class User(Base):



    __tablename__ = "users"



    username = Column(

        String(100),

        primary_key=True,

    )



    email = Column(

        String(255),

        nullable=True,

    )



    email_verified = Column(

        Boolean,

        default=False,

        nullable=False,

    )



    password_hash = Column(

        Text,

        nullable=False,

    )



    created_at = Column(

        DateTime,

        default=datetime.utcnow,

        nullable=False,

    )



    chats = relationship(

        "Chat",

        back_populates="user",

        cascade="all, delete-orphan",

    )





class Chat(Base):



    __tablename__ = "chats"



    chat_id = Column(

        String(64),

        primary_key=True,

    )



    username = Column(

        String(100),

        ForeignKey(

            "users.username",

            ondelete="CASCADE",

        ),

        nullable=False,

        index=True,

    )



    title = Column(

        String(255),

        default="New Chat",

        nullable=False,

    )



    created_at = Column(

        DateTime,

        default=datetime.utcnow,

        nullable=False,

    )



    user = relationship(

        "User",

        back_populates="chats",

    )



    messages = relationship(

        "Message",

        back_populates="chat",

        cascade="all, delete-orphan",

        order_by="Message.id",

    )





class Message(Base):



    __tablename__ = "messages"



    id = Column(

        Integer,

        primary_key=True,

        autoincrement=True,

    )



    chat_id = Column(

        String(64),

        ForeignKey(

            "chats.chat_id",

            ondelete="CASCADE",

        ),

        nullable=False,

        index=True,

    )



    role = Column(

        String(30),

        nullable=False,

    )



    content = Column(

        Text,

        nullable=False,

    )



    created_at = Column(

        DateTime,

        default=datetime.utcnow,

        nullable=False,

    )



    chat = relationship(

        "Chat",

        back_populates="messages",

    )





class UserMemory(Base):



    __tablename__ = "user_memory"



    __table_args__ = (

        UniqueConstraint(

            "username",

            "memory_key",

            name="uq_user_memory_key",

        ),

    )



    id = Column(

        Integer,

        primary_key=True,

        autoincrement=True,

    )



    username = Column(

        String(100),

        ForeignKey(

            "users.username",

            ondelete="CASCADE",

        ),

        nullable=False,

        index=True,

    )



    memory_key = Column(

        String(255),

        nullable=False,

    )



    memory_value = Column(

        Text,

        nullable=False,

    )



    updated_at = Column(

        DateTime,

        default=datetime.utcnow,

        onupdate=datetime.utcnow,

        nullable=False,

    )





class PasswordResetCode(Base):



    __tablename__ = (

        "password_reset_codes"

    )



    id = Column(

        Integer,

        primary_key=True,

        autoincrement=True,

    )



    username = Column(

        String(100),

        ForeignKey(

            "users.username",

            ondelete="CASCADE",

        ),

        nullable=False,

        index=True,

    )



    code_hash = Column(

        String(64),

        nullable=False,

    )



    expires_at = Column(

        DateTime,

        nullable=False,

    )



    used = Column(

        Boolean,

        default=False,

        nullable=False,

    )



    created_at = Column(

        DateTime,

        default=datetime.utcnow,

        nullable=False,

    )





class EmailVerificationCode(Base):



    __tablename__ = (

        "email_verification_codes"

    )



    id = Column(

        Integer,

        primary_key=True,

        autoincrement=True,

    )



    username = Column(

        String(100),

        ForeignKey(

            "users.username",

            ondelete="CASCADE",

        ),

        nullable=False,

        index=True,

    )



    code_hash = Column(

        String(64),

        nullable=False,

    )



    expires_at = Column(

        DateTime,

        nullable=False,

    )



    used = Column(

        Boolean,

        default=False,

        nullable=False,

    )



    created_at = Column(

        DateTime,

        default=datetime.utcnow,

        nullable=False,

    )







class RagDocument(Base):

    __tablename__ = "rag_documents"

    document_id = Column(
        String(64),
        primary_key=True,
    )

    username = Column(
        String(100),
        ForeignKey(
            "users.username",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    filename = Column(
        String(255),
        nullable=False,
    )

    file_path = Column(
        Text,
        nullable=False,
    )

    file_type = Column(
        String(20),
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


class RagChunk(Base):

    __tablename__ = "rag_chunks"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    document_id = Column(
        String(64),
        ForeignKey(
            "rag_documents.document_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    username = Column(
        String(100),
        ForeignKey(
            "users.username",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    chunk_index = Column(
        Integer,
        nullable=False,
    )

    content = Column(
        Text,
        nullable=False,
    )

    embedding = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


Base.metadata.create_all(

    bind=engine

)





# =========================================================

# DATABASE MIGRATION

# =========================================================



with engine.begin() as connection:



    connection.execute(

        text(

            """

            ALTER TABLE users

            ADD COLUMN IF NOT EXISTS

            email VARCHAR(255)

            """

        )

    )



    connection.execute(

        text(

            """

            ALTER TABLE users

            ADD COLUMN IF NOT EXISTS

            email_verified BOOLEAN

            NOT NULL DEFAULT TRUE

            """

        )

    )



    connection.execute(

        text(

            """

            CREATE UNIQUE INDEX IF NOT EXISTS

            uq_users_email

            ON users (email)

            WHERE email IS NOT NULL

            """

        )

    )






    connection.execute(
        text(
            """
            ALTER TABLE rag_chunks
            ADD COLUMN IF NOT EXISTS
            embedding TEXT
            """
        )
    )


# =========================================================

# UPLOAD DIRECTORY

# =========================================================



UPLOAD_DIR = os.getenv(

    "UPLOAD_DIR",

    "uploads",

)



os.makedirs(

    UPLOAD_DIR,

    exist_ok=True,

)





# =========================================================

# HELPERS

# =========================================================



def normalize_email(

    email: str,

):



    return (

        email

        .strip()

        .lower()

    )





def valid_email(

    email: str,

):



    pattern = (

        r"^[^@\s]+@[^@\s]+\\.[^@\s]+$"

    )



    return bool(

        re.match(

            pattern,

            email,

        )

    )





def hash_reset_code(

    email,

    code,

):



    value = (

        f"{email}:{code}:{JWT_SECRET}"

    )



    return hashlib.sha256(

        value.encode()

    ).hexdigest()





def hash_verification_code(

    email,

    code,

):



    value = (

        f"verify:{email}:{code}:"

        f"{JWT_SECRET}"

    )



    return hashlib.sha256(

        value.encode()

    ).hexdigest()





# =========================================================

# EMAIL

# =========================================================



def send_email_message(

    email,

    subject,

    body,

):



    if not all([

        SMTP_HOST,

        SMTP_USER,

        SMTP_PASSWORD,

        SMTP_FROM,

    ]):



        raise RuntimeError(

            "Email service is not configured."

        )



    message = EmailMessage()



    message["Subject"] = subject

    message["From"] = SMTP_FROM

    message["To"] = email



    message.set_content(

        body

    )



    if SMTP_USE_SSL:



        with smtplib.SMTP_SSL(

            SMTP_HOST,

            SMTP_PORT,

            timeout=20,

        ) as smtp:



            smtp.login(

                SMTP_USER,

                SMTP_PASSWORD,

            )



            smtp.send_message(

                message

            )



    else:



        with smtplib.SMTP(

            SMTP_HOST,

            SMTP_PORT,

            timeout=20,

        ) as smtp:



            smtp.ehlo()



            if SMTP_USE_TLS:



                smtp.starttls()

                smtp.ehlo()



            smtp.login(

                SMTP_USER,

                SMTP_PASSWORD,

            )



            smtp.send_message(

                message

            )





def send_reset_email(

    email,

    code,

):



    send_email_message(

        email,

        (

            "My AI Agent - "

            "Password Reset Code"

        ),

        f"""

Hello,



Your password reset code is:



{code}



This code will expire in 10 minutes.



If you did not request a password reset,

you can ignore this email.



My AI Agent

""",

    )





def send_verification_email(

    email,

    code,

):



    send_email_message(

        email,

        (

            "My AI Agent - "

            "Verify Your Email"

        ),

        f"""

Hello,



Welcome to My AI Agent.



Your email verification code is:



{code}



This code will expire in 10 minutes.



If you did not create this account,

you can ignore this email.



My AI Agent

""",

    )





# =========================================================

# JWT

# =========================================================



def create_token(

    username,

):



    payload = {

        "username": username,

        "exp": (

            datetime.utcnow()

            + timedelta(days=7)

        ),

    }



    return jwt.encode(

        payload,

        JWT_SECRET,

        algorithm="HS256",

    )





def get_current_user(

    authorization: Optional[str],

):



    if not authorization:



        raise HTTPException(

            status_code=401,

            detail="Login required",

        )



    if not authorization.startswith(

        "Bearer "

    ):



        raise HTTPException(

            status_code=401,

            detail=(

                "Invalid authentication"

            ),

        )



    token = authorization.split(

        " ",

        1,

    )[1]



    try:



        payload = jwt.decode(

            token,

            JWT_SECRET,

            algorithms=["HS256"],

        )



        username = (

            payload["username"]

        )



    except Exception:



        raise HTTPException(

            status_code=401,

            detail=(

                "Invalid or expired token"

            ),

        )



    db = SessionLocal()



    try:



        user = (

            db.query(User)

            .filter(

                User.username

                == username

            )

            .first()

        )



        if not user:



            raise HTTPException(

                status_code=401,

                detail=(

                    "User account no "

                    "longer exists"

                ),

            )



        return username



    finally:



        db.close()






# =========================================================
# ADMIN HELPERS
# =========================================================

def is_admin_username(username: str) -> bool:
    return bool(
        username
        and username.strip().lower() in ADMIN_USERNAMES
    )


def require_admin(
    authorization: Optional[str],
):
    username = get_current_user(authorization)

    if not is_admin_username(username):
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    return username


# =========================================================

# REQUEST MODELS

# =========================================================



class RegisterRequest(BaseModel):

    username: str

    email: str

    password: str





class LoginRequest(BaseModel):

    username: str

    password: str





class ForgotPasswordRequest(BaseModel):

    email: str





class ResetPasswordRequest(BaseModel):

    email: str

    code: str

    new_password: str





class VerifyEmailRequest(BaseModel):

    email: str

    code: str





class ResendVerificationRequest(

    BaseModel

):

    email: str





class ChangePasswordRequest(

    BaseModel

):

    current_password: str

    new_password: str





class DeleteAccountRequest(

    BaseModel

):

    password: str





class CreateChatRequest(BaseModel):

    title: Optional[str] = "New Chat"





class RenameChatRequest(BaseModel):

    title: str





class MemoryRequest(BaseModel):

    key: str

    value: str





class ChatRequest(BaseModel):

    chat_id: str

    message: str

    file_path: Optional[str] = None


class UrlReaderRequest(BaseModel):

    url: str

    question: Optional[str] = None


class RagAskRequest(BaseModel):
    question: str
    document_id: Optional[str] = None
    top_k: int = 5





# =========================================================

# REGISTER

# =========================================================



@app.post("/register")

def register(

    data: RegisterRequest,

):



    username = (

        data.username

        .strip()

        .lower()

    )



    email = normalize_email(

        data.email

    )



    if len(username) < 3:



        raise HTTPException(

            status_code=400,

            detail="Username too short",

        )



    if not valid_email(email):



        raise HTTPException(

            status_code=400,

            detail=(

                "Invalid email address"

            ),

        )



    if len(data.password) < 6:



        raise HTTPException(

            status_code=400,

            detail=(

                "Password must be at least "

                "6 characters"

            ),

        )



    db = SessionLocal()



    try:



        if (

            db.query(User)

            .filter(

                User.username

                == username

            )

            .first()

        ):



            raise HTTPException(

                status_code=400,

                detail=(

                    "Username already exists"

                ),

            )



        if (

            db.query(User)

            .filter(

                User.email

                == email

            )

            .first()

        ):



            raise HTTPException(

                status_code=400,

                detail=(

                    "Email already registered"

                ),

            )



        hashed_password = (

            bcrypt.hashpw(

                data.password.encode(),

                bcrypt.gensalt(),

            )

            .decode()

        )



        user = User(

            username=username,

            email=email,

            password_hash=hashed_password,

            email_verified=False,

        )



        db.add(user)

        db.flush()



        code = str(

            secrets.randbelow(

                900000

            )

            + 100000

        )



        verification = (

            EmailVerificationCode(

                username=username,

                code_hash=(

                    hash_verification_code(

                        email,

                        code,

                    )

                ),

                expires_at=(

                    datetime.utcnow()

                    + timedelta(

                        minutes=10

                    )

                ),

                used=False,

            )

        )



        db.add(

            verification

        )



        try:



            send_verification_email(

                email,

                code,

            )



        except Exception as error:



            db.rollback()



            print(

                "VERIFICATION EMAIL ERROR:",

                str(error),

            )



            raise HTTPException(

                status_code=500,

                detail=(

                    "Could not send "

                    "verification email."

                ),

            )



        db.commit()



        return {

            "message": (

                "Account created. "

                "Please verify your email."

            ),

            "email": email,

            "verification_required": True,

        }



    finally:



        db.close()





# =========================================================

# VERIFY EMAIL

# =========================================================



@app.post("/verify-email")

def verify_email(

    data: VerifyEmailRequest,

):



    email = normalize_email(

        data.email

    )



    code = data.code.strip()



    if (

        len(code) != 6

        or not code.isdigit()

    ):



        raise HTTPException(

            status_code=400,

            detail=(

                "Invalid verification code"

            ),

        )



    db = SessionLocal()



    try:



        user = (

            db.query(User)

            .filter(

                User.email == email

            )

            .first()

        )



        if not user:



            raise HTTPException(

                status_code=400,

                detail=(

                    "Invalid or expired "

                    "verification code"

                ),

            )



        if user.email_verified:



            return {

                "message":

                    "Email already verified.",

                "token":

                    create_token(

                        user.username

                    ),

                "username":

                    user.username,

            }



        verification = (

            db.query(

                EmailVerificationCode

            )

            .filter(

                EmailVerificationCode

                .username

                == user.username,



                EmailVerificationCode

                .used

                == False,

            )

            .order_by(

                EmailVerificationCode

                .created_at

                .desc()

            )

            .first()

        )



        if not verification:



            raise HTTPException(

                status_code=400,

                detail=(

                    "Invalid or expired "

                    "verification code"

                ),

            )



        if (

            verification.expires_at

            < datetime.utcnow()

        ):



            verification.used = True



            db.commit()



            raise HTTPException(

                status_code=400,

                detail=(

                    "Verification code "

                    "has expired"

                ),

            )



        expected_hash = (

            hash_verification_code(

                email,

                code,

            )

        )



        if not hmac.compare_digest(

            verification.code_hash,

            expected_hash,

        ):



            raise HTTPException(

                status_code=400,

                detail=(

                    "Invalid or expired "

                    "verification code"

                ),

            )



        user.email_verified = True

        verification.used = True



        db.commit()



        return {

            "message":

                (

                    "Email verified "

                    "successfully."

                ),



            "token":

                create_token(

                    user.username

                ),



            "username":

                user.username,

        }



    finally:



        db.close()





# =========================================================

# RESEND VERIFICATION

# =========================================================



@app.post(

    "/resend-verification-code"

)

def resend_verification_code(

    data: ResendVerificationRequest,

):



    email = normalize_email(

        data.email

    )



    db = SessionLocal()



    try:



        user = (

            db.query(User)

            .filter(

                User.email == email

            )

            .first()

        )



        if not user:



            return {

                "message": (

                    "If the account exists, "

                    "a verification code "

                    "has been sent."

                )

            }



        if user.email_verified:



            return {

                "message":

                    "Email is already verified."

            }



        old_codes = (

            db.query(

                EmailVerificationCode

            )

            .filter(

                EmailVerificationCode

                .username

                == user.username,



                EmailVerificationCode

                .used

                == False,

            )

            .all()

        )



        for item in old_codes:

            item.used = True



        code = str(

            secrets.randbelow(

                900000

            )

            + 100000

        )



        verification = (

            EmailVerificationCode(

                username=user.username,

                code_hash=(

                    hash_verification_code(

                        email,

                        code,

                    )

                ),

                expires_at=(

                    datetime.utcnow()

                    + timedelta(

                        minutes=10

                    )

                ),

                used=False,

            )

        )



        db.add(

            verification

        )



        send_verification_email(

            email,

            code,

        )



        db.commit()



        return {

            "message":

                (

                    "Verification code "

                    "sent successfully."

                )

        }



    finally:



        db.close()





# =========================================================

# LOGIN

# =========================================================



@app.post("/login")

def login(

    data: LoginRequest,

):



    username = (

        data.username

        .strip()

        .lower()

    )



    db = SessionLocal()



    try:



        user = (

            db.query(User)

            .filter(

                User.username

                == username

            )

            .first()

        )



        if not user:



            raise HTTPException(

                status_code=401,

                detail=(

                    "Invalid username "

                    "or password"

                ),

            )



        valid = bcrypt.checkpw(

            data.password.encode(),

            user.password_hash.encode(),

        )



        if not valid:



            raise HTTPException(

                status_code=401,

                detail=(

                    "Invalid username "

                    "or password"

                ),

            )



        if not user.email_verified:



            raise HTTPException(

                status_code=403,

                detail=(

                    "Please verify your "

                    "email first."

                ),

            )



        return {

            "token":

                create_token(

                    username

                ),

            "username":

                username,

        }



    finally:



        db.close()





# =========================================================

# PROFILE

# =========================================================



@app.get("/profile")

def get_profile(

    authorization: Optional[str]

    = Header(None),

):



    username = get_current_user(

        authorization

    )



    db = SessionLocal()



    try:



        user = (

            db.query(User)

            .filter(

                User.username

                == username

            )

            .first()

        )



        return {

            "username":

                user.username,



            "email":

                user.email,



            "email_verified":

                user.email_verified,



            "created_at":

                (

                    user.created_at

                    .isoformat()

                    if user.created_at

                    else None

                ),

            "is_admin":
                is_admin_username(
                    user.username
                ),

        }



    finally:



        db.close()





# =========================================================
# MEMORY MANAGEMENT
# =========================================================


@app.get("/memories")
def list_memories(
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(authorization)
    db = SessionLocal()

    try:
        items = (
            db.query(UserMemory)
            .filter(UserMemory.username == username)
            .order_by(UserMemory.updated_at.desc())
            .all()
        )

        return {
            "memories": [
                {
                    "id": item.id,
                    "key": item.memory_key,
                    "value": item.memory_value,
                    "updated_at": (
                        item.updated_at.isoformat()
                        if item.updated_at
                        else None
                    ),
                }
                for item in items
            ]
        }

    finally:
        db.close()


@app.post("/memories")
def create_memory(
    data: MemoryRequest,
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(authorization)
    key = data.key.strip()
    value = data.value.strip()

    if not key or not value:
        raise HTTPException(status_code=400, detail="Memory key and value are required.")

    if len(key) > 255:
        raise HTTPException(status_code=400, detail="Memory key must be 255 characters or less.")

    db = SessionLocal()
    try:
        item = (
            db.query(UserMemory)
            .filter(UserMemory.username == username, UserMemory.memory_key == key)
            .first()
        )
        if item:
            item.memory_value = value
            item.updated_at = datetime.utcnow()
        else:
            item = UserMemory(username=username, memory_key=key, memory_value=value)
            db.add(item)

        db.commit()
        db.refresh(item)
        return {
            "message": "Memory saved successfully.",
            "memory": {
                "id": item.id,
                "key": item.memory_key,
                "value": item.memory_value,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            },
        }
    finally:
        db.close()


@app.put("/memories/{memory_id}")
def update_memory(
    memory_id: int,
    data: MemoryRequest,
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(authorization)
    key = data.key.strip()
    value = data.value.strip()

    if not key or not value:
        raise HTTPException(status_code=400, detail="Memory key and value are required.")
    if len(key) > 255:
        raise HTTPException(status_code=400, detail="Memory key must be 255 characters or less.")

    db = SessionLocal()
    try:
        item = (
            db.query(UserMemory)
            .filter(UserMemory.id == memory_id, UserMemory.username == username)
            .first()
        )
        if not item:
            raise HTTPException(status_code=404, detail="Memory not found.")

        duplicate = (
            db.query(UserMemory)
            .filter(
                UserMemory.username == username,
                UserMemory.memory_key == key,
                UserMemory.id != memory_id,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="A memory with this key already exists.")

        item.memory_key = key
        item.memory_value = value
        item.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(item)
        return {
            "message": "Memory updated successfully.",
            "memory": {
                "id": item.id,
                "key": item.memory_key,
                "value": item.memory_value,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            },
        }
    finally:
        db.close()


@app.delete("/memories/{memory_id}")
def delete_memory(
    memory_id: int,
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(authorization)
    db = SessionLocal()
    try:
        item = (
            db.query(UserMemory)
            .filter(UserMemory.id == memory_id, UserMemory.username == username)
            .first()
        )
        if not item:
            raise HTTPException(status_code=404, detail="Memory not found.")
        db.delete(item)
        db.commit()
        return {"message": "Memory deleted successfully."}
    finally:
        db.close()


# =========================================================

# CHANGE PASSWORD

# =========================================================



@app.post("/change-password")

def change_password(

    data: ChangePasswordRequest,

    authorization: Optional[str]

    = Header(None),

):



    username = get_current_user(

        authorization

    )



    if len(

        data.new_password

    ) < 6:



        raise HTTPException(

            status_code=400,

            detail=(

                "New password must be "

                "at least 6 characters"

            ),

        )



    db = SessionLocal()



    try:



        user = (

            db.query(User)

            .filter(

                User.username

                == username

            )

            .first()

        )



        valid = bcrypt.checkpw(

            data.current_password.encode(),

            user.password_hash.encode(),

        )



        if not valid:



            raise HTTPException(

                status_code=400,

                detail=(

                    "Current password "

                    "is incorrect"

                ),

            )



        if bcrypt.checkpw(

            data.new_password.encode(),

            user.password_hash.encode(),

        ):



            raise HTTPException(

                status_code=400,

                detail=(

                    "New password must be "

                    "different from current "

                    "password"

                ),

            )



        user.password_hash = (

            bcrypt.hashpw(

                data.new_password.encode(),

                bcrypt.gensalt(),

            )

            .decode()

        )



        db.commit()



        return {

            "message":

                (

                    "Password changed "

                    "successfully."

                )

        }



    finally:



        db.close()





# =========================================================

# DELETE ACCOUNT

# =========================================================



@app.delete("/account")

def delete_account(

    data: DeleteAccountRequest,

    authorization: Optional[str]

    = Header(None),

):



    username = get_current_user(

        authorization

    )



    db = SessionLocal()



    try:



        user = (

            db.query(User)

            .filter(

                User.username

                == username

            )

            .first()

        )



        valid = bcrypt.checkpw(

            data.password.encode(),

            user.password_hash.encode(),

        )



        if not valid:



            raise HTTPException(

                status_code=400,

                detail=(

                    "Password is incorrect"

                ),

            )



        db.query(

            PasswordResetCode

        ).filter(

            PasswordResetCode.username

            == username

        ).delete(

            synchronize_session=False

        )



        db.query(

            EmailVerificationCode

        ).filter(

            EmailVerificationCode.username

            == username

        ).delete(

            synchronize_session=False

        )



        db.query(

            UserMemory

        ).filter(

            UserMemory.username

            == username

        ).delete(

            synchronize_session=False

        )



        db.delete(

            user

        )



        db.commit()



        user_folder = os.path.join(

            UPLOAD_DIR,

            username,

        )



        if os.path.isdir(

            user_folder

        ):



            try:



                shutil.rmtree(

                    user_folder

                )



            except Exception as error:



                print(

                    "FILE CLEANUP ERROR:",

                    str(error),

                )



        return {

            "message":

                (

                    "Account deleted "

                    "successfully."

                )

        }



    finally:



        db.close()





# =========================================================

# FORGOT PASSWORD

# =========================================================



@app.post("/forgot-password")

def forgot_password(

    data: ForgotPasswordRequest,

):



    email = normalize_email(

        data.email

    )



    db = SessionLocal()



    try:



        user = (

            db.query(User)

            .filter(

                User.email == email

            )

            .first()

        )



        if not user:



            return {

                "message": (

                    "If this email is "

                    "registered, a reset "

                    "code has been sent."

                )

            }



        old_codes = (

            db.query(

                PasswordResetCode

            )

            .filter(

                PasswordResetCode.username

                == user.username,



                PasswordResetCode.used

                == False,

            )

            .all()

        )



        for item in old_codes:

            item.used = True



        code = str(

            secrets.randbelow(

                900000

            )

            + 100000

        )



        db.add(

            PasswordResetCode(

                username=user.username,

                code_hash=(

                    hash_reset_code(

                        email,

                        code,

                    )

                ),

                expires_at=(

                    datetime.utcnow()

                    + timedelta(

                        minutes=10

                    )

                ),

                used=False,

            )

        )



        send_reset_email(

            email,

            code,

        )



        db.commit()



        return {

            "message": (

                "If this email is "

                "registered, a reset "

                "code has been sent."

            )

        }



    finally:



        db.close()





# =========================================================

# RESET PASSWORD

# =========================================================



@app.post("/reset-password")

def reset_password(

    data: ResetPasswordRequest,

):



    email = normalize_email(

        data.email

    )



    code = data.code.strip()



    if (

        len(code) != 6

        or not code.isdigit()

    ):



        raise HTTPException(

            status_code=400,

            detail=(

                "Invalid reset code"

            ),

        )



    if len(

        data.new_password

    ) < 6:



        raise HTTPException(

            status_code=400,

            detail=(

                "Password must be at least "

                "6 characters"

            ),

        )



    db = SessionLocal()



    try:



        user = (

            db.query(User)

            .filter(

                User.email == email

            )

            .first()

        )



        if not user:



            raise HTTPException(

                status_code=400,

                detail=(

                    "Invalid or expired "

                    "reset code"

                ),

            )



        reset_record = (

            db.query(

                PasswordResetCode

            )

            .filter(

                PasswordResetCode.username

                == user.username,



                PasswordResetCode.used

                == False,

            )

            .order_by(

                PasswordResetCode

                .created_at

                .desc()

            )

            .first()

        )



        if not reset_record:



            raise HTTPException(

                status_code=400,

                detail=(

                    "Invalid or expired "

                    "reset code"

                ),

            )



        if (

            reset_record.expires_at

            < datetime.utcnow()

        ):



            reset_record.used = True

            db.commit()



            raise HTTPException(

                status_code=400,

                detail=(

                    "Reset code has expired"

                ),

            )



        expected_hash = (

            hash_reset_code(

                email,

                code,

            )

        )



        if not hmac.compare_digest(

            reset_record.code_hash,

            expected_hash,

        ):



            raise HTTPException(

                status_code=400,

                detail=(

                    "Invalid or expired "

                    "reset code"

                ),

            )



        user.password_hash = (

            bcrypt.hashpw(

                data.new_password.encode(),

                bcrypt.gensalt(),

            )

            .decode()

        )



        reset_record.used = True



        db.commit()



        return {

            "message": (

                "Password reset "

                "successfully. "

                "You can now login."

            )

        }



    finally:



        db.close()





# =========================================================

# TOOLS

# =========================================================



def add_numbers(

    a,

    b,

):



    return a + b





def get_current_datetime():



    return datetime.now().strftime(

        "%Y-%m-%d %H:%M:%S"

    )





def web_search(

    query,

):



    try:



        results = DDGS().text(

            query,

            max_results=5,

        )



        return [

            {

                "title":

                    item.get("title"),

                "url":

                    item.get("href"),

                "snippet":

                    item.get("body"),

            }

            for item in results

        ]



    except Exception as error:



        return (

            "Search error: "

            + str(error)

        )





# =========================================================

# MEMORY

# =========================================================



def save_user_memory(

    username,

    key,

    value,

):



    db = SessionLocal()



    try:



        item = (

            db.query(UserMemory)

            .filter(

                UserMemory.username

                == username,



                UserMemory.memory_key

                == key,

            )

            .first()

        )



        if item:



            item.memory_value = (

                str(value)

            )



            item.updated_at = (

                datetime.utcnow()

            )



        else:



            db.add(

                UserMemory(

                    username=username,

                    memory_key=key,

                    memory_value=(

                        str(value)

                    ),

                )

            )



        db.commit()



        return (

            f"Saved {key}: {value}"

        )



    finally:



        db.close()





def get_user_memory(

    username,

    key,

):



    db = SessionLocal()



    try:



        item = (

            db.query(UserMemory)

            .filter(

                UserMemory.username

                == username,



                UserMemory.memory_key

                == key,

            )

            .first()

        )



        if not item:



            return (

                "No saved information found."

            )



        return item.memory_value



    finally:



        db.close()





# =========================================================

# FILE READERS

# =========================================================





def validate_user_upload_path(
    username,
    file_path,
):
    if not username or not file_path:
        return None

    base_folder = os.path.abspath(
        os.path.join(
            UPLOAD_DIR,
            username,
        )
    )

    target_path = os.path.abspath(
        file_path
    )

    try:
        common = os.path.commonpath([
            base_folder,
            target_path,
        ])
    except ValueError:
        return None

    if common != base_folder:
        return None

    if not os.path.isfile(
        target_path
    ):
        return None

    return target_path



def read_text_file(

    file_path,

):



    if not os.path.exists(

        file_path

    ):

        return "File not found."



    try:



        with open(

            file_path,

            "r",

            encoding="utf-8",

        ) as file:



            content = file.read()



        return content[:20000]



    except Exception as error:



        return (

            "TXT error: "

            + str(error)

        )





def read_csv_file(

    file_path,

):



    if not os.path.exists(

        file_path

    ):

        return "File not found."



    try:



        dataframe = pd.read_csv(

            file_path

        )



        return {

            "rows":

                len(dataframe),



            "columns":

                dataframe

                .columns

                .tolist(),



            "preview":

                dataframe

                .head(15)

                .to_dict(

                    orient="records"

                ),

        }



    except Exception as error:



        return (

            "CSV error: "

            + str(error)

        )





def read_pdf_file(

    file_path,

):



    if not os.path.exists(

        file_path

    ):

        return "File not found."



    try:



        reader = PdfReader(

            file_path

        )



        content = ""



        for number, page in enumerate(

            reader.pages,

            start=1,

        ):



            page_text = (

                page.extract_text()

            )



            if page_text:



                content += (

                    f"\n--- Page "

                    f"{number} ---\n"

                    + page_text

                )



        if not content.strip():



            return (

                "No readable text found. "

                "PDF may be scanned."

            )



        return {

            "pages":

                len(reader.pages),



            "content":

                content[:30000],

        }



    except Exception as error:



        return (

            "PDF error: "

            + str(error)

        )





# =========================================================
# SAFE WEBSITE / URL READER
# =========================================================

URL_READER_MAX_BYTES = 2 * 1024 * 1024
URL_READER_MAX_TEXT = 60000


def _validate_public_url(url: str):
    value = (url or "").strip()
    parsed = urlparse(value)

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http:// and https:// URLs are supported.")

    if not parsed.hostname:
        raise ValueError("Invalid URL.")

    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not allowed.")

    hostname = parsed.hostname.strip().lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ValueError("Local or private network URLs are not allowed.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError("Could not resolve website hostname.")

    if not addresses:
        raise ValueError("Could not resolve website hostname.")

    for item in addresses:
        ip_text = item[4][0]
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            continue

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("Local or private network URLs are not allowed.")

    return value


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _ReadableHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.title_parts = []
        self.skip_depth = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        name = tag.lower()
        if name in {"script", "style", "noscript", "svg", "canvas", "template"}:
            self.skip_depth += 1
        if name == "title" and self.skip_depth == 0:
            self.in_title = True
        if name in {"p", "div", "section", "article", "main", "header", "footer", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        name = tag.lower()
        if name == "title":
            self.in_title = False
        if name in {"script", "style", "noscript", "svg", "canvas", "template"} and self.skip_depth:
            self.skip_depth -= 1
        if name in {"p", "div", "section", "article", "main", "header", "footer", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth:
            return
        clean = " ".join((data or "").split())
        if not clean:
            return
        if self.in_title:
            self.title_parts.append(clean)
        self.parts.append(clean + " ")

    def get_text(self):
        raw = "".join(self.parts)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return "\n".join(line for line in lines if line).strip()

    def get_title(self):
        return " ".join(self.title_parts).strip()


def read_webpage(url: str):
    safe_url = _validate_public_url(url)

    request = Request(
        safe_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MyAIAgent/1.0)",
            "Accept": "text/html,text/plain,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
        method="GET",
    )

    opener = build_opener(_SafeRedirectHandler())

    with opener.open(request, timeout=12) as response:
        final_url = response.geturl()
        _validate_public_url(final_url)

        content_type = (response.headers.get_content_type() or "").lower()
        if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
            raise ValueError("This URL is not a readable HTML/text webpage.")

        data = response.read(URL_READER_MAX_BYTES + 1)
        if len(data) > URL_READER_MAX_BYTES:
            raise ValueError("Webpage is too large to read safely.")

        charset = response.headers.get_content_charset() or "utf-8"
        try:
            decoded = data.decode(charset, errors="replace")
        except LookupError:
            decoded = data.decode("utf-8", errors="replace")

    if content_type == "text/plain":
        title = urlparse(final_url).hostname or "Webpage"
        text_content = "\n".join(
            " ".join(line.split())
            for line in decoded.splitlines()
            if line.strip()
        )
    else:
        parser = _ReadableHTMLParser()
        parser.feed(decoded)
        title = parser.get_title() or (urlparse(final_url).hostname or "Webpage")
        text_content = parser.get_text()

    if not text_content:
        raise ValueError("No readable text was found on this webpage.")

    return {
        "title": title[:300],
        "url": final_url,
        "content": text_content[:URL_READER_MAX_TEXT],
    }


# =========================================================

# TOOL SCHEMAS

# =========================================================



tools = [



    {

        "type": "function",

        "function": {

            "name":

                "add_numbers",



            "description":

                "Add two numbers.",



            "parameters": {

                "type":

                    "object",



                "properties": {

                    "a": {

                        "type": "number"

                    },

                    "b": {

                        "type": "number"

                    },

                },



                "required": [

                    "a",

                    "b",

                ],

            },

        },

    },



    {

        "type": "function",

        "function": {

            "name":

                "get_current_datetime",



            "description":

                (

                    "Get current "

                    "date and time."

                ),



            "parameters": {

                "type": "object",

                "properties": {},

            },

        },

    },



    {

        "type": "function",

        "function": {

            "name":

                "web_search",



            "description":

                (

                    "Search the web "

                    "for current information."

                ),



            "parameters": {

                "type":

                    "object",



                "properties": {

                    "query": {

                        "type": "string"

                    },

                },



                "required": [

                    "query"

                ],

            },

        },

    },



    {

        "type": "function",

        "function": {

            "name":

                "save_user_memory",



            "description":

                (

                    "Save information "

                    "the user explicitly "

                    "asks to remember."

                ),



            "parameters": {

                "type":

                    "object",



                "properties": {

                    "key": {

                        "type": "string"

                    },

                    "value": {

                        "type": "string"

                    },

                },



                "required": [

                    "key",

                    "value",

                ],

            },

        },

    },



    {

        "type": "function",

        "function": {

            "name":

                "get_user_memory",



            "description":

                (

                    "Get saved user "

                    "information."

                ),



            "parameters": {

                "type":

                    "object",



                "properties": {

                    "key": {

                        "type": "string"

                    },

                },



                "required": [

                    "key"

                ],

            },

        },

    },



    {

        "type": "function",

        "function": {

            "name":

                "read_text_file",



            "description":

                "Read TXT file.",



            "parameters": {

                "type":

                    "object",



                "properties": {

                    "file_path": {

                        "type": "string"

                    },

                },



                "required": [

                    "file_path"

                ],

            },

        },

    },



    {

        "type": "function",

        "function": {

            "name":

                "read_csv_file",



            "description":

                "Read CSV file.",



            "parameters": {

                "type":

                    "object",



                "properties": {

                    "file_path": {

                        "type": "string"

                    },

                },



                "required": [

                    "file_path"

                ],

            },

        },

    },



    {

        "type": "function",

        "function": {

            "name":

                "read_pdf_file",



            "description":

                "Read PDF file.",



            "parameters": {

                "type":

                    "object",



                "properties": {

                    "file_path": {

                        "type": "string"

                    },

                },



                "required": [

                    "file_path"

                ],

            },

        },

    },

]




# Website reader tool is appended separately to keep the main tool list simple.
tools.append({
    "type": "function",
    "function": {
        "name": "read_webpage",
        "description": "Read the visible text content of a public website URL supplied by the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"}
            },
            "required": ["url"]
        }
    }
})



SYSTEM_PROMPT = """

You are a helpful AI agent.



Capabilities:

- normal conversation

- calculator

- current date/time

- web search

- persistent memory

- TXT reading

- CSV reading

- PDF reading

- website URL reading



Use tools only when appropriate.



For ordinary questions, answer normally.



Use web_search when the user asks

for current or recent information.



Use save_user_memory only when the user

explicitly asks you to remember something.



When a file path is supplied,

use the appropriate file-reading tool.

When the user gives a public webpage URL and asks you to read, summarize, or analyze it, use read_webpage.



Always provide a useful text response.



Do not return an empty response.

"""





# =========================================================

# CHAT MANAGEMENT

# =========================================================



@app.post("/chats")

def create_chat(

    request: CreateChatRequest,

    authorization: Optional[str]

    = Header(None),

):



    username = get_current_user(

        authorization

    )



    db = SessionLocal()



    try:



        chat_id = uuid.uuid4().hex



        title = (

            request.title

            or "New Chat"

        ).strip()



        if not title:

            title = "New Chat"



        chat_object = Chat(

            chat_id=chat_id,

            username=username,

            title=title[:255],

        )



        db.add(

            chat_object

        )



        db.commit()



        return {

            "chat_id":

                chat_id,



            "title":

                chat_object.title,

        }



    finally:



        db.close()





@app.get("/chats")

def list_chats(

    authorization: Optional[str]

    = Header(None),

):



    username = get_current_user(

        authorization

    )



    db = SessionLocal()



    try:



        user_chats = (

            db.query(Chat)

            .filter(

                Chat.username

                == username

            )

            .order_by(

                Chat.created_at.desc()

            )

            .all()

        )



        return {

            "chats": [

                {

                    "chat_id":

                        item.chat_id,



                    "title":

                        item.title,

                }



                for item

                in user_chats

            ]

        }



    finally:



        db.close()





@app.get("/chats/{chat_id}")

def get_chat(

    chat_id: str,

    authorization: Optional[str]

    = Header(None),

):



    username = get_current_user(

        authorization

    )



    db = SessionLocal()



    try:



        chat_object = (

            db.query(Chat)

            .filter(

                Chat.chat_id

                == chat_id,



                Chat.username

                == username,

            )

            .first()

        )



        if not chat_object:



            raise HTTPException(

                status_code=404,

                detail="Chat not found",

            )



        return {

            "title":

                chat_object.title,



            "messages": [

                {

                    "role":

                        item.role,



                    "content":

                        item.content,

                }



                for item

                in chat_object.messages

            ],

        }



    finally:



        db.close()





# =========================================================
# CHAT EXPORT HELPERS
# =========================================================


def safe_export_filename(title: str):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (title or "chat").strip())
    cleaned = cleaned.strip("._-")
    return (cleaned or "chat")[:80]


def get_export_chat(db, username, chat_id):
    chat_object = (
        db.query(Chat)
        .filter(Chat.chat_id == chat_id, Chat.username == username)
        .first()
    )
    if not chat_object:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat_object


def build_chat_txt(chat_object):
    lines = [
        "My AI Agent - Chat Export",
        f"Title: {chat_object.title}",
        f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "=" * 60,
        "",
    ]
    for message in chat_object.messages:
        role = "You" if message.role == "user" else "AI Agent"
        lines.extend([f"{role}:", message.content or "", "", "-" * 60, ""])
    return "\n".join(lines)


def register_pdf_font():
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for font_path in candidates:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont("ChatExportFont", font_path))
                return "ChatExportFont"
            except Exception:
                pass
    return "Helvetica"


def pdf_safe_text(value, font_name):
    text_value = str(value or "")
    if font_name == "Helvetica":
        text_value = text_value.encode("latin-1", errors="replace").decode("latin-1")
    return escape(text_value).replace("\n", "<br/>")


def build_chat_pdf(chat_object):
    buffer = io.BytesIO()
    font_name = register_pdf_font()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=chat_object.title or "Chat Export",
        author="My AI Agent",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ChatTitle", parent=styles["Title"], fontName=font_name,
        fontSize=18, leading=22, alignment=TA_CENTER, spaceAfter=8,
    )
    meta_style = ParagraphStyle(
        "ChatMeta", parent=styles["Normal"], fontName=font_name,
        fontSize=9, leading=12, alignment=TA_CENTER, spaceAfter=14,
    )
    role_style = ParagraphStyle(
        "ChatRole", parent=styles["Heading3"], fontName=font_name,
        fontSize=11, leading=14, spaceBefore=8, spaceAfter=4,
    )
    message_style = ParagraphStyle(
        "ChatMessage", parent=styles["BodyText"], fontName=font_name,
        fontSize=10, leading=15, spaceAfter=8,
    )
    story = [
        Paragraph(pdf_safe_text(chat_object.title or "New Chat", font_name), title_style),
        Paragraph(
            pdf_safe_text(
                "Exported from My AI Agent on "
                + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                font_name,
            ),
            meta_style,
        ),
    ]
    if not chat_object.messages:
        story.append(Paragraph("This chat has no messages.", message_style))
    for message in chat_object.messages:
        role = "You" if message.role == "user" else "AI Agent"
        story.append(Paragraph(pdf_safe_text(role, font_name), role_style))
        story.append(Paragraph(pdf_safe_text(message.content or "", font_name), message_style))
        story.append(Spacer(1, 5))
    document.build(story)
    buffer.seek(0)
    return buffer


# =========================================================
# EXPORT CHAT AS TXT
# =========================================================

@app.get("/chats/{chat_id}/export/txt")
def export_chat_txt(
    chat_id: str,
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(authorization)
    db = SessionLocal()
    try:
        chat_object = get_export_chat(db, username, chat_id)
        content = build_chat_txt(chat_object)
        filename = safe_export_filename(chat_object.title) + ".txt"
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        db.close()


# =========================================================
# EXPORT CHAT AS PDF
# =========================================================

@app.get("/chats/{chat_id}/export/pdf")
def export_chat_pdf(
    chat_id: str,
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(authorization)
    db = SessionLocal()
    try:
        chat_object = get_export_chat(db, username, chat_id)
        pdf_buffer = build_chat_pdf(chat_object)
        filename = safe_export_filename(chat_object.title) + ".pdf"
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        db.close()


# =========================================================

# RENAME CHAT

# =========================================================



@app.patch(

    "/chats/{chat_id}/title"

)

def rename_chat(

    chat_id: str,

    request: RenameChatRequest,

    authorization: Optional[str]

    = Header(None),

):



    username = get_current_user(

        authorization

    )



    new_title = (

        request.title

        .strip()

    )



    if not new_title:



        raise HTTPException(

            status_code=400,

            detail=(

                "Chat title cannot be empty"

            ),

        )



    if len(new_title) > 100:



        raise HTTPException(

            status_code=400,

            detail=(

                "Chat title must be "

                "100 characters or less"

            ),

        )



    db = SessionLocal()



    try:



        chat_object = (

            db.query(Chat)

            .filter(

                Chat.chat_id

                == chat_id,



                Chat.username

                == username,

            )

            .first()

        )



        if not chat_object:



            raise HTTPException(

                status_code=404,

                detail="Chat not found",

            )



        chat_object.title = (

            new_title

        )



        db.commit()



        return {

            "success":

                True,



            "chat_id":

                chat_object.chat_id,



            "title":

                chat_object.title,

        }



    finally:



        db.close()





@app.delete(

    "/chats/{chat_id}"

)

def delete_chat(

    chat_id: str,

    authorization: Optional[str]

    = Header(None),

):



    username = get_current_user(

        authorization

    )



    db = SessionLocal()



    try:



        chat_object = (

            db.query(Chat)

            .filter(

                Chat.chat_id

                == chat_id,



                Chat.username

                == username,

            )

            .first()

        )



        if not chat_object:



            raise HTTPException(

                status_code=404,

                detail="Chat not found",

            )



        db.delete(

            chat_object

        )



        db.commit()



        return {

            "success":

                True

        }



    finally:



        db.close()





# =========================================================

# FILE UPLOAD

# =========================================================



@app.post("/upload")

async def upload_file(

    file: UploadFile = File(...),

    authorization: Optional[str]

    = Header(None),

):



    username = get_current_user(

        authorization

    )



    original_name = (

        file.filename

        or "file"

    )



    extension = (

        os.path.splitext(

            original_name

        )[1]

        .lower()

    )



    if extension not in [

        ".txt",

        ".csv",

        ".pdf",

    ]:



        raise HTTPException(

            status_code=400,

            detail=(

                "Only TXT, CSV "

                "and PDF supported."

            ),

        )



    user_folder = os.path.join(

        UPLOAD_DIR,

        username,

    )



    os.makedirs(

        user_folder,

        exist_ok=True,

    )



    filename = (

        f"{uuid.uuid4().hex}_"

        + os.path.basename(

            original_name

        )

    )



    path = os.path.join(

        user_folder,

        filename,

    )



    content = await file.read()



    with open(

        path,

        "wb",

    ) as output:



        output.write(

            content

        )



    return {

        "success":

            True,



        "filename":

            original_name,



        "file_path":

            os.path.abspath(

                path

            ),

    }





# =========================================================

# TOOL EXECUTION

# =========================================================



def execute_tool(

    username,

    name,

    arguments,

):



    if name == "add_numbers":



        return add_numbers(

            arguments["a"],

            arguments["b"],

        )



    if name == (

        "get_current_datetime"

    ):



        return (

            get_current_datetime()

        )



    if name == "web_search":



        return web_search(

            arguments["query"]

        )



    if name == (

        "save_user_memory"

    ):



        return save_user_memory(

            username,

            arguments["key"],

            arguments["value"],

        )



    if name == (

        "get_user_memory"

    ):



        return get_user_memory(

            username,

            arguments["key"],

        )



    if name == (

        "read_text_file"

    ):



        return read_text_file(

            arguments["file_path"]

        )



    if name == (

        "read_csv_file"

    ):



        return read_csv_file(

            arguments["file_path"]

        )



    if name == (

        "read_pdf_file"

    ):



        return read_pdf_file(

            arguments["file_path"]

        )



    if name == "read_webpage":

        return read_webpage(

            arguments["url"]

        )


    return "Unknown tool"





# =========================================================
# SMART LONG-TERM MEMORY
# =========================================================

SMART_MEMORY_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
    "be", "been", "being", "to", "of", "in", "on", "for", "with", "at",
    "by", "from", "as", "it", "this", "that", "these", "those", "i", "me",
    "my", "mine", "you", "your", "yours", "we", "our", "ours", "they",
    "their", "what", "which", "who", "how", "when", "where", "why", "do",
    "does", "did", "can", "could", "would", "should", "will", "just",
    "about", "tell", "please", "give", "show", "want", "need", "ka", "ki",
    "ke", "hai", "hain", "tha", "thi", "ho", "aur", "se", "ko", "mera",
    "meri", "mere", "mujhe", "kya", "kon", "kab", "kahan", "kyun",
}


def _memory_tokens(value):
    return {
        token
        for token in re.findall(r"[A-Za-z0-9_\u0600-\u06FF]+", (value or "").lower())
        if len(token) >= 3 and token not in SMART_MEMORY_STOPWORDS
    }


def _memory_score(query_tokens, text):
    text_tokens = _memory_tokens(text)
    if not query_tokens or not text_tokens:
        return 0

    overlap = len(query_tokens & text_tokens)
    if overlap == 0:
        return 0

    return overlap * 10 + int((overlap / max(len(query_tokens), 1)) * 10)


def get_smart_memory_context(username, query, exclude_chat_id=None):
    """Return small, relevant cross-chat context for this user only."""
    db = SessionLocal()

    try:
        query_tokens = _memory_tokens(query)
        sections = []

        explicit_items = (
            db.query(UserMemory)
            .filter(UserMemory.username == username)
            .order_by(UserMemory.updated_at.desc())
            .limit(20)
            .all()
        )

        explicit_lines = []
        for item in explicit_items:
            combined = f"{item.memory_key}: {item.memory_value}"
            score = _memory_score(query_tokens, combined)
            if score > 0 or not query_tokens:
                explicit_lines.append((score, combined))

        explicit_lines.sort(key=lambda x: x[0], reverse=True)
        explicit_lines = [text for _, text in explicit_lines[:8]]

        if explicit_lines:
            sections.append(
                "Explicit saved memories:\n- " + "\n- ".join(explicit_lines)
            )

        history_query = (
            db.query(Message, Chat.title)
            .join(Chat, Message.chat_id == Chat.chat_id)
            .filter(
                Chat.username == username,
                Message.role.in_(["user", "assistant"]),
            )
        )

        if exclude_chat_id:
            history_query = history_query.filter(Chat.chat_id != exclude_chat_id)

        history_rows = (
            history_query
            .order_by(Message.id.desc())
            .limit(250)
            .all()
        )

        scored = []
        seen = set()

        for message, chat_title in history_rows:
            content = (message.content or "").strip()
            if not content:
                continue

            score = _memory_score(query_tokens, content)
            if score <= 0:
                continue

            signature = (message.role, content[:300])
            if signature in seen:
                continue
            seen.add(signature)

            label = "User" if message.role == "user" else "Assistant"
            snippet = content[:700]
            scored.append((score, f"[{chat_title or 'Past chat'}] {label}: {snippet}"))

        scored.sort(key=lambda x: x[0], reverse=True)
        history_lines = [text for _, text in scored[:6]]

        if history_lines:
            sections.append(
                "Relevant past conversation excerpts:\n- " + "\n- ".join(history_lines)
            )

        if not sections:
            return ""

        return "\n\n".join(sections)[:6000]

    finally:
        db.close()


def add_smart_memory_to_messages(model_messages, username, query, exclude_chat_id=None):
    memory_context = get_smart_memory_context(
        username=username,
        query=query,
        exclude_chat_id=exclude_chat_id,
    )

    if not memory_context:
        return model_messages

    memory_instruction = (
        "Potentially relevant long-term memory for this user is provided below. "
        "Use it only when it is actually relevant to the current request. "
        "Prefer the user's current message if it conflicts with older context. "
        "Do not claim certainty when the memory is ambiguous, and do not mention "
        "that a retrieval system was used unless the user asks.\n\n"
        + memory_context
    )

    return [
        model_messages[0],
        {"role": "system", "content": memory_instruction},
        *model_messages[1:],
    ]


# =========================================================

# AI

# =========================================================



def generate_ai_answer(

    username,

    model_messages,

):



    response = (

        client.chat

        .completions

        .create(

            model=OPENROUTER_MODEL,

            messages=model_messages,

            tools=tools,

            tool_choice="auto",

        )

    )



    assistant_message = (

        response

        .choices[0]

        .message

    )



    if not assistant_message.tool_calls:



        answer = (

            assistant_message.content

        )



        if answer:



            return answer



        fallback = (

            client.chat

            .completions

            .create(

                model=OPENROUTER_MODEL,



                messages=(

                    model_messages

                    + [

                        {

                            "role":

                                "system",



                            "content":

                                (

                                    "Answer the "

                                    "user's latest "

                                    "request directly "

                                    "with useful text."

                                ),

                        }

                    ]

                ),

            )

        )



        return (

            fallback

            .choices[0]

            .message

            .content



            or



            (

                "I could not generate "

                "a response. "

                "Please try again."

            )

        )



    model_messages.append(

        assistant_message

    )



    for tool_call in (

        assistant_message.tool_calls

    ):



        name = (

            tool_call

            .function

            .name

        )



        try:



            arguments = json.loads(

                tool_call

                .function

                .arguments

            )



        except Exception:



            arguments = {}



        try:



            result = execute_tool(

                username,

                name,

                arguments,

            )



        except Exception as error:



            result = (

                "Tool error: "

                + str(error)

            )



        model_messages.append(

            {

                "role":

                    "tool",



                "tool_call_id":

                    tool_call.id,



                "content":

                    json.dumps(

                        result,

                        ensure_ascii=False,

                        default=str,

                    ),

            }

        )



    final_response = (

        client.chat

        .completions

        .create(

            model=OPENROUTER_MODEL,

            messages=model_messages,

        )

    )



    return (

        final_response

        .choices[0]

        .message

        .content



        or



        (

            "I could not generate "

            "a response. "

            "Please try again."

        )

    )





# =========================================================

# CHAT

# =========================================================



@app.post("/chat")

def chat_endpoint(

    request: ChatRequest,

    authorization: Optional[str]

    = Header(None),

):



    username = get_current_user(

        authorization

    )



    db = SessionLocal()



    try:



        current_chat = (

            db.query(Chat)

            .filter(

                Chat.chat_id

                == request.chat_id,



                Chat.username

                == username,

            )

            .first()

        )



        if not current_chat:



            raise HTTPException(

                status_code=404,

                detail="Chat not found",

            )



        visible_message = (

            request.message.strip()

        )



        if not visible_message:



            visible_message = (

                "Please analyze "

                "the uploaded file."

            )



        model_message = (

            visible_message

        )



        if request.file_path:



            model_message += (

                "\n\nUploaded file path: "

                + request.file_path

                + "\nRead this file "

                "before answering."

            )



        previous_messages = (

            db.query(Message)

            .filter(

                Message.chat_id

                == request.chat_id

            )

            .order_by(

                Message.id.asc()

            )

            .all()

        )



        model_messages = [

            {

                "role":

                    "system",



                "content":

                    SYSTEM_PROMPT,

            }

        ]



        model_messages = add_smart_memory_to_messages(
            model_messages,
            username,
            visible_message,
            exclude_chat_id=request.chat_id,
        )

        for item in (

            previous_messages

        ):



            if item.role in [

                "user",

                "assistant",

            ]:



                model_messages.append(

                    {

                        "role":

                            item.role,



                        "content":

                            item.content,

                    }

                )



        model_messages.append(

            {

                "role":

                    "user",



                "content":

                    model_message,

            }

        )



        try:



            answer = (

                generate_ai_answer(

                    username,

                    model_messages,

                )

            )



        except Exception as error:



            error_text = str(

                error

            )



            print(

                "OPENROUTER ERROR:",

                error_text,

            )



            if (

                "429" in error_text

                or

                "Rate limit"

                in error_text

            ):



                answer = (

                    "Free API limit reached. "

                    "Please try again later."

                )



            elif (

                "401"

                in error_text

            ):



                answer = (

                    "OpenRouter "

                    "authentication failed."

                )



            else:



                answer = (

                    "AI error: "

                    + error_text

                )



        db.add(

            Message(

                chat_id=request.chat_id,

                role="user",

                content=visible_message,

            )

        )



        db.add(

            Message(

                chat_id=request.chat_id,

                role="assistant",

                content=answer,

            )

        )



        if (

            current_chat.title

            == "New Chat"

            and visible_message

        ):



            current_chat.title = (

                visible_message[:30]

            )



        db.commit()



        return {

            "answer":

                answer,



            "title":

                current_chat.title,

        }



    except HTTPException:



        raise



    except Exception as error:



        db.rollback()



        print(

            "CHAT ERROR:",

            str(error),

        )



        return {

            "answer":

                (

                    "Server error: "

                    + str(error)

                )

        }



    finally:



        db.close()





# =========================================================

# REGENERATE RESPONSE

# =========================================================

@app.post("/chats/{chat_id}/regenerate")
def regenerate_response(
    chat_id: str,
    authorization: Optional[str] = Header(None),
):

    username = get_current_user(
        authorization
    )

    db = SessionLocal()

    try:

        current_chat = (
            db.query(Chat)
            .filter(
                Chat.chat_id == chat_id,
                Chat.username == username,
            )
            .first()
        )

        if not current_chat:
            raise HTTPException(
                status_code=404,
                detail="Chat not found",
            )

        messages = (
            db.query(Message)
            .filter(
                Message.chat_id == chat_id
            )
            .order_by(
                Message.id.asc()
            )
            .all()
        )

        if not messages:
            raise HTTPException(
                status_code=400,
                detail="There is no message to regenerate.",
            )

        last_user_index = None

        for index in range(
            len(messages) - 1,
            -1,
            -1,
        ):
            if messages[index].role == "user":
                last_user_index = index
                break

        if last_user_index is None:
            raise HTTPException(
                status_code=400,
                detail="No user message found to regenerate from.",
            )

        last_user_message = (
            messages[last_user_index]
        )

        model_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        model_messages = add_smart_memory_to_messages(
            model_messages,
            username,
            last_user_message.content,
            exclude_chat_id=chat_id,
        )

        for item in messages[:last_user_index + 1]:
            if item.role in [
                "user",
                "assistant",
            ]:
                model_messages.append(
                    {
                        "role": item.role,
                        "content": item.content,
                    }
                )

        try:
            answer = generate_ai_answer(
                username,
                model_messages,
            )

        except Exception as error:
            error_text = str(error)

            print(
                "REGENERATE ERROR:",
                error_text,
            )

            if (
                "429" in error_text
                or "Rate limit" in error_text
            ):
                raise HTTPException(
                    status_code=429,
                    detail=(
                        "Free API limit reached. "
                        "Please try again later."
                    ),
                )

            if "401" in error_text:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "OpenRouter authentication failed."
                    ),
                )

            raise HTTPException(
                status_code=502,
                detail=(
                    "AI error: "
                    + error_text
                ),
            )

        # Replace assistant output for the latest user turn.
        for item in messages[last_user_index + 1:]:
            if item.role == "assistant":
                db.delete(item)

        new_message = Message(
            chat_id=chat_id,
            role="assistant",
            content=answer,
        )

        db.add(new_message)
        db.commit()

        return {
            "answer": answer,
            "chat_id": chat_id,
            "user_message": last_user_message.content,
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()

        print(
            "REGENERATE SERVER ERROR:",
            str(error),
        )

        raise HTTPException(
            status_code=500,
            detail="Could not regenerate response.",
        )

    finally:
        db.close()


# =========================================================
# RAG - DOCUMENT RETRIEVAL
# =========================================================

def extract_rag_text(file_path, extension):
    extension = extension.lower()

    if extension == ".txt":
        with open(
            file_path,
            "r",
            encoding="utf-8",
            errors="replace",
        ) as file:
            return file.read()

    if extension == ".csv":
        dataframe = pd.read_csv(file_path)
        return dataframe.to_csv(index=False)

    if extension == ".pdf":
        reader = PdfReader(file_path)
        pages = []

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            page_text = page.extract_text() or ""

            if page_text.strip():
                pages.append(
                    f"[Page {page_number}]\n{page_text}"
                )

        return "\n\n".join(pages)

    raise ValueError("Unsupported RAG file type")


def chunk_rag_text(
    text_value,
    chunk_size=1200,
    overlap=200,
):
    clean_text = re.sub(
        r"[ \t]+",
        " ",
        text_value or "",
    )

    clean_text = re.sub(
        r"\n{3,}",
        "\n\n",
        clean_text,
    ).strip()

    if not clean_text:
        return []

    chunks = []
    start = 0
    length = len(clean_text)

    while start < length:
        end = min(
            start + chunk_size,
            length,
        )

        if end < length:
            boundary = max(
                clean_text.rfind("\n", start, end),
                clean_text.rfind(". ", start, end),
                clean_text.rfind(" ", start, end),
            )

            if boundary > start + (chunk_size // 2):
                end = boundary + 1

        chunk = clean_text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= length:
            break

        start = max(
            end - overlap,
            start + 1,
        )

    return chunks




def create_rag_embeddings(
    texts,
    batch_size=24,
):
    """
    Create embeddings through the existing
    OpenRouter/OpenAI-compatible client.
    """

    if not texts:
        return []

    all_vectors = []

    for start in range(
        0,
        len(texts),
        batch_size,
    ):
        batch = texts[
            start:
            start + batch_size
        ]

        response = client.embeddings.create(
            model=RAG_EMBEDDING_MODEL,
            input=batch,
            encoding_format="float",
        )

        batch_vectors = [
            item.embedding
            for item in response.data
        ]

        if len(batch_vectors) != len(batch):
            raise RuntimeError(
                "Embedding API returned an unexpected result."
            )

        all_vectors.extend(
            batch_vectors
        )

    return all_vectors


def parse_rag_embedding(
    value,
):
    if not value:
        return None

    try:
        vector = json.loads(value)

        if not isinstance(
            vector,
            list,
        ):
            return None

        return [
            float(item)
            for item in vector
        ]

    except Exception:
        return None


def cosine_similarity(
    first,
    second,
):
    if (
        not first
        or not second
        or len(first) != len(second)
    ):
        return 0.0

    dot = sum(
        a * b
        for a, b in zip(
            first,
            second,
        )
    )

    first_norm = math.sqrt(
        sum(
            value * value
            for value in first
        )
    )

    second_norm = math.sqrt(
        sum(
            value * value
            for value in second
        )
    )

    denominator = (
        first_norm
        * second_norm
    )

    if denominator <= 0:
        return 0.0

    return dot / denominator



def rag_tokens(text_value):
    return re.findall(
        r"[\w]+",
        (text_value or "").lower(),
        flags=re.UNICODE,
    )


def score_rag_chunk(question, chunk_content):
    query_tokens = rag_tokens(question)

    if not query_tokens:
        return 0.0

    chunk_tokens = rag_tokens(chunk_content)

    if not chunk_tokens:
        return 0.0

    query_set = set(query_tokens)
    chunk_set = set(chunk_tokens)
    overlap = query_set.intersection(chunk_set)

    if not overlap:
        return 0.0

    overlap_score = len(overlap) / max(
        len(query_set),
        1,
    )

    exact_bonus = 0.0
    clean_question = (question or "").strip().lower()

    if (
        len(clean_question) >= 4
        and clean_question in (chunk_content or "").lower()
    ):
        exact_bonus = 1.0

    frequency_bonus = sum(
        min(chunk_tokens.count(token), 3)
        for token in overlap
    ) / max(len(query_set) * 3, 1)

    return (
        overlap_score * 0.75
        + frequency_bonus * 0.25
        + exact_bonus
    )


def retrieve_rag_chunks(
    db,
    username,
    question,
    document_id=None,
    top_k=5,
):
    query = db.query(
        RagChunk,
        RagDocument,
    ).join(
        RagDocument,
        RagDocument.document_id
        == RagChunk.document_id,
    ).filter(
        RagChunk.username == username,
        RagDocument.username == username,
    )

    if document_id:
        query = query.filter(
            RagChunk.document_id
            == document_id
        )

    rows = query.all()

    if not rows:
        return []

    # ---------------------------------
    # Query semantic embedding
    # ---------------------------------

    query_embedding = None

    try:
        vectors = create_rag_embeddings(
            [question]
        )

        if vectors:
            query_embedding = vectors[0]

    except Exception as error:
        print(
            "RAG QUERY EMBEDDING ERROR:",
            str(error),
        )

        # Keyword retrieval still works.


    scored = []

    for chunk, document in rows:

        # ---------------------------------
        # Existing lexical score
        # ---------------------------------

        keyword_score = score_rag_chunk(
            question,
            chunk.content,
        )

        # Existing keyword score can exceed
        # 1 because of exact-match bonus.
        # Normalize it before hybrid scoring.

        normalized_keyword = min(
            max(keyword_score, 0.0)
            / 1.5,
            1.0,
        )


        # ---------------------------------
        # Semantic similarity
        # ---------------------------------

        semantic_score = 0.0

        stored_embedding = (
            parse_rag_embedding(
                chunk.embedding
            )
        )

        if (
            query_embedding
            and stored_embedding
        ):
            semantic_score = (
                cosine_similarity(
                    query_embedding,
                    stored_embedding,
                )
            )

            semantic_score = max(
                semantic_score,
                0.0,
            )


        # ---------------------------------
        # Hybrid score
        # ---------------------------------

        if (
            query_embedding
            and stored_embedding
        ):
            final_score = (
                semantic_score
                * 0.75
                +
                normalized_keyword
                * 0.25
            )

        else:
            # Old documents or API failure:
            # preserve keyword retrieval.
            final_score = (
                normalized_keyword
            )


        if final_score > 0:
            scored.append((
                final_score,
                chunk,
                document,
            ))


    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return scored[:top_k]



@app.post("/rag/upload")
async def rag_upload_document(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(authorization)

    original_name = os.path.basename(
        file.filename or "document"
    )

    extension = os.path.splitext(
        original_name
    )[1].lower()

    if extension not in [
        ".txt",
        ".csv",
        ".pdf",
    ]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only TXT, CSV and PDF "
                "documents are supported."
            ),
        )

    document_id = uuid.uuid4().hex

    rag_folder = os.path.join(
        UPLOAD_DIR,
        username,
        "rag",
    )

    os.makedirs(
        rag_folder,
        exist_ok=True,
    )

    stored_name = (
        f"{document_id}_"
        + original_name
    )

    file_path = os.path.abspath(
        os.path.join(
            rag_folder,
            stored_name,
        )
    )

    content = await file.read(
        MAX_UPLOAD_BYTES + 1
    )

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                "File is too large. "
                "Maximum upload size is 10 MB."
            ),
        )

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty.",
        )

    with open(file_path, "wb") as output:
        output.write(content)

    try:
        extracted_text = extract_rag_text(
            file_path,
            extension,
        )
    except Exception as error:
        try:
            os.remove(file_path)
        except Exception:
            pass

        raise HTTPException(
            status_code=400,
            detail=(
                "Could not read this document."
            ),
        )

    if not extracted_text.strip():
        try:
            os.remove(file_path)
        except Exception:
            pass

        raise HTTPException(
            status_code=400,
            detail=(
                "No readable text found. "
                "Scanned PDFs need OCR before upload."
            ),
        )

    chunks = chunk_rag_text(extracted_text)

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="Could not create document chunks.",
        )

    # Generate semantic embeddings.
    # If the free embedding service is temporarily
    # unavailable, document upload still succeeds
    # and keyword retrieval remains available.

    chunk_embeddings = [
        None
        for _ in chunks
    ]

    try:
        generated_embeddings = (
            create_rag_embeddings(
                chunks
            )
        )

        if (
            len(generated_embeddings)
            == len(chunks)
        ):
            chunk_embeddings = (
                generated_embeddings
            )

    except Exception as error:
        print(
            "RAG DOCUMENT EMBEDDING ERROR:",
            str(error),
        )


    db = SessionLocal()

    try:
        document = RagDocument(
            document_id=document_id,
            username=username,
            filename=original_name,
            file_path=file_path,
            file_type=extension.lstrip("."),
        )

        db.add(document)
        db.flush()

        for index, chunk in enumerate(chunks):
            db.add(
                RagChunk(
                    document_id=document_id,
                    username=username,
                    chunk_index=index,
                    content=chunk,
                    embedding=(
                        json.dumps(
                            chunk_embeddings[index]
                        )
                        if chunk_embeddings[index]
                        is not None
                        else None
                    ),
                )
            )

        db.commit()

        return {
            "success": True,
            "document_id": document_id,
            "filename": original_name,
            "chunks": len(chunks),
        }

    except Exception:
        db.rollback()

        try:
            os.remove(file_path)
        except Exception:
            pass

        raise

    finally:
        db.close()


@app.get("/rag/documents")
def rag_list_documents(
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(authorization)
    db = SessionLocal()

    try:
        documents = (
            db.query(RagDocument)
            .filter(
                RagDocument.username == username
            )
            .order_by(
                RagDocument.created_at.desc()
            )
            .all()
        )

        result = []

        for document in documents:
            chunk_count = (
                db.query(RagChunk)
                .filter(
                    RagChunk.document_id
                    == document.document_id,
                    RagChunk.username
                    == username,
                )
                .count()
            )

            result.append({
                "document_id": document.document_id,
                "filename": document.filename,
                "file_type": document.file_type,
                "chunks": chunk_count,
                "created_at": (
                    document.created_at.isoformat()
                    if document.created_at
                    else None
                ),
            })

        return {
            "documents": result
        }

    finally:
        db.close()


@app.delete("/rag/documents/{document_id}")
def rag_delete_document(
    document_id: str,
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(authorization)
    db = SessionLocal()

    try:
        document = (
            db.query(RagDocument)
            .filter(
                RagDocument.document_id == document_id,
                RagDocument.username == username,
            )
            .first()
        )

        if not document:
            raise HTTPException(
                status_code=404,
                detail="Document not found.",
            )

        stored_path = document.file_path

        db.query(RagChunk).filter(
            RagChunk.document_id == document_id,
            RagChunk.username == username,
        ).delete(
            synchronize_session=False
        )

        db.delete(document)
        db.commit()

        if stored_path and os.path.exists(stored_path):
            try:
                os.remove(stored_path)
            except Exception as error:
                print(
                    "RAG FILE DELETE ERROR:",
                    str(error),
                )

        return {
            "success": True,
            "message": "Document deleted.",
        }

    finally:
        db.close()


@app.post("/rag/ask")
def rag_ask(
    request: RagAskRequest,
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(authorization)

    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question is required.",
        )

    top_k = max(
        1,
        min(request.top_k, 8),
    )

    db = SessionLocal()

    try:
        if request.document_id:
            document = (
                db.query(RagDocument)
                .filter(
                    RagDocument.document_id
                    == request.document_id,
                    RagDocument.username
                    == username,
                )
                .first()
            )

            if not document:
                raise HTTPException(
                    status_code=404,
                    detail="Document not found.",
                )

        matches = retrieve_rag_chunks(
            db,
            username,
            question,
            document_id=request.document_id,
            top_k=top_k,
        )

        if not matches:
            return {
                "answer": (
                    "I could not find relevant "
                    "information in your uploaded documents."
                ),
                "sources": [],
            }

        context_parts = []
        source_items = []

        for rank, (score, chunk, document) in enumerate(
            matches,
            start=1,
        ):
            context_parts.append(
                f"SOURCE {rank} - {document.filename} "
                f"(chunk {chunk.chunk_index + 1}):\n"
                f"{chunk.content}"
            )

            source_items.append({
                "document_id": document.document_id,
                "filename": document.filename,
                "chunk": chunk.chunk_index + 1,
                "score": round(score, 4),
            })

        rag_prompt = (
            "Answer the user's question using only the "
            "document context below. If the answer is not "
            "supported by the context, say that it was not "
            "found in the uploaded documents. Do not invent "
            "facts. When useful, mention the source filename.\n\n"
            "DOCUMENT CONTEXT:\n"
            + "\n\n".join(context_parts)
            + "\n\nUSER QUESTION:\n"
            + question
        )

        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a retrieval-augmented "
                        "document question-answering assistant."
                    ),
                },
                {
                    "role": "user",
                    "content": rag_prompt,
                },
            ],
        )

        answer = (
            response.choices[0].message.content
            or (
                "I could not generate a document-based "
                "answer. Please try again."
            )
        )

        return {
            "answer": answer,
            "sources": source_items,
        }

    except HTTPException:
        raise

    except Exception as error:
        print(
            "RAG ASK ERROR:",
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Could not generate a "
                "document-based answer."
            ),
        )

    finally:
        db.close()




@app.post("/rag/reindex")
def rag_reindex_embeddings(
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(
        authorization
    )

    db = SessionLocal()

    try:

        chunks = (
            db.query(RagChunk)
            .filter(
                RagChunk.username
                == username
            )
            .order_by(
                RagChunk.id.asc()
            )
            .all()
        )

        if not chunks:
            return {
                "success": True,
                "updated": 0,
                "message":
                    "No RAG chunks found.",
            }


        pending = [
            chunk
            for chunk in chunks
            if not chunk.embedding
        ]


        if not pending:
            return {
                "success": True,
                "updated": 0,
                "message":
                    "All chunks already have embeddings.",
            }


        updated = 0
        batch_size = 24


        for start in range(
            0,
            len(pending),
            batch_size,
        ):

            batch_chunks = pending[
                start:
                start + batch_size
            ]


            texts = [
                chunk.content
                for chunk in batch_chunks
            ]


            vectors = (
                create_rag_embeddings(
                    texts,
                    batch_size=batch_size,
                )
            )


            if (
                len(vectors)
                != len(batch_chunks)
            ):
                raise RuntimeError(
                    "Embedding result count mismatch."
                )


            for chunk, vector in zip(
                batch_chunks,
                vectors,
            ):

                chunk.embedding = (
                    json.dumps(vector)
                )

                updated += 1


            db.commit()


        return {
            "success": True,
            "updated": updated,
            "message": (
                f"{updated} RAG chunks reindexed "
                "with semantic embeddings."
            ),
        }


    except HTTPException:
        db.rollback()
        raise

    except Exception as error:

        db.rollback()

        print(
            "RAG REINDEX ERROR:",
            str(error),
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Could not generate document embeddings."
            ),
        )

    finally:
        db.close()



# =========================================================
# WEBSITE / URL READER API
# =========================================================

@app.post("/url/ask")
def ask_webpage(
    data: UrlReaderRequest,
    authorization: Optional[str] = Header(None),
):
    get_current_user(authorization)

    try:
        page = read_webpage(data.url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        print("URL READER ERROR:", str(error))
        raise HTTPException(
            status_code=502,
            detail="Could not read this webpage. The site may block automated access.",
        )

    question = (data.question or "").strip()
    if not question:
        question = "Summarize this webpage clearly and concisely."

    prompt = f"""
You are analyzing a webpage for the user.

Use ONLY the webpage content below for factual claims about the page.
If the requested information is not present, say that it was not found on the webpage.
Do not invent missing details.

Page title: {page['title']}
URL: {page['url']}

User request:
{question}

Webpage content:
{page['content']}
"""

    try:
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Answer from the supplied webpage content only.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )

        answer = (
            response.choices[0].message.content
            or "I could not generate a webpage answer."
        )

    except Exception as error:
        error_text = str(error)
        print("URL AI ERROR:", error_text)

        if "429" in error_text or "Rate limit" in error_text:
            raise HTTPException(
                status_code=429,
                detail="Free API limit reached. Please try again later.",
            )

        raise HTTPException(
            status_code=502,
            detail="AI could not analyze the webpage right now.",
        )

    return {
        "title": page["title"],
        "url": page["url"],
        "answer": answer,
    }



# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.get("/admin/status")
def admin_status(
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(authorization)

    return {
        "is_admin": is_admin_username(username),
    }


@app.get("/admin/stats")
def admin_stats(
    authorization: Optional[str] = Header(None),
):
    require_admin(authorization)

    db = SessionLocal()

    try:
        return {
            "users": db.query(User).count(),
            "verified_users": (
                db.query(User)
                .filter(User.email_verified == True)
                .count()
            ),
            "chats": db.query(Chat).count(),
            "messages": db.query(Message).count(),
            "documents": db.query(RagDocument).count(),
            "rag_chunks": db.query(RagChunk).count(),
            "memories": db.query(UserMemory).count(),
        }

    finally:
        db.close()


@app.get("/admin/users")
def admin_users(
    authorization: Optional[str] = Header(None),
):
    require_admin(authorization)

    db = SessionLocal()

    try:
        users = (
            db.query(User)
            .order_by(User.created_at.desc())
            .all()
        )

        output = []

        for user in users:
            output.append({
                "username": user.username,
                "email": user.email,
                "email_verified": user.email_verified,
                "created_at": (
                    user.created_at.isoformat()
                    if user.created_at
                    else None
                ),
                "chat_count": (
                    db.query(Chat)
                    .filter(Chat.username == user.username)
                    .count()
                ),
                "document_count": (
                    db.query(RagDocument)
                    .filter(RagDocument.username == user.username)
                    .count()
                ),
                "memory_count": (
                    db.query(UserMemory)
                    .filter(UserMemory.username == user.username)
                    .count()
                ),
            })

        return {
            "users": output,
        }

    finally:
        db.close()


@app.get("/admin/users/{target_username}")
def admin_user_details(
    target_username: str,
    authorization: Optional[str] = Header(None),
):
    require_admin(authorization)

    clean_username = (
        target_username
        .strip()
        .lower()
    )

    db = SessionLocal()

    try:

        user = (
            db.query(User)
            .filter(
                User.username
                == clean_username
            )
            .first()
        )

        if not user:

            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        chat_ids = [
            item.chat_id
            for item in (
                db.query(Chat)
                .filter(
                    Chat.username
                    == user.username
                )
                .all()
            )
        ]

        message_count = 0

        if chat_ids:

            message_count = (
                db.query(Message)
                .filter(
                    Message.chat_id.in_(
                        chat_ids
                    )
                )
                .count()
            )

        recent_chats = (
            db.query(Chat)
            .filter(
                Chat.username
                == user.username
            )
            .order_by(
                Chat.created_at.desc()
            )
            .limit(5)
            .all()
        )

        return {

            "username":
                user.username,

            "email":
                user.email,

            "email_verified":
                user.email_verified,

            "created_at":
                (
                    user.created_at.isoformat()
                    if user.created_at
                    else None
                ),

            "is_admin":
                is_admin_username(
                    user.username
                ),

            "chat_count":
                len(chat_ids),

            "message_count":
                message_count,

            "document_count":
                (
                    db.query(
                        RagDocument
                    )
                    .filter(
                        RagDocument.username
                        == user.username
                    )
                    .count()
                ),

            "rag_chunk_count":
                (
                    db.query(
                        RagChunk
                    )
                    .filter(
                        RagChunk.username
                        == user.username
                    )
                    .count()
                ),

            "memory_count":
                (
                    db.query(
                        UserMemory
                    )
                    .filter(
                        UserMemory.username
                        == user.username
                    )
                    .count()
                ),

            "recent_chats": [

                {
                    "chat_id":
                        chat.chat_id,

                    "title":
                        chat.title,

                    "created_at":
                        (
                            chat.created_at
                            .isoformat()
                            if chat.created_at
                            else None
                        ),
                }

                for chat
                in recent_chats
            ],
        }

    finally:

        db.close()


# =========================================================


@app.get("/admin/analytics")
def admin_analytics(
    authorization: Optional[str] = Header(None),
):
    require_admin(authorization)

    db = SessionLocal()

    try:

        today = datetime.utcnow().date()

        daily = []

        for offset in range(6, -1, -1):

            day = today - timedelta(days=offset)

            start = datetime.combine(
                day,
                datetime.min.time(),
            )

            end = start + timedelta(days=1)

            users_count = (
                db.query(User)
                .filter(
                    User.created_at >= start,
                    User.created_at < end,
                )
                .count()
            )

            chats_count = (
                db.query(Chat)
                .filter(
                    Chat.created_at >= start,
                    Chat.created_at < end,
                )
                .count()
            )

            messages_count = (
                db.query(Message)
                .filter(
                    Message.created_at >= start,
                    Message.created_at < end,
                )
                .count()
            )

            daily.append({
                "date": day.isoformat(),
                "users": users_count,
                "chats": chats_count,
                "messages": messages_count,
            })


        recent_activity = []


        recent_users = (
            db.query(User)
            .order_by(
                User.created_at.desc()
            )
            .limit(5)
            .all()
        )

        for user in recent_users:

            recent_activity.append({
                "type": "user",
                "title": (
                    "New user: "
                    + user.username
                ),
                "username": user.username,
                "created_at": (
                    user.created_at.isoformat()
                    if user.created_at
                    else None
                ),
            })


        recent_chats = (
            db.query(Chat)
            .order_by(
                Chat.created_at.desc()
            )
            .limit(5)
            .all()
        )

        for chat in recent_chats:

            recent_activity.append({
                "type": "chat",
                "title": (
                    "New chat: "
                    + (
                        chat.title
                        or "New Chat"
                    )
                ),
                "username": chat.username,
                "created_at": (
                    chat.created_at.isoformat()
                    if chat.created_at
                    else None
                ),
            })


        recent_messages = (
            db.query(
                Message,
                Chat.username,
            )
            .join(
                Chat,
                Message.chat_id
                == Chat.chat_id,
            )
            .order_by(
                Message.created_at.desc()
            )
            .limit(5)
            .all()
        )

        for message, username in recent_messages:

            recent_activity.append({
                "type": "message",
                "title": (
                    "New "
                    + (
                        message.role
                        or "message"
                    )
                    + " message"
                ),
                "username": username,
                "created_at": (
                    message.created_at.isoformat()
                    if message.created_at
                    else None
                ),
            })


        recent_activity.sort(
            key=lambda item: (
                item.get("created_at")
                or ""
            ),
            reverse=True,
        )


        last_7_days = (
            today - timedelta(days=6)
        )

        last_7_start = datetime.combine(
            last_7_days,
            datetime.min.time(),
        )


        return {

            "daily": daily,

            "last_7_days": {

                "new_users": (
                    db.query(User)
                    .filter(
                        User.created_at
                        >= last_7_start
                    )
                    .count()
                ),

                "new_chats": (
                    db.query(Chat)
                    .filter(
                        Chat.created_at
                        >= last_7_start
                    )
                    .count()
                ),

                "new_messages": (
                    db.query(Message)
                    .filter(
                        Message.created_at
                        >= last_7_start
                    )
                    .count()
                ),

            },

            "recent_activity":
                recent_activity[:12],

        }

    finally:
        db.close()


# HEALTH

# =========================================================



@app.get("/health")

def health():



    db = None



    try:



        db = SessionLocal()



        db.execute(

            text(

                "SELECT 1"

            )

        )



        return {

            "status":

                "ok",



            "database":

                "connected",

        }



    except Exception as error:



        return {

            "status":

                "error",



            "database":

                str(error),

        }



    finally:



        if db:

            db.close()





# =========================================================

# FRONTEND

# =========================================================



@app.get("/")

def frontend():



    return FileResponse(

        "index.html"

    )  
    
    # =========================================================
# REAL-TIME AI CHAT STREAMING
# =========================================================

@app.post("/chat/stream")
def chat_stream_endpoint(
    request: ChatRequest,
    authorization: Optional[str] = Header(None),
):
    username = get_current_user(authorization)

    # Validate ownership before starting the stream.
    db = SessionLocal()

    try:
        current_chat = (
            db.query(Chat)
            .filter(
                Chat.chat_id == request.chat_id,
                Chat.username == username,
            )
            .first()
        )

        if not current_chat:
            raise HTTPException(
                status_code=404,
                detail="Chat not found",
            )

    finally:
        db.close()

    visible_message = request.message.strip()

    if not visible_message:
        visible_message = (
            "Please analyze the uploaded file."
        )

    model_message = visible_message

    if request.file_path:
        model_message += (
            "\n\nUploaded file path: "
            + request.file_path
            + "\nRead this file before answering."
        )

    def event_stream():

        stream_db = SessionLocal()

        stream = None

        completed = False

        try:

            current_chat = (
                stream_db.query(Chat)
                .filter(
                    Chat.chat_id == request.chat_id,
                    Chat.username == username,
                )
                .first()
            )

            if not current_chat:

                yield (
                    "data: "
                    + json.dumps({
                        "type": "error",
                        "message": "Chat not found",
                    })
                    + "\n\n"
                )

                return

            previous_messages = (
                stream_db.query(Message)
                .filter(
                    Message.chat_id == request.chat_id
                )
                .order_by(Message.id.asc())
                .all()
            )

            model_messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                }
            ]

            model_messages = add_smart_memory_to_messages(
                model_messages,
                username,
                visible_message,
                exclude_chat_id=request.chat_id,
            )

            for item in previous_messages:

                if item.role in (
                    "user",
                    "assistant",
                ):

                    model_messages.append({
                        "role": item.role,
                        "content": item.content,
                    })

            model_messages.append({
                "role": "user",
                "content": model_message,
            })

            # ---------------------------------
            # STEP 1: CHECK WHETHER TOOLS
            # ARE REQUIRED
            # ---------------------------------

            initial_response = (
                client.chat.completions.create(
                    model=OPENROUTER_MODEL,
                    messages=model_messages,
                    tools=tools,
                    tool_choice="auto",
                )
            )

            assistant_message = (
                initial_response.choices[0].message
            )

            tool_calls = (
                assistant_message.tool_calls or []
            )

            # ---------------------------------
            # STEP 2: EXECUTE TOOLS
            # ---------------------------------

            if tool_calls:

                model_messages.append(
                    assistant_message
                )

                for tool_call in tool_calls:

                    tool_name = (
                        tool_call.function.name
                    )

                    try:

                        arguments = json.loads(
                            tool_call.function.arguments
                        )

                    except Exception:

                        arguments = {}

                    try:

                        result = execute_tool(
                            username,
                            tool_name,
                            arguments,
                        )

                    except Exception as error:

                        result = (
                            "Tool error: "
                            + str(error)
                        )

                    model_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(
                            result,
                            ensure_ascii=False,
                            default=str,
                        ),
                    })

            # ---------------------------------
            # STEP 3: STREAM THE FINAL ANSWER
            # ---------------------------------

            yield (
                "data: "
                + json.dumps({
                    "type": "start",
                })
                + "\n\n"
            )

            # The final request does not pass
            # tools again, preventing repeated
            # tool calls or an empty tool response.

            stream = (
                client.chat.completions.create(
                    model=OPENROUTER_MODEL,
                    messages=model_messages,
                    stream=True,
                )
            )

            answer_parts = []

            for chunk in stream:

                if not chunk.choices:
                    continue

                delta = (
                    chunk.choices[0]
                    .delta
                    .content
                )

                if not delta:
                    continue

                answer_parts.append(delta)

                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "delta",
                            "content": delta,
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )

            answer = "".join(answer_parts).strip()

            if not answer:

                answer = (
                    "I could not generate "
                    "a response. Please try again."
                )

                yield (
                    "data: "
                    + json.dumps({
                        "type": "delta",
                        "content": answer,
                    })
                    + "\n\n"
                )

            # ---------------------------------
            # STEP 4: SAVE CHAT HISTORY
            # ---------------------------------

            stream_db.add(
                Message(
                    chat_id=request.chat_id,
                    role="user",
                    content=visible_message,
                )
            )

            stream_db.add(
                Message(
                    chat_id=request.chat_id,
                    role="assistant",
                    content=answer,
                )
            )

            if (
                current_chat.title == "New Chat"
                and visible_message
            ):

                current_chat.title = (
                    visible_message[:30]
                )

            stream_db.commit()

            completed = True

            # ---------------------------------
            # STEP 5: STREAM COMPLETED
            # ---------------------------------

            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "done",
                        "answer": answer,
                        "title": current_chat.title,
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )

        except GeneratorExit:

            # Client disconnected.
            # Do not save incomplete answers.

            if not completed:
                stream_db.rollback()

            raise

        except Exception as error:

            stream_db.rollback()

            print(
                "STREAM ERROR:",
                str(error),
            )

            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "message": str(error),
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )

        finally:

            if stream is not None:

                try:
                    stream.close()
                except Exception:
                    pass

            stream_db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
