import os
import json
import uuid
import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from ddgs import DDGS
from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Header,
    HTTPException
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
from pypdf import PdfReader
from dotenv import load_dotenv


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv(override=True)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret")

if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY missing from .env")


# =========================================================
# APP
# =========================================================

app = FastAPI(title="My AI Agent")

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
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY.strip()
)


# =========================================================
# FILES
# =========================================================

USERS_FILE = "users.json"
CHATS_FILE = "chats.json"
MEMORY_FILE = "memory.json"

UPLOAD_DIR = "uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)


# =========================================================
# JSON HELPERS
# =========================================================

def load_json(path, default):

    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return default


def save_json(path, data):

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4
        )


users = load_json(USERS_FILE, {})
chats = load_json(CHATS_FILE, {})
memory = load_json(MEMORY_FILE, {})


# =========================================================
# AUTH
# =========================================================

def create_token(username):

    payload = {
        "username": username,
        "exp": datetime.utcnow() + timedelta(days=7)
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm="HS256"
    )


def get_current_user(
    authorization: Optional[str]
):

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Login required"
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication"
        )

    token = authorization.split(" ", 1)[1]

    try:

        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"]
        )

        return payload["username"]

    except Exception:

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )


# =========================================================
# AUTH MODELS
# =========================================================

class AuthRequest(BaseModel):
    username: str
    password: str


@app.post("/register")
def register(data: AuthRequest):

    username = data.username.strip().lower()

    if len(username) < 3:
        raise HTTPException(
            status_code=400,
            detail="Username too short"
        )

    if len(data.password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters"
        )

    if username in users:
        raise HTTPException(
            status_code=400,
            detail="User already exists"
        )

    hashed = bcrypt.hashpw(
        data.password.encode(),
        bcrypt.gensalt()
    ).decode()

    users[username] = {
        "password": hashed
    }

    chats[username] = {}

    save_json(USERS_FILE, users)
    save_json(CHATS_FILE, chats)

    token = create_token(username)

    return {
        "token": token,
        "username": username
    }


@app.post("/login")
def login(data: AuthRequest):

    username = data.username.strip().lower()

    user = users.get(username)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    valid = bcrypt.checkpw(
        data.password.encode(),
        user["password"].encode()
    )

    if not valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    return {
        "token": create_token(username),
        "username": username
    }


# =========================================================
# TOOLS
# =========================================================

def add_numbers(a, b):
    return a + b


def get_current_datetime():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def web_search(query):

    try:

        results = DDGS().text(
            query,
            max_results=5
        )

        return [
            {
                "title": r.get("title"),
                "url": r.get("href"),
                "snippet": r.get("body")
            }
            for r in results
        ]

    except Exception as e:

        return f"Search error: {e}"


def save_user_memory(username, key, value):

    if username not in memory:
        memory[username] = {}

    memory[username][key] = value

    save_json(
        MEMORY_FILE,
        memory
    )

    return f"Saved {key}: {value}"


def get_user_memory(username, key):

    return memory.get(
        username,
        {}
    ).get(
        key,
        "No saved information found."
    )


def read_text_file(file_path):

    if not os.path.exists(file_path):
        return "File not found."

    try:

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as f:

            text = f.read()

        return text[:20000]

    except Exception as e:
        return f"TXT error: {e}"


def read_csv_file(file_path):

    if not os.path.exists(file_path):
        return "File not found."

    try:

        df = pd.read_csv(file_path)

        return {
            "rows": len(df),
            "columns": df.columns.tolist(),
            "preview": df.head(15).to_dict(
                orient="records"
            )
        }

    except Exception as e:
        return f"CSV error: {e}"


def read_pdf_file(file_path):

    if not os.path.exists(file_path):
        return "File not found."

    try:

        reader = PdfReader(file_path)

        text = ""

        for i, page in enumerate(
            reader.pages,
            start=1
        ):

            content = page.extract_text()

            if content:

                text += (
                    f"\n--- Page {i} ---\n"
                    + content
                )

        if not text.strip():
            return (
                "No readable text found. "
                "PDF may be scanned."
            )

        return {
            "pages": len(reader.pages),
            "content": text[:30000]
        }

    except Exception as e:
        return f"PDF error: {e}"


