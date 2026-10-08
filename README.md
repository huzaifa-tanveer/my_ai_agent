# 🤖 My AI Agent

A full-stack AI assistant built with **FastAPI, PostgreSQL, OpenRouter, and vanilla JavaScript**.

The application provides real-time AI chat, persistent conversations, long-term memory, document-based RAG, URL analysis, file tools, authentication, email verification, an admin dashboard, analytics, and security protections.

## 🌐 Live Application

**Production:**  
https://myaiagent-production-649a.up.railway.app

## ✨ Features

### 💬 AI Chat

- Real-time streaming AI responses
- Multiple chat conversations
- Persistent chat history
- Rename chats
- Delete chats
- Search chats
- Regenerate AI responses
- Stop generation
- Copy responses
- Export conversations as TXT
- Export conversations as PDF

### 🧠 Smart Memory

The assistant can store long-term user information in PostgreSQL.

Users can:

- Create memories
- Update memories
- Delete memories
- View saved memories
- Use saved context in future conversations

### 📚 Retrieval-Augmented Generation (RAG)

Users can upload private knowledge documents and ask questions about them.

Supported files:

- TXT
- CSV
- Text-based PDF

RAG pipeline:

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
Semantic + Keyword Retrieval
      ↓
Top Relevant Chunks
      ↓
OpenRouter LLM
      ↓
Grounded Answer
```

The retrieval system uses **hybrid retrieval**:

```text
75% Semantic Similarity
25% Keyword Similarity
```

If the embedding service is temporarily unavailable, the application can fall back to keyword-based retrieval.

### 🌐 Website / URL Reader

Users can provide a public webpage URL and:

- Summarize the webpage
- Ask questions about its content
- Generate answers grounded in the webpage

Private/local network URLs are blocked for security.

### 📎 File Tools

The AI assistant can work with uploaded:

- TXT files
- CSV files
- PDF files

Uploaded files are isolated per user.

### 🛠 AI Tools

The agent includes callable tools for:

- Calculator operations
- Current date/time
- Web search
- Memory storage
- Memory retrieval
- TXT reading
- CSV reading
- PDF reading
- Website reading

### 🔐 Authentication

Authentication includes:

- Account registration
- Password hashing with bcrypt
- JWT authentication
- Email verification
- Verification-code resend
- Forgot password
- Email password reset
- Password change
- Account deletion

### 📧 Email

SMTP is used for:

- Account verification codes
- Password reset codes

### 🛡 Admin Dashboard

Configured administrators receive access to a private admin dashboard.

Admin features include:

- Total users
- Verified users
- Total chats
- Total messages
- RAG document count
- Saved memory count
- User search
- Detailed user information
- User chat statistics
- User RAG statistics
- Recent chats

### 📊 Usage Analytics

The admin dashboard includes 7-day analytics for:

- New users
- New chats
- New messages
- Daily activity
- Recent platform activity

### 🌙 User Interface

- Light mode
- Dark mode
- Responsive mobile layout
- Mobile sidebar
- Loading states
- Streaming indicators
- Document management modal
- URL Reader modal
- Settings panel
- Admin panel
- Keyboard shortcuts
- File-size validation

## 🔒 Security

The project includes several security protections:

- bcrypt password hashing
- JWT authentication
- User ownership checks
- Admin authorization
- Email verification
- Password reset tokens/codes
- Restricted CORS
- API rate limiting
- Request-size protection
- File upload-size limits
- User-isolated file access
- Safer server error messages
- Security response headers
- SSRF protection for URL Reader
- Private/localhost URL blocking

The default maximum upload size is:

```text
10 MB
```

## 🧰 Tech Stack

### Backend

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
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

### Deployment

- Railway
- PostgreSQL
- GitHub

## 📁 Project Structure

A simplified project structure:

```text
my_ai_agent/
│
├── app.py
├── index.html
├── requirements.txt
├── .env
├── .gitignore
│
├── uploads/
│
└── README.md
```

The `uploads/` directory contains user-uploaded files during application runtime.

## ⚙️ Environment Variables

Create a `.env` file in the project root.

Example:

```env
OPENROUTER_API_KEY=your_openrouter_api_key

DATABASE_URL=postgresql://username:password@host:port/database

JWT_SECRET=replace_with_a_long_random_secret

OPENROUTER_MODEL=openrouter/free

RAG_EMBEDDING_MODEL=nvidia/llama-nemotron-embed-vl-1b-v2:free

ADMIN_USERNAMES=your_admin_username

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email@gmail.com

SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

Security configuration can also be controlled through environment variables such as:

```env
MAX_UPLOAD_BYTES=10485760
MAX_REQUEST_BYTES=12582912

ALLOWED_ORIGINS=https://your-domain.com,http://127.0.0.1:8000
```

