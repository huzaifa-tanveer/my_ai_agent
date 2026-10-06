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

from datetime import datetime, timedelta
from typing import Optional
from email.message import EmailMessage

import pandas as pd
from ddgs import DDGS

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Header,
    HTTPException,
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from pydantic import BaseModel

from openai import OpenAI
from pypdf import PdfReader
from dotenv import load_dotenv

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
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
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


class ChatRequest(BaseModel):
    chat_id: str
    message: str
    file_path: Optional[str] = None


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
        }

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

Use tools only when appropriate.

For ordinary questions, answer normally.

Use web_search when the user asks
for current or recent information.

Use save_user_memory only when the user
explicitly asks you to remember something.

When a file path is supplied,
use the appropriate file-reading tool.

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

    return "Unknown tool"


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