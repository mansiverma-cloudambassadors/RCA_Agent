### ClassicBrain – RCA RAG Agent 🚀🧠

This project is a **powerful, conversational AI agent** designed to help engineers perform **Root Cause Analysis (RCA)**. It uses a **Retrieval-Augmented Generation (RAG) architecture**, combining the power of **Google's Gemini Pro** with a private knowledge base of past RCA documents stored in **Google Cloud Storage**.

The agent features a **modern, streaming web interface** built with React and is powered by a **scalable FastAPI backend**, fully containerized with Docker and ready for deployment on **Google Cloud Run**.

---

### ✨ Key Features

* **Conversational Q\&A**: Ask natural language questions about your knowledge base (e.g., *"How many RCAs do we have?"*, *"Give me details about the DrinkPrime incident"*).
* **Specialist Problem-Solver**: Describe a new technical issue, and the agent uses semantic vector search to find similar past incidents and recommend a detailed solution.
* **Hybrid AI Router**: Intelligently determines user intent to switch between being a general knowledge assistant and a specialist problem-solver.
* **Modern Web UI**: A Gemini-inspired interface built with React, featuring streaming responses, session management (create/delete/rename), and Markdown rendering with code highlighting.
* **Cloud-Native & Scalable**: A fully Dockerized backend ready for serverless deployment on Google Cloud Run with a CI/CD pipeline from GitHub.
* **Automated Knowledge Base**: Automatically syncs, parses, and indexes documents (`.txt`, `.md`, `.pdf`, `.docx`) from a Google Cloud Storage bucket.

---

### 🛠️ Tech Stack

* **Backend**: Python, FastAPI, Uvicorn, Google Generative AI (Gemini), ChromaDB (Vector Store), SQLite
* **Frontend**: React, JavaScript, Axios, React Markdown, Lucide React
* **Deployment**: Docker, Google Cloud Run, Google Artifact Registry, Google Cloud Build

---

### 📋 Prerequisites

Before you begin, ensure you have the following installed on your local machine:

* Python (3.9+)
* Node.js (v18+) and npm
* Docker Desktop
* Google Cloud SDK (gcloud)

---

### ⚙️ Configuration & Setup

#### **1. Google Cloud Project Setup**

* Create a new project in the Google Cloud Console.
* Enable Billing for the project.
* Enable the following APIs:

  * Artifact Registry API
  * Cloud Build API
  * Cloud Run Admin API
  * Vertex AI API (Gemini + Embedding models)
  * Cloud Storage API
  * Secret Manager API
* **Create a Service Account**:

  * Go to *IAM & Admin → Service Accounts*.
  * Click **Create Service Account**.
  * Grant roles:

    * Storage Admin
    * Vertex AI User
    * Secret Manager Secret Accessor
  * Download the JSON key.
* **Create a GCS Bucket**:

  * Create a new bucket for RCA documents.
  * Grant Service Account access.
  * Note bucket name (e.g., `rca-bucket`).

---

#### **2. Local Project Configuration**

* **Clone the Repository**:

  ```bash
  git clone https://github.com/your-username/your-repository-name.git
  cd your-repository-name
  ```

* **Place Service Account Key** inside `backend/` directory.

* **Set up Backend Environment**:

  ```bash
  cd backend
  python -m venv venv
  source venv/bin/activate   # Windows: venv\Scripts\activate
  pip install -r requirements.txt
  ```

* **Create `.env` file** in `backend/`:

  ```env
  GEMINI_API_KEY="your_actual_gemini_api_key_here"
  ```

* **Set up Frontend Environment**:

  ```bash
  cd ../frontend
  npm install
  ```

---

### 🚀 Running the Application Locally

* **Backend (Terminal 1)**:

  ```bash
  cd backend
  source venv/bin/activate
  uvicorn main:app --reload
  ```

  Runs at → [http://127.0.0.1:8000](http://127.0.0.1:8000)

* **Frontend (Terminal 2)**:

  ```bash
  npm start
  ```

  Opens at → [http://localhost:3000](http://localhost:3000)

---

### ▶️ Usage Workflow

1. **Sync Knowledge Base**:

   * Upload RCA docs (`.txt`, `.pdf`, `.docx`) to your GCS bucket.
   * Open → [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   * Run **POST /sync-gcs** endpoint.

2. **Start Chatting**:

   * Open frontend → [http://localhost:3000](http://localhost:3000)
   * Ask questions like *"Show me past network issues"*

---

### 🚢 Deployment to Google Cloud Run

1. **Push Code**: Commit + push code (with Dockerfile) to GitHub repo.
2. **Store Secrets**: Add Gemini API key to Secret Manager → `gemini-api-key`.
3. **Create Cloud Run Service**:

   * Deploy from GitHub repo → main branch.
   * Build type → Dockerfile.
   * Container Port → `8000`.
   * Add environment variable → `GEMINI_API_KEY` mapped to secret.
4. **Deploy** → Cloud Build will build + deploy automatically.

Your service will get a **public URL**, and every push to `main` will trigger redeployment 🚀

---

Would you like me to also **add badges** (like build passing, deploy to Cloud Run, made with Python/React) at the top so the README looks more professional for GitHub?

