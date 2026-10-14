# 🤖 My AI Agent

A production-style full-stack AI assistant built with **FastAPI, PostgreSQL, Redis, OpenRouter, and vanilla JavaScript**.

My AI Agent combines real-time AI chat, persistent conversations, long-term memory, document-based RAG, website analysis, authentication, admin analytics, usage controls, monitoring, and production-focused security in one deployable application.

## 🌐 Live Demo

**Production:**  
https://myaiagent-production-649a.up.railway.app

**GitHub:**  
https://github.com/huzaifa-tanveer/my_ai_agent

---

## ✨ Key Features

### 💬 AI Chat
- Real-time streaming responses with Server-Sent Events
- Multiple persistent conversations
- Rename, delete, and search chats
- Stop generation
- Regenerate responses
- Copy AI responses
- Export conversations as TXT or PDF

### 🧠 Persistent Smart Memory
- Create, edit, delete, and view saved memories
- Reuse saved user context in future conversations
- PostgreSQL-backed, per-user storage

### 📚 Retrieval-Augmented Generation (RAG)
Upload TXT, CSV, or text-based PDF documents and ask grounded questions about them.

```text
Document Upload
      ↓
Text Extraction
      ↓
Chunking
      ↓
Embedding Generation
      ↓
PostgreSQL Storage
      ↓
User Question
      ↓
75% Semantic Retrieval
25% Keyword Retrieval
      ↓
Relevant Chunks
      ↓
OpenRouter LLM
      ↓
Grounded Answer
```

If embedding generation is unavailable, the application can fall back to keyword-based retrieval.

### 🌐 Website / URL Reader
- Summarize a public webpage
- Ask questions about page content
- Generate grounded answers from fetched text
- Block localhost/private-network targets for SSRF protection

> Some websites may block automated server-side access.

### 📎 File Tools
- TXT
- CSV
- PDF
- Per-user upload isolation
- Frontend/backend file-size validation

### 🛠 Built-in AI Tools
- Calculator
- Current date/time
- Web search
- Memory storage/retrieval
- TXT/CSV/PDF reading
- Website reading

### 🔐 Authentication & Account Security
- Registration
- bcrypt password hashing
- JWT authentication
- Email verification
- Verification-code resend
- Forgot password
- Email password reset
- Password change
- Account deletion

### 🛡 Admin Dashboard
- User, chat, message, RAG, and memory statistics
- User search and detailed user information
- Recent chats
- 7-day platform analytics

### 📈 Daily Usage Limits
Persistent daily limits protect public demo resources.

Default limits:
- AI Chat: **50/day**
- RAG Uploads: **10/day**
- RAG Questions: **30/day**
- URL Reader: **20/day**

Users can see current usage in **Profile / Settings**. Configured administrators are exempt.

### 🌙 User Interface
- Light/dark mode
- Responsive mobile layout
- Mobile sidebar
- Streaming/loading indicators
- RAG document manager
- URL Reader modal
- Settings panel
- Daily Usage dashboard
- Admin dashboard
- Privacy Policy and Terms of Use
- Keyboard shortcuts

---

## 🔒 Security & Reliability

- bcrypt password hashing
- JWT authentication with production secret from environment variables
- User ownership checks
- Admin authorization
- Email verification and password reset controls
- Restricted CORS
- Redis-backed API rate limiting
- In-memory fallback if Redis is temporarily unavailable
- Persistent per-user daily usage limits
- Request-size and upload-size protection
- User-isolated file access
- Safer public error responses
- Security response headers
- SSRF protection for URL Reader
- Private/localhost URL blocking
- Safe `/health` endpoint without raw database errors
- Sentry production error monitoring
- PostgreSQL backup/recovery script

Default maximum upload size:

```text
10 MB
```

---

## 🧰 Tech Stack

### Backend
- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- Redis
- OpenAI Python SDK
- OpenRouter
- PyJWT
- bcrypt
- Pydantic

