# 🧠 E-Commerce Database Performance Analyzer Agent

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB_Atlas-47A248?style=for-the-badge&logo=mongodb&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini_AI-4285F4?style=for-the-badge&logo=google&logoColor=white)
![Groq](https://img.shields.io/badge/Groq_LLM-F55036?style=for-the-badge&logo=lightning&logoColor=white)

**A production-ready Agentic AI that understands natural language, queries your MongoDB database safely, and delivers real-time business insights — with full conversation memory.**

[API Docs](#-api-reference) · [Architecture](#-architecture) · [Scaling](#-scaling-guide)

</div>

---

## ✨ What It Does

Ask plain English questions about your e-commerce business. The AI Agent plans and executes safe read-only database queries, then generates structured insights with metrics, trends, and actionable recommendations.

```
"How much revenue did we generate this month?"
  → Intent detected: revenue | period: this_month
  → MongoDB aggregation: orders.aggregate([{$match...}, {$group...}])
  → ₹4,82,310 total revenue across 312 orders, up 14.2% vs last month

"Which products are underperforming this week?"
  → Intent detected: product_performance | period: this_week
  → Sorted by soldCount ASC with stock > 0
  → 8 products flagged with restocking recommendations

"Hi, explain the last result"
  → Conversational mode (no DB query)
  → Answers using session memory from previous turn
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     FRONTEND                            │
│     Vanilla JS + CSS  (served by FastAPI /static)       │
│  Session ID  ──►  POST /api/ask  ◄──  Admin Key Auth    │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP
┌────────────────────▼────────────────────────────────────┐
│                  FASTAPI BACKEND                         │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │           AGENT ORCHESTRATOR                     │   │
│  │                                                  │   │
│  │  ┌─────────────┐    ┌───────────────────────┐   │   │
│  │  │   Intent    │    │  ConversationalAgent   │   │   │
│  │  │  Detector   │───►│  (greetings/follow-ups)│   │   │
│  │  │  (Stage 1)  │    │  Session Memory ✓      │   │   │
│  │  └──────┬──────┘    └───────────────────────┘   │   │
│  │         │ analytics intent                       │   │
│  │  ┌──────▼──────┐                                │   │
│  │  │   Query     │  Structured JSON plan           │   │
│  │  │   Planner   │  (never raw DB code)            │   │
│  │  │  (Stage 2)  │  Security check ✓               │   │
│  │  └──────┬──────┘  No PII ✓                      │   │
│  │         │                                        │   │
│  │  ┌──────▼──────┐                                │   │
│  │  │   Query     │  MongoDB aggregations           │   │
│  │  │  Executor   │  Read-only ✓  Timeout ✓        │   │
│  │  │  (Stage 3)  │  Schema-validated ✓             │   │
│  │  └──────┬──────┘                                │   │
│  │         │                                        │   │
│  │  ┌──────▼──────┐                                │   │
│  │  │   Insight   │  Headline + Metrics +           │   │
│  │  │  Generator  │  Trend + Recommendations        │   │
│  │  │  (Stage 4)  │  No hallucinated numbers ✓      │   │
│  │  └─────────────┘                                │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  LLM Client (Groq ←→ Gemini auto-fallback on quota)     │
└────────────────────┬────────────────────────────────────┘
                     │ Motor (async)
┌────────────────────▼────────────────────────────────────┐
│              MONGODB ATLAS                               │
│  orders · products · users · payments                   │
└─────────────────────────────────────────────────────────┘
```

### Security by Design
| Threat | Protection |
|---|---|
| SQL/NoSQL injection | LLM outputs structured JSON plan, never raw queries |
| Write operations | Allowlist: only `aggregate`, `count`, `find_one`, `distinct` |
| PII exposure | `name`, `email`, `phone`, `password` blocked at schema level |
| Hallucinated metrics | Insight generator only uses actual DB result values |
| Unauth access | `X-Admin-Key` header required on all `/api/*` routes |

---

## 🚀 Quick Start (Local)

### Prerequisites
- Python 3.10+
- MongoDB Atlas account (free tier works)
- Groq API key (free) **or** Google Gemini API key

### 1. Clone & Install
```bash
git clone https://github.com/vansharora21/E-Commerce-Database-Performance-Analyzer-AGENT.git
cd E-Commerce-Database-Performance-Analyzer-AGENT
pip install -r requirements.txt
```

### 2. Configure `.env`
```env
# MongoDB Atlas (get from cloud.mongodb.com)
MONGODB_URI=mongodb+srv://user:password@cluster0.xxxx.mongodb.net/
DB_NAME=fashion_ecommerce

# LLM Provider — use "groq" (free, fast) or "gemini"
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx     # https://console.groq.com
GEMINI_API_KEY=AIzaSy_xxxxxxxxxxxxxxxxxxxx # https://aistudio.google.com

GEMINI_MODEL=gemini-2.0-flash

# Security
ADMIN_API_KEY=your-strong-secret-here

# Server
HOST=0.0.0.0
PORT=8000
```

### 3. Seed Database
```bash
python scripts/seed_database.py
# Creates: 200 users, 150 products, 1200 orders, payments
```

### 4. Start Server
```bash
python main.py
```
Open **http://localhost:8000** — dashboard loads instantly.

---

## 📦 Project Structure

```
.
├── main.py                        # FastAPI app entry point
├── requirements.txt
├── .env                           # Your secrets (never commit this)
├── .env.example                   # Template
│
├── config/
│   ├── settings.py                # Pydantic-Settings env config
│   └── database.py                # Async Motor/MongoDB connection
│
├── models/
│   └── schemas.py                 # All Pydantic schemas (null-tolerant)
│
├── agent/
│   ├── orchestrator.py            # Master router: chat vs analytics
│   ├── intent_detector.py         # Stage 1: NL → structured intent
│   ├── query_planner.py           # Stage 2: intent → safe query plan
│   ├── query_executor.py          # Stage 3: plan → MongoDB execution
│   ├── insight_generator.py       # Stage 4: raw data → business insight
│   ├── conversational_agent.py    # Handles greetings & follow-ups
│   ├── conversation_manager.py    # In-memory session store (30min TTL)
│   └── llm_client.py              # Unified Groq/Gemini client w/ fallback
│
├── api/
│   ├── routes.py                  # All endpoints
│   └── middleware.py              # Auth + timing middleware
│
├── frontend/
│   ├── index.html                 # Dashboard shell
│   ├── style.css                  # Dark glass design system
│   └── app.js                     # API calls, rendering, session
│
└── scripts/
    ├── seed_database.py           # Realistic fake data generator
    └── test_agent.py              # CLI smoke tests
```

---

## 🌐 Deployment (Fast & Free)

### Option 1 — Koyeb 🔥 (Best Free Tier, No Sleeping)
Koyeb provides an always-on free tier that perfectly supports Python deployments without 30s cold starts.

1. Go to [Koyeb.com](https://www.koyeb.com/)
2. Create an App and connect your GitHub repository
3. Koyeb will automatically detect the `Dockerfile` in this repo
4. Add your `.env` variables under the Environment Variables section
5. Deploy (your app will be live 24/7 on the free tier)

---

### Option 2 — Fly.io (Low Latency Edge)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Create app
fly auth login
fly launch --name ecommerce-agent --region sin   # Singapore for low India latency

# Set secrets
fly secrets set GROQ_API_KEY=gsk_xxx MONGODB_URI=mongodb+srv://... ADMIN_API_KEY=xxx LLM_PROVIDER=groq

# Deploy
fly deploy
```

*(Note: If using Railway or Render free tiers, expect the server to sleep after 15 mins of inactivity, resulting in a 30-60 second cold start on the first request).*

---

### Option 3 — Docker (Self-host / VPS)

```bash
# Build
docker build -t ecommerce-agent .

# Run
docker run -d \
  --name ecommerce-agent \
  -p 8000:8000 \
  --env-file .env \
  ecommerce-agent
```

For **Nginx reverse proxy** on a ₹500/mo VPS (DigitalOcean, Hetzner, Hostinger):
```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## ⚡ Scaling Guide

### Current Architecture (MVP — handles ~50 concurrent users)

| Component | Current | Bottleneck |
|---|---|---|
| FastAPI | Single process | CPU-bound at ~100 RPS |
| MongoDB | Atlas M0 (free) | 512MB RAM, shared cluster |
| LLM | Groq free (30 RPM) | Rate limiting |
| Sessions | In-memory dict | Lost on restart |

---

### Scale Layer 1 — Small Team (up to 500 users/day)

**Cost: ~$20-40/month**

```bash
# Run multiple uvicorn workers
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# Or with gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

- Upgrade MongoDB Atlas to **M10** (~$57/mo) — dedicated cluster, indexes
- Add MongoDB indexes (the agent suggests them in responses):
  ```javascript
  db.orders.createIndex({ createdAt: -1 })
  db.orders.createIndex({ status: 1, createdAt: -1 })
  db.products.createIndex({ soldCount: -1 })
  ```

---

### Scale Layer 2 — Growing Startup (up to 5,000 users/day)

**Cost: ~$100-200/month**

1. **Replace in-memory sessions with Redis:**
   ```python
   # pip install redis[asyncio]
   # Store conversation_manager sessions in Redis with TTL
   import redis.asyncio as redis
   r = redis.from_url(os.getenv("REDIS_URL"))
   ```

2. **Add a task queue for slow queries:**
   ```python
   # pip install celery[redis]
   # Move DB-heavy queries to async Celery workers
   # Return job_id immediately, frontend polls for result
   ```

3. **Response caching for repeat questions:**
   ```python
   # Cache identical questions for 5 minutes in Redis
   cache_key = hashlib.md5(question.encode()).hexdigest()
   cached = await r.get(cache_key)
   if cached: return json.loads(cached)
   ```

4. **Rate limiting per user:**
   ```python
   # pip install slowapi
   from slowapi import Limiter
   limiter = Limiter(key_func=get_remote_address)
   @router.post("/api/ask")
   @limiter.limit("20/minute")
   async def ask_agent(...):
   ```

5. Use **Groq paid tier** or **Gemini 1.5 Pro** for higher throughput

---

## 📡 API Reference

### `POST /api/ask`
Submit a natural language question.

**Headers:**
```
Content-Type: application/json
X-Admin-Key: your-admin-key
```

**Body:**
```json
{
  "question": "How much revenue did we generate this month?",
  "session_id": "session_abc123"
}
```

**Response:**
```json
{
  "question": "How much revenue did we generate this month?",
  "intent": "revenue",
  "time_period": "this_month",
  "is_conversational": false,
  "insight": {
    "headline": "₹4.8L revenue across 312 orders this month",
    "summary": "Total revenue this month is ₹4,82,310...",
    "key_metrics": [
      { "label": "Total Revenue", "value": 482310, "unit": "₹", "change_pct": 14.2 }
    ],
    "trend": { "direction": "up", "change_pct": 14.2, "period_label": "vs last month" },
    "recommendations": ["Consider flash sale on slow-moving inventory"],
    "chart_hint": "bar"
  },
  "execution_time_ms": 3240,
  "pipeline_steps": [
    "[1] Intent: revenue (this_month) conf=97%",
    "[2] Plan: orders.aggregate safety=OK",
    "[3] DB: 1 rows in 180ms",
    "[4] Insight generated"
  ]
}
```

### Other Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | ❌ | DB ping + status |
| `GET` | `/api/schema` | ❌ | DB schema overview |
| `GET` | `/api/sample-questions` | ❌ | Suggested questions |
| `GET` | `/api/history` | ❌ | Last 50 sessions |
| `GET` | `/docs` | ❌ | Swagger UI |

---

## 🛠️ Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `MONGODB_URI` | ✅ | — | Atlas connection string |
| `DB_NAME` | ✅ | `fashion_ecommerce` | Database name |
| `LLM_PROVIDER` | ✅ | `groq` | `groq` or `gemini` |
| `GROQ_API_KEY` | ✅ (if groq) | — | From console.groq.com |
| `GEMINI_API_KEY` | ✅ (if gemini) | — | From aistudio.google.com |
| `GEMINI_MODEL` | ❌ | `gemini-2.0-flash` | Model name |
| `ADMIN_API_KEY` | ✅ | — | Dashboard auth key |
| `HOST` | ❌ | `0.0.0.0` | Server host |
| `PORT` | ❌ | `8000` | Server port |
| `AGENT_MAX_RETRIES` | ❌ | `3` | LLM retry attempts |
| `AGENT_TEMPERATURE` | ❌ | `0.1` | LLM temperature (lower = more deterministic) |

---

## 💡 Sample Questions by Category

<details>
<summary><strong>💰 Revenue & Sales</strong></summary>

- How much revenue did we generate this week?
- What was our total revenue last month?
- Compare this week's revenue vs last week
- What is our average order value this month?
- How did our sales compare this quarter vs last quarter?
</details>

<details>
<summary><strong>📦 Orders</strong></summary>

- How many orders were placed today?
- What are the pending orders this month?
- How many orders were cancelled this week?
- Show me the order status breakdown
- What percentage of orders are delivered vs pending?
</details>

<details>
<summary><strong>👗 Products</strong></summary>

- Which products are underperforming this month?
- What are our top 5 best-selling products?
- Which product categories generate the most revenue?
- How many products are low on stock?
- What is the average rating of our shoe category?
</details>

<details>
<summary><strong>👥 Customers</strong></summary>

- How many new customers signed up this month?
- What percentage of customers are gold or platinum tier?
- Which city has the most orders?
- How many active customers do we have?
</details>

<details>
<summary><strong>💳 Payments</strong></summary>

- What is the most popular payment method this month?
- How many payments failed this week?
- What is the UPI vs card payment split?
- How much revenue was lost to refunds?
</details>

---

## 🧪 Testing

```bash
# Run the smoke test script
python scripts/test_agent.py

# Quick single question test
python scripts/quick_test.py

# Manual API test (PowerShell)
$headers = @{ "Content-Type"="application/json"; "X-Admin-Key"="YOUR_API_KEY" }
$body = '{"question":"How much revenue this month?","session_id":"test"}'
Invoke-RestMethod -Uri "http://localhost:8000/api/ask" -Method Post -Headers $headers -Body $body
```

---

## 🔒 Security Checklist for Production

- [ ] Change `ADMIN_API_KEY` to a strong random string (`openssl rand -hex 32`)
- [ ] Enable MongoDB Atlas IP Allowlist (only your server IP)
- [ ] Put the API behind HTTPS
- [ ] Set `DEBUG=false` in production
- [ ] Rotate Groq/Gemini API keys regularly
- [ ] Add rate limiting (see Scale Layer 2)
- [ ] Never commit `.env` to git (add to `.gitignore`)

---

## 📈 Portfolio Highlights

This project demonstrates:

| Skill | Implementation |
|---|---|
| **Agentic AI Design** | 4-stage pipeline: Intent → Plan → Execute → Insight |
| **LLM Engineering** | Structured JSON prompting, hallucination prevention, multi-provider fallback |
| **Backend Architecture** | FastAPI, async Motor, Pydantic v2, middleware chains |
| **Database Engineering** | MongoDB aggregation pipelines, read-only security, schema validation |
| **Security** | API key auth, PII blocking, allowlist-based query execution |
| **Conversation AI** | Session memory, intent routing, follow-up context |
| **Full-Stack** | Dark glass dashboard, real-time pipeline trace, chat UX |
| **Production Readiness** | Retry logic, graceful errors, quota handling, multi-LLM fallback |

---

## 🤝 Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI + Uvicorn |
| Database Driver | Motor (async PyMongo) |
| AI — Primary | Google Gemini 2.0 Flash |
| AI — Fallback | Groq |
| Data Validation | Pydantic v2 |
| Config | pydantic-settings |
| Frontend | Vanilla HTML/CSS/JS |
| Database | MongoDB Atlas |

---

## 📄 License

MIT — free to use, modify, and deploy.

---

<div align="center">

**Built with ❤️ as a production-grade AI × Database Engineering portfolio project.**

*Star ⭐ the repo if you found it useful!*

</div>

# E-Commerce-Database-Performance-Analyzer-AGENT