# =========================================================
# TOOL SCHEMAS
# =========================================================

tools = [

    {
        "type": "function",
        "function": {
            "name": "add_numbers",
            "description": "Add two numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"}
                },
                "required": ["a", "b"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Get current date and time.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string"
                    }
                },
                "required": ["query"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "save_user_memory",
            "description": (
                "Save information the user explicitly "
                "asks to remember."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"}
                },
                "required": ["key", "value"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "get_user_memory",
            "description": (
                "Get saved user information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                },
                "required": ["key"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "read_text_file",
            "description": "Read TXT file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string"
                    }
                },
                "required": ["file_path"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "read_csv_file",
            "description": "Read CSV file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string"
                    }
                },
                "required": ["file_path"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "read_pdf_file",
            "description": "Read PDF file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string"
                    }
                },
                "required": ["file_path"]
            }
        }
    }
]


SYSTEM_PROMPT = """
You are a helpful AI agent.

Capabilities:

- conversation
- calculator
- date/time
- web search
- persistent memory
- TXT reading
- CSV reading
- PDF reading

Use tools when appropriate.

Use web_search for current or recent information.

Use save_user_memory only when the user explicitly
asks you to remember something.

If a file path is supplied, use the appropriate
file-reading tool.

Keep answers clear and helpful.
"""


# =========================================================
# CHAT MODELS
# =========================================================

class CreateChatRequest(BaseModel):
    title: Optional[str] = "New Chat"


class ChatRequest(BaseModel):
    chat_id: str
    message: str
    file_path: Optional[str] = None


# =========================================================
# CHAT MANAGEMENT
# =========================================================

@app.post("/chats")
def create_chat(
    request: CreateChatRequest,
    authorization: Optional[str] = Header(None)
):

    username = get_current_user(
        authorization
    )

    if username not in chats:
        chats[username] = {}

    chat_id = uuid.uuid4().hex

    chats[username][chat_id] = {
        "title": request.title or "New Chat",
        "messages": []
    }

    save_json(CHATS_FILE, chats)

    return {
        "chat_id": chat_id,
        "title": chats[username][chat_id]["title"]
    }


@app.get("/chats")
def list_chats(
    authorization: Optional[str] = Header(None)
):

    username = get_current_user(
        authorization
    )

    user_chats = chats.get(
        username,
        {}
    )

    result = []

    for chat_id, data in user_chats.items():

        result.append({
            "chat_id": chat_id,
            "title": data.get(
                "title",
                "New Chat"
            )
        })

    return {
        "chats": result
    }


@app.get("/chats/{chat_id}")
def get_chat(
    chat_id: str,
    authorization: Optional[str] = Header(None)
):

    username = get_current_user(
        authorization
    )

    chat = chats.get(
        username,
        {}
    ).get(chat_id)

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found"
        )

    return chat


@app.delete("/chats/{chat_id}")
def delete_chat(
    chat_id: str,
    authorization: Optional[str] = Header(None)
):

    username = get_current_user(
        authorization
    )

    if (
        username in chats
        and chat_id in chats[username]
    ):

        del chats[username][chat_id]

        save_json(
            CHATS_FILE,
            chats
        )

    return {
        "success": True
    }