### AI / Retrieval
- OpenRouter
- Semantic embeddings
- Hybrid retrieval
- Cosine similarity
- Document chunking
- DDGS web search

### File Processing
- pandas
- PyPDF
- ReportLab

### Frontend
- HTML
- CSS
- JavaScript
- Fetch API
- Server-Sent Events
- Marked.js

### Monitoring / Infrastructure
- Railway
- PostgreSQL
- Redis
- Sentry
- GitHub

---

## 🧠 System Architecture

```text
                         ┌──────────────────┐
                         │       User       │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │  HTML / CSS / JS │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │     FastAPI      │
                         └────────┬─────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
 ┌────────────────┐      ┌────────────────┐      ┌────────────────┐
 │   PostgreSQL   │      │   OpenRouter   │      │ External Web   │
 │ Users          │      │ Chat LLM       │      │ / DDGS Search  │
 │ Chats          │      │ Embeddings     │      └────────────────┘
 │ Messages       │      └────────────────┘
 │ Memory         │
 │ RAG Chunks     │
 │ Usage Events   │
 └────────────────┘
          │
          ▼
 ┌────────────────┐
 │     Redis      │
 │ Rate Limiting  │
 └────────────────┘

 FastAPI errors ───────────────────────────────► Sentry
```

---

## 📁 Project Structure

```text
my_ai_agent/
│
├── app.py
├── index.html
├── requirements.txt
├── backup_my_ai_agent.ps1
├── .env
├── .gitignore
│
├── uploads/
│
└── README.md
```

> `.env`, runtime uploads, local dumps, and credentials should never be committed to Git.

---

## ⚙️ Environment Variables

```env
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=openrouter/free

DATABASE_URL=postgresql://username:password@host:port/database
REDIS_URL=redis://username:password@host:port

JWT_SECRET=replace_with_a_long_random_secret

RAG_EMBEDDING_MODEL=nvidia/llama-nemotron-embed-vl-1b-v2:free
ADMIN_USERNAMES=your_admin_username

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email@gmail.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false

SENTRY_DSN=your_sentry_dsn
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1

MAX_UPLOAD_BYTES=10485760
MAX_REQUEST_BYTES=12582912
ALLOWED_ORIGINS=https://your-domain.com,http://127.0.0.1:8000

DAILY_CHAT_LIMIT=50
DAILY_RAG_UPLOAD_LIMIT=10
DAILY_RAG_ASK_LIMIT=30
DAILY_URL_READER_LIMIT=20
```

> Never commit API keys, SMTP passwords, JWT secrets, database credentials, Redis credentials, or Sentry DSNs to GitHub.

---

## 📦 Installation

```bash
git clone https://github.com/huzaifa-tanveer/my_ai_agent.git
cd my_ai_agent
```

### Windows virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Main dependencies:

```text
fastapi
uvicorn
openai
python-dotenv
python-multipart
pydantic
pandas
ddgs
pypdf
bcrypt
PyJWT
SQLAlchemy
psycopg[binary]
reportlab
redis
sentry-sdk[fastapi]
```

---

## ▶️ Run Locally

```powershell
uvicorn app:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

Healthy response:

```json
{"status":"ok"}
```

---

## 🗄 PostgreSQL

The application stores:
- Users
- Chats
- Messages
- Saved memories
- Email verification codes
- Password reset codes
- RAG documents
- RAG chunks
- Embeddings
- Daily usage events

---

## ⚡ Redis Rate Limiting

Redis is the primary rate-limit store so rate limits work across app instances.

Railway variable:

```env
REDIS_URL=${{Redis.REDIS_URL}}
```

If Redis is temporarily unavailable, the app falls back to an in-memory limiter.

---

## 📊 Daily Usage Endpoint

```text
GET /usage
```

The frontend displays current usage and remaining quota inside **Profile / Settings**.

---

## 🩺 Health Check

```text
GET /health
```

Healthy response:

```json
{"status":"ok"}
```

Database failures return a generic error response without exposing raw exception details.

---

## 📡 Sentry Monitoring

Configure:

```env
SENTRY_DSN=your_sentry_dsn
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

