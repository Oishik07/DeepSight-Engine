# 🚀 DeepSight Engine

> **A production-grade Agentic Deep Research Engine built with LangGraph that autonomously plans, researches, critiques, and generates citation-backed research reports using multiple collaborating AI agents.**

---

# 🏗️ System Architecture

> The architecture below illustrates the complete end-to-end workflow of DeepSight Engine.

<p align="center">
    <img src="docs/system-design.png" alt="DeepSight Engine Architecture" width="1000"/>
</p>

---

## ✨ Key Features

- 🧠 Dynamic query decomposition using a dedicated **Planner Agent**
- 🔎 Autonomous multi-step web research with **Researcher Agent**
- 📝 Structured report generation with **Reporter Agent**
- 🧐 Quality evaluation through a **Critic Agent**
- ✍️ Automatic refinement using an **Editor Agent**
- 🌐 Multi-provider **LLM Gateway** (Llama, OpenAI & Claude)
- ⚡ Real-time progress streaming via **Server-Sent Events (SSE)**
- 🧠 Redis Semantic Caching for repeated and semantically similar queries
- 📄 PDF & DOCX report export
- 📊 Usage tracking and API key management
- 🚀 Production-ready FastAPI backend

---

# 🤖 Multi-Agent Workflow

Unlike a traditional chatbot that relies on a single LLM response, DeepSight Engine orchestrates multiple specialized AI agents.

### 🧠 Planner Agent
- Understands the user's objective
- Breaks complex queries into dynamic research objectives
- Creates an execution strategy

### 🔎 Researcher Agent
- Executes one research objective at a time
- Performs iterative web research
- Collects and consolidates evidence

### 📝 Reporter Agent
- Synthesizes collected information
- Generates a structured research report

### 🧐 Critic Agent
- Evaluates report quality
- Detects missing information
- Decides whether refinement is required

### ✍️ Editor Agent
- Improves weak sections
- Refines report quality
- Produces the final polished output

---

# 🔀 LLM Gateway

DeepSight includes an intelligent LLM Gateway supporting multiple providers.

Supported Providers

- Llama
- OpenAI
- Claude

Capabilities

- Smart model routing
- API key management
- Usage tracking
- Provider abstraction

---

# ⚡ Technology Stack

## Backend

- FastAPI
- Python
- LangGraph
- LangChain

## AI

- OpenAI
- Claude
- Llama
- Tavily Search API

## Databases

- PostgreSQL
- Redis

## Infrastructure

- Server-Sent Events (SSE)
- Docker
- Render

---

# 🔄 Workflow

```text
User Query
      │
      ▼
Planner Agent
      │
      ▼
Dynamic Research Plan
      │
      ▼
Researcher Agent
      │
      ▼
Web Search (Tavily)
      │
      ▼
Reporter Agent
      │
      ▼
Critic Agent
      │
      ▼
Editor Agent
      │
      ▼
Citation-backed Research Report
```

---

# 🚀 Why DeepSight?

Traditional AI chatbots usually perform a single LLM call.

DeepSight instead follows a production-style multi-agent workflow where specialized agents collaborate to:

- Plan
- Research
- Verify
- Critique
- Refine

This produces more comprehensive, citation-backed reports while keeping the architecture modular and extensible.

---

# ⚙️ Running Locally

Clone the repository

```bash
git clone https://github.com/<your-username>/DeepSight-Engine.git
```

Navigate into the project

```bash
cd DeepSight-Engine
```

Install dependencies

```bash
pip install -r requirements.txt
```

Create a `.env` file

```env
LLAMA_API_KEY=
OPENAI_API_KEY=
CLAUDE_API_KEY=
TAVILY_API_KEY=
DATABASE_URL=
REDIS_URL=
```

Run the application

```bash
uvicorn app.main:app --reload
```

Open

```
http://localhost:8000
```

---

# 👨‍💻 Author

**Oishik Bandyopadhyay**

AI Engineer • GenAI • Agentic AI • LangGraph • LLM Engineering

---

⭐ If you found this project interesting, consider giving it a star!