# =========================================================
# FILE UPLOAD
# =========================================================

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):

    username = get_current_user(
        authorization
    )

    original_name = (
        file.filename
        or "file"
    )

    extension = os.path.splitext(
        original_name
    )[1].lower()

    if extension not in [
        ".txt",
        ".csv",
        ".pdf"
    ]:

        raise HTTPException(
            status_code=400,
            detail="Only TXT, CSV and PDF supported."
        )

    user_folder = os.path.join(
        UPLOAD_DIR,
        username
    )

    os.makedirs(
        user_folder,
        exist_ok=True
    )

    filename = (
        f"{uuid.uuid4().hex}_"
        f"{os.path.basename(original_name)}"
    )

    path = os.path.join(
        user_folder,
        filename
    )

    content = await file.read()

    with open(
        path,
        "wb"
    ) as f:

        f.write(content)

    return {
        "success": True,
        "filename": original_name,
        "file_path": os.path.abspath(path)
    }


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
def chat(
    request: ChatRequest,
    authorization: Optional[str] = Header(None)
):

    username = get_current_user(
        authorization
    )

    user_chats = chats.get(
        username,
        {}
    )

    current_chat = user_chats.get(
        request.chat_id
    )

    if not current_chat:

        raise HTTPException(
            status_code=404,
            detail="Chat not found"
        )

    visible_message = (
        request.message.strip()
    )

    model_message = visible_message

    if request.file_path:

        model_message += (
            "\n\nUploaded file path: "
            + request.file_path
            + "\nRead this file before answering."
        )


    previous_messages = current_chat.get(
        "messages",
        []
    )


    model_messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]


    for item in previous_messages:

        if item["role"] in [
            "user",
            "assistant"
        ]:

            model_messages.append({
                "role": item["role"],
                "content": item["content"]
            })


    model_messages.append({
        "role": "user",
        "content": model_message
    })


    try:

        response = client.chat.completions.create(
            model="openrouter/free",
            messages=model_messages,
            tools=tools,
            tool_choice="auto"
        )

        message = (
            response
            .choices[0]
            .message
        )


        if message.tool_calls:

            model_messages.append(
                message
            )


            for tool_call in message.tool_calls:

                name = (
                    tool_call.function.name
                )

                args = json.loads(
                    tool_call.function.arguments
                )

                result = None


                if name == "add_numbers":

                    result = add_numbers(
                        args["a"],
                        args["b"]
                    )


                elif name == "get_current_datetime":

                    result = (
                        get_current_datetime()
                    )


                elif name == "web_search":

                    result = web_search(
                        args["query"]
                    )


                elif name == "save_user_memory":

                    result = save_user_memory(
                        username,
                        args["key"],
                        args["value"]
                    )


                elif name == "get_user_memory":

                    result = get_user_memory(
                        username,
                        args["key"]
                    )


                elif name == "read_text_file":

                    result = read_text_file(
                        args["file_path"]
                    )


                elif name == "read_csv_file":

                    result = read_csv_file(
                        args["file_path"]
                    )


                elif name == "read_pdf_file":

                    result = read_pdf_file(
                        args["file_path"]
                    )


                else:

                    result = (
                        "Unknown tool"
                    )


                model_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(
                        result,
                        ensure_ascii=False,
                        default=str
                    )
                })


            final_response = (
                client.chat.completions.create(
                    model="openrouter/free",
                    messages=model_messages,
                    tools=tools
                )
            )


            answer = (
                final_response
                .choices[0]
                .message
                .content
            )


        else:

            answer = message.content


        current_chat["messages"].append({
            "role": "user",
            "content": visible_message
        })


        current_chat["messages"].append({
            "role": "assistant",
            "content": answer or ""
        })


        if (
            current_chat["title"]
            == "New Chat"
            and visible_message
        ):

            current_chat["title"] = (
                visible_message[:30]
            )


        save_json(
            CHATS_FILE,
            chats
        )


        return {
            "answer": answer,
            "title": current_chat["title"]
        }


    except Exception as e:

        text = str(e)

        if (
            "429" in text
            or "Rate limit" in text
        ):

            answer = (
                "Free API daily limit reached. "
                "Please try again later."
            )

        elif (
            "401" in text
        ):

            answer = (
                "OpenRouter authentication failed."
            )

        else:

            answer = (
                "Error: " + text
            )

        return {
            "answer": answer
        }


# =========================================================
# FRONTEND
# =========================================================

@app.get("/")
def frontend():

    return FileResponse(
        "index.html"
    )