The backend reports unexpected production errors to Sentry with default PII sending disabled.

---

## 💾 Database Backups

The repository includes:

```text
backup_my_ai_agent.ps1
```

The script:
- Reads Railway's public PostgreSQL URL at runtime
- Creates timestamped custom-format dumps
- Stores backups locally
- Deletes backups older than 14 days

A Windows Task Scheduler job can run the script daily.

> Local scheduled backups depend on the configured Windows machine/task environment being available. For higher-reliability production use, use managed/offsite backups.

---

## 📚 RAG Usage

1. Log in.
2. Open **Documents / RAG**.
3. Upload a TXT, CSV, or text-based PDF.
4. Wait for processing.
5. Select one document or search all documents.
6. Enter a question.
7. Relevant chunks are retrieved.
8. The LLM generates a grounded answer.

Reindex existing chunks:

```text
POST /rag/reindex
```

---

## 🔌 Main API Endpoints

### Authentication
```text
POST /register
POST /login
POST /verify-email
POST /resend-verification-code
POST /forgot-password
POST /reset-password
```

### Account
```text
GET    /profile
POST   /change-password
DELETE /account
GET    /usage
```

### Memories
```text
GET    /memories
POST   /memories
PUT    /memories/{memory_id}
DELETE /memories/{memory_id}
```

### Chats
```text
POST   /chats
GET    /chats
GET    /chats/{chat_id}
PATCH  /chats/{chat_id}/title
DELETE /chats/{chat_id}
POST   /chat
POST   /chat/stream
POST   /chats/{chat_id}/regenerate
```

### Chat Export
```text
GET /chats/{chat_id}/export/txt
GET /chats/{chat_id}/export/pdf
```

### Files
```text
POST /upload
```

### RAG
```text
POST   /rag/upload
GET    /rag/documents
DELETE /rag/documents/{document_id}
POST   /rag/ask
POST   /rag/reindex
```

### URL Reader
```text
POST /url/ask
```

### Admin
```text
GET /admin/status
GET /admin/stats
GET /admin/users
GET /admin/users/{username}
GET /admin/analytics
```

### System
```text
GET /health
GET /
```

---

## 🚀 Railway Deployment

1. Connect the GitHub repository to Railway.
2. Add PostgreSQL.
3. Add Redis.
4. Configure production environment variables.
5. Use the start command:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

Railway automatically redeploys when new commits are pushed to the connected branch.

---

## 🧪 Production Checklist

```text
✓ Registration and email verification
✓ Login / logout
✓ Forgot/reset password
✓ Normal and streaming chat
✓ Persistent chat history
✓ Rename/delete/search chat
✓ Regenerate response
✓ File upload and TXT/CSV/PDF reading
✓ RAG upload / ask / delete / reindex
✓ URL Reader
✓ Memory create/update/delete
✓ Daily Usage dashboard
✓ TXT/PDF chat export
✓ Dark mode and mobile layout
✓ Admin Dashboard / user search / analytics
✓ Privacy Policy / Terms
✓ Redis connection
✓ Sentry monitoring
✓ /health response
✓ Database backup
```

---

## ⚠️ Current Limitations

- Scanned PDFs without extractable text require OCR before the current RAG reader can use them.
- Some websites block automated URL fetching.
- AI availability depends on the configured OpenRouter provider/model.
- Free model endpoints may impose rate or quota limits.
- Local scheduled database backups depend on the configured Windows machine being available.

---

## 👨‍💻 Author

**Huzaifa Tanveer**  
AI / Python Developer

GitHub:  
https://github.com/huzaifa-tanveer

---

## 📄 License

This project is currently provided for **educational, portfolio, and development purposes**.

Add a formal open-source license such as MIT before distributing or accepting external contributions under an open-source license.