> Never commit `.env`, API keys, SMTP passwords, JWT secrets, or database credentials to GitHub.

## 📦 Installation

Clone the repository:

```bash
git clone https://github.com/huzaifa-tanveer/my_ai_agent.git
```

Enter the project:

```bash
cd my_ai_agent
```

Create a virtual environment:

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

## 📋 Main Dependencies

The project uses:

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
```

## 🗄 PostgreSQL Setup

Set the PostgreSQL connection string:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE
```

SQLAlchemy initializes the database models when the application starts.

The application stores data including:

- users
- chats
- messages
- memories
- email verification codes
- password reset codes
- RAG documents
- RAG chunks
- document embeddings

## ▶️ Run Locally

Start the FastAPI server:

```powershell
uvicorn app:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Health endpoint:

```text
http://127.0.0.1:8000/health
```

## 🔑 Admin Setup

Add your username to:

```env
ADMIN_USERNAMES=yourusername
```

Multiple admins can be separated by commas:

```env
ADMIN_USERNAMES=user1,user2,user3
```

Restart/redeploy the application after changing environment variables.

## 📚 RAG Usage

1. Login to the application.
2. Open **Documents / RAG**.
3. Upload a TXT, CSV, or PDF document.
4. Wait for processing.
5. Select a specific document or search all documents.
6. Enter a question.
7. The system retrieves relevant document chunks.
8. The LLM generates a grounded answer.

Existing RAG chunks can also be reindexed with embeddings through:

```text
POST /rag/reindex
```

## 🔌 Main API Endpoints

### Authentication

```text
POST   /register
POST   /login
POST   /verify-email
POST   /resend-verification-code
POST   /forgot-password
POST   /reset-password
```

### Account

```text
GET    /profile
POST   /change-password
DELETE /account
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

### File Upload

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

## 🚀 Railway Deployment

### 1. Push the project to GitHub

```powershell
git add .
git commit -m "Prepare production deployment"
git push
```

### 2. Create Railway Project

Create a Railway service connected to the GitHub repository.

### 3. Add PostgreSQL

Add a PostgreSQL service to the Railway project.

Set:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

### 4. Add Environment Variables

Configure:

```text
OPENROUTER_API_KEY
JWT_SECRET
DATABASE_URL
OPENROUTER_MODEL
RAG_EMBEDDING_MODEL
ADMIN_USERNAMES
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASSWORD
SMTP_FROM
SMTP_USE_TLS
SMTP_USE_SSL
ALLOWED_ORIGINS
```

### 5. Start Command

Use:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

Railway will automatically redeploy whenever new commits are pushed to the connected branch.

## 🩺 Health Check

The backend provides:

```text
GET /health
```

A healthy server should return a response indicating that the application and PostgreSQL database are available.

## 🧠 System Architecture

```text
                         ┌──────────────────┐
                         │      User        │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ HTML/CSS/JS UI   │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │     FastAPI      │
                         └────────┬─────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
              ▼                   ▼                   ▼
      ┌───────────────┐   ┌──────────────┐   ┌───────────────┐
      │  PostgreSQL   │   │  OpenRouter  │   │ External Web  │
      │               │   │              │   │ / DDGS Search │
      │ Users         │   │ Chat LLM     │   └───────────────┘
      │ Chats         │   │ Embeddings   │
      │ Messages      │   └──────────────┘
      │ Memory        │
      │ RAG Chunks    │
      │ Embeddings    │
      └───────────────┘
```

## 🧪 Recommended Production Tests

Before releasing a new version, test:

```text
✓ Registration
✓ Email verification
✓ Login
✓ Forgot password
✓ Password reset
✓ Normal chat
✓ Streaming chat
✓ Chat history
✓ Regenerate response
✓ File upload
✓ TXT reading
✓ CSV reading
✓ PDF reading
✓ RAG upload
✓ Semantic RAG question
✓ RAG delete
✓ URL Reader
✓ Memory create/update/delete
✓ Chat export TXT
✓ Chat export PDF
✓ Dark mode
✓ Mobile layout
✓ Admin Dashboard
✓ Admin User Search
✓ Admin Analytics
✓ Logout
```

## ⚠️ Notes

- Scanned PDFs without extractable text require OCR before they can be used by the current RAG document reader.
- AI availability depends on the configured OpenRouter model/provider.
- Free model endpoints may have rate limits.
- Never place production secrets directly inside source code.

## 👨‍💻 Author

**Huzaifa Tanveer**

AI / Python Developer

GitHub:  
https://github.com/huzaifa-tanveer

## 📄 License

This project is currently provided for educational, portfolio, and development purposes.

Add a formal open-source license such as MIT if you plan to distribute the project publicly.