import os
import json
import sqlite3
import re
import uuid
import tempfile
from datetime import datetime
from pathlib import Path
import google.generativeai as genai
from google.cloud import storage
from typing import List, Dict, Any

# Third-party libraries
import chromadb
from docx import Document
import PyPDF2

# Constants
GCS_BUCKET_NAME = "rca-bucket"
SERVICE_ACCOUNT_PATH = "agentspace-cloudambassadors-15d3494c755b.json"


class AdvancedRCAKnowledgeBase:
    """
    An advanced RCA system using vector embeddings for semantic search and
    a robust RAG pipeline for generating expert recommendations.
    """
    def __init__(self, api_key: str):
        try:
            # Configure Gemini API
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            self.embedding_model = 'models/text-embedding-004'

            # Initialize GCS client
            self.client = storage.Client.from_service_account_json(SERVICE_ACCOUNT_PATH)
            self.bucket = self.client.bucket(GCS_BUCKET_NAME)

            # Initialize SQLite database for metadata
            self.db_path = "rca_knowledge_base.db"
            self.init_database()

            # Initialize Vector Database (ChromaDB) for embeddings
            self.chroma_client = chromadb.PersistentClient(path="./chroma_db")
            self.collection = self.chroma_client.get_or_create_collection(name="rca_documents")

        except Exception as e:
            raise RuntimeError(f"Failed to initialize Advanced RCA Knowledge Base: {e}")

    def init_database(self):
        """Initializes the SQLite database schema for RCA metadata and chat history."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # RCA Documents Table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS rca_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                gcs_path TEXT NOT NULL,
                project_name TEXT,
                problems TEXT,
                solutions TEXT,
                root_causes TEXT,
                lessons_learned TEXT,
                full_content TEXT,
                file_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            # Chat Sessions Table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            # Chat Messages Table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                message_type TEXT CHECK(message_type IN ('user', 'assistant')),
                content TEXT,
                matched_rcas TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
            )''')
            conn.commit()

    def _get_embedding(self, text: str) -> List[float]:
        """Generates embedding for a given text using the specified model."""
        return genai.embed_content(model=self.embedding_model, content=text)["embedding"]

    def extract_rca_content_from_bytes(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Extracts structured content from file bytes.
        Handles various file formats like .txt, .md, .docx, and .pdf.
        """
        content = ""
        file_ext = Path(filename).suffix.lower()

        try:
            if file_ext in ['.txt', '.md']:
                content = file_content.decode('utf-8', errors='ignore')
            elif file_ext == '.docx':
                with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                    tmp.write(file_content)
                    tmp_path = tmp.name
                doc = Document(tmp_path)
                content = '\n'.join([para.text for para in doc.paragraphs])
                os.remove(tmp_path)
            elif file_ext == '.pdf':
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(file_content)
                    tmp_path = tmp.name
                with open(tmp_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    content = '\n'.join([page.extract_text() for page in reader.pages])
                os.remove(tmp_path)
            else:
                return None # Unsupported file type

            # Use Gemini to extract structured information
            extraction_prompt = f"""
            Analyze the following RCA document content and extract structured information.
            Return ONLY a valid JSON object with the specified keys.

            Document Content:
            {content[:8000]}  # Limit content to avoid token limits

            JSON format to extract:
            {{
                "project_name": "string",
                "problems": ["list of identified problems"],
                "solutions": ["list of applied solutions"],
                "root_causes": ["list of root causes"],
                "lessons_learned": ["list of key lessons learned"]
            }}
            """
            response = self.model.generate_content(extraction_prompt)
            # Clean up the response to get only the JSON part
            json_text = re.search(r'```json\n(\{.*?\})\n```', response.text, re.DOTALL)
            if json_text:
                extracted_data = json.loads(json_text.group(1))
            else: # Fallback for plain JSON output
                extracted_data = json.loads(response.text)

            return {
                "filename": filename,
                "full_content": content,
                "extracted_data": extracted_data
            }

        except Exception as e:
            print(f"Error processing file {filename}: {e}")
            return None

    def generate_general_response(self, query: str, stream: bool = False):
        """
        Answers general questions by providing the LLM with context from all RCAs.
        This version is corrected and safe.
        """
        all_rcas = self.get_all_rcas()
        if not all_rcas:
            return "The RCA knowledge base is currently empty."

        context = "Here is a summary of all the RCA documents in the knowledge base:\n\n"
        for rca in all_rcas:
            filename = rca.get('filename', 'N/A')
            project = rca.get('project_name', 'N/A')
            problems = ", ".join(rca.get('problems', []))
            solutions = ", ".join(rca.get('solutions', []))
            context += f"--- Document: {filename} ---\nProject: {project}\nProblems: {problems}\nSolutions: {solutions}\n\n"

        prompt = f"""You are a helpful and knowledgeable RCA assistant. Your task is to answer the user's question accurately based ONLY on the context provided below from the knowledge base. If the answer is not contained within the provided context, state that you do not have that specific information. --- KNOWLEDGE BASE CONTEXT --- {context[:25000]} --- USER'S QUESTION --- {query} --- YOUR ANSWER ---"""
        
        try:
            # This call now works because the `stream` variable is defined.
            response = self.model.generate_content(prompt, stream=stream)
            if stream:
                return response
            else:
                return response.text
        except Exception as e:
            print(f"ERROR during general response generation: {e}")
            return f"I encountered an issue while generating a response. The error was: {e}"
    
    def sync_gcs_files(self) -> Dict[str, int]:
        """
        Syncs files from GCS, stores metadata in SQLite, and creates embeddings in ChromaDB.
        """
        gcs_blobs = self.bucket.list_blobs()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT filename, file_hash FROM rca_documents')
            existing_files = {row[0]: row[1] for row in cursor.fetchall()}
        
        stats = {'processed': 0, 'updated': 0, 'skipped': 0, 'errors': 0}

        for blob in gcs_blobs:
            filename = os.path.basename(blob.name)
            file_hash = blob.md5_hash

            if existing_files.get(filename) == file_hash:
                stats['skipped'] += 1
                continue

            try:
                file_content = blob.download_as_bytes()
                rca_data = self.extract_rca_content_from_bytes(file_content, filename)
                if not rca_data:
                    stats['errors'] += 1
                    continue
                
                ext_data = rca_data['extracted_data']
                now_iso = datetime.now().isoformat()

                # Upsert metadata into SQLite
                cursor.execute('''
                    INSERT INTO rca_documents (filename, gcs_path, project_name, problems, solutions, root_causes, lessons_learned, full_content, file_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(filename) DO UPDATE SET
                    gcs_path=excluded.gcs_path, project_name=excluded.project_name, problems=excluded.problems, solutions=excluded.solutions, root_causes=excluded.root_causes, lessons_learned=excluded.lessons_learned, full_content=excluded.full_content, file_hash=excluded.file_hash, updated_at=excluded.updated_at
                ''', (
                    filename, blob.name, ext_data.get('project_name'), json.dumps(ext_data.get('problems', [])),
                    json.dumps(ext_data.get('solutions', [])), json.dumps(ext_data.get('root_causes', [])),
                    json.dumps(ext_data.get('lessons_learned', [])), rca_data['full_content'], file_hash, now_iso, now_iso
                ))
                conn.commit()
                
                # Get the SQLite row ID for linking
                cursor.execute('SELECT id FROM rca_documents WHERE filename = ?', (filename,))
                doc_id = str(cursor.fetchone()[0])

                # Create a comprehensive text for embedding
                embedding_text = f"Project: {ext_data.get('project_name')}\nProblems: {', '.join(ext_data.get('problems',[]))}\nRoot Causes: {', '.join(ext_data.get('root_causes',[]))}\nSolutions: {', '.join(ext_data.get('solutions',[]))}"
                embedding = self._get_embedding(embedding_text)

                # Add/Update the document in the vector store
                self.collection.upsert(
                    ids=[doc_id],
                    embeddings=[embedding],
                    metadatas=[{"filename": filename, "project_name": ext_data.get('project_name')}]
                )
                
                if filename in existing_files:
                    stats['updated'] += 1
                else:
                    stats['processed'] += 1

            except Exception as e:
                print(f"Failed to sync {filename}: {e}")
                stats['errors'] += 1

        return stats

    def search_similar_problems(self, current_problem: str, top_n: int = 5) -> List[Dict[str, Any]]:
        """Searches for similar problems using vector embeddings for high accuracy."""
        query_embedding = self._get_embedding(current_problem)
        results = self.collection.query(query_embeddings=[query_embedding], n_results=top_n)

        if not results or not results.get('ids') or not results['ids'][0]:
            return []

        matched_ids = [int(id_str) for id_str in results['ids'][0]]
        distances = results['distances'][0]
        
        placeholders = ','.join('?' for _ in matched_ids)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f'SELECT id, filename, project_name, problems, solutions, root_causes FROM rca_documents WHERE id IN ({placeholders})', matched_ids)
            rca_map = {row[0]: row for row in cursor.fetchall()}

        similar_rcas = []
        for i, doc_id in enumerate(matched_ids):
            rca = rca_map.get(doc_id)
            if rca:
                similarity_score = max(0, (1 - distances[i])) * 100
                similar_rcas.append({
                    'rca_id': rca[0], 'filename': rca[1], 'project_name': rca[2],
                    'problems': json.loads(rca[3]), 'solutions': json.loads(rca[4]),
                    'root_causes': json.loads(rca[5]), 'similarity_score': round(similarity_score, 2)
                })
        return similar_rcas

    def generate_solution_recommendation(self, current_problem: str, similar_rcas: List[Dict[str, Any]]) -> str:
        """Generates an expert-level recommendation based on retrieved RCAs."""
        if not similar_rcas:
            return "No similar problems were found in the knowledge base. The knowledge base may need to be synced or expanded."

        prompt = f"""
        You are an expert Senior Site Reliability Engineer (SRE) and Root Cause Analysis specialist.
        Your task is to provide a comprehensive solution recommendation for a new problem based on historical RCA data.

        **Current Problem Description:**
        "{current_problem}"

        **Retrieved Similar Historical Incidents (ranked by relevance):**
        """
        for i, rca in enumerate(similar_rcas, 1):
            prompt += f"""
        ---
        **Incident #{i} (Similarity: {rca['similarity_score']:.2f}%)**
        - **File:** {rca['filename']}
        - **Project:** {rca['project_name']}
        - **Problem Summary:** {'; '.join(rca['problems'])}
        - **Identified Root Causes:** {'; '.join(rca['root_causes'])}
        - **Successful Solutions Applied:** {'; '.join(rca['solutions'])}
        """
        prompt += """
        ---
        **Your Analysis and Recommendations:**

        Based on your expert analysis of the current problem and the historical data provided, generate a structured response with the following sections:

        1.  **Problem Synopsis:** Briefly synthesize the user's current problem and explain *why* the retrieved incidents are relevant. Highlight the common themes.
        2.  **Top Recommended Solutions:** Provide a prioritized list of actionable solutions derived from the most successful historical data. For each solution, explain the reasoning behind its recommendation.
        3.  **Step-by-Step Implementation Plan:** For the #1 recommended solution, provide a clear, step-by-step guide for implementation.
        4.  **Potential Risks and Mitigation:** What are the potential risks of implementing the proposed solutions? Suggest ways to mitigate these risks.
        5.  **Further Investigation Questions:** What clarifying questions should be asked to get more context about the current problem? This will help refine the diagnosis.

        Format your response using Markdown for clarity and readability.
        """
        response = self.model.generate_content(prompt)
        return response.text

    # --- Chat and Data Management Methods ---
    def create_chat_session(self, title: str = None) -> str:
        session_id = str(uuid.uuid4())
        if not title:
            title = f"Chat Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO chat_sessions (id, title) VALUES (?, ?)', (session_id, title))
            conn.commit()
        return session_id

    def get_chat_sessions(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM chat_sessions ORDER BY updated_at DESC')
            return [dict(row) for row in cursor.fetchall()]
        
    def update_session_title(self, session_id: str, new_title: str):
        """Updates the title of a specific chat session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?',
                (new_title, datetime.now().isoformat(), session_id)
            )
            conn.commit()

    def get_chat_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM chat_messages WHERE session_id = ? ORDER BY timestamp ASC', (session_id,))
            messages = []
            for row in cursor.fetchall():
                msg = dict(row)
                if msg['matched_rcas']:
                    msg['matched_rcas'] = json.loads(msg['matched_rcas'])
                messages.append(msg)
            return messages

    def add_chat_message(self, session_id: str, message_type: str, content: str, matched_rcas: List[Dict] = None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            rcas_json = json.dumps(matched_rcas) if matched_rcas else None
            cursor.execute(
                'INSERT INTO chat_messages (session_id, message_type, content, matched_rcas) VALUES (?, ?, ?, ?)',
                (session_id, message_type, content, rcas_json)
            )
            cursor.execute('UPDATE chat_sessions SET updated_at = ? WHERE id = ?', (datetime.now().isoformat(), session_id))
            conn.commit()

    def get_rca_count(self) -> int:
        """A simple helper to get the total count of RCAs from the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM rca_documents')
            count = cursor.fetchone()[0]
            return count

    def get_query_intent(self, query: str) -> str:
        """
        A more robust router. It checks for keywords in the LLM response
        instead of strictly parsing JSON, making it more reliable.
        """
        prompt = f"""
        You are a high-level query routing system. Your only job is to classify the user's request into one of two categories.

        Categories:
        1. "technical_problem_solving": The user is describing a live, ongoing technical problem, an error, or a system failure and is looking for a solution. Examples: "The database is timing out again", "I'm getting 500 errors on the checkout page", "Our main VM just crashed".
        2. "general_knowledge_query": The user is asking a question *about* the knowledge base (e.g., "how many...", "list...", "tell me about..."), or is having a general conversation.

        User Query: "{query}"

        Analyze the query and respond with just the category name.
        Example response: general_knowledge_query
        """
        try:
            response = self.model.generate_content(prompt)
            # Check for keywords in the response text, which is more robust
            # than parsing JSON from an LLM.
            response_text = response.text.lower().strip()
            if "technical_problem_solving" in response_text:
                return "technical_problem_solving"
            else:
                return "general_knowledge_query"
        except Exception as e:
            print(f"Error determining intent, defaulting to general query: {e}")
            return "general_knowledge_query" # Default on error
        
    def delete_chat_session(self, session_id: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # The 'ON DELETE CASCADE' in the table definition ensures
            # that all messages for this session are also deleted.
            cursor.execute('DELETE FROM chat_sessions WHERE id = ?', (session_id,))
            conn.commit()

    def get_all_rcas(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM rca_documents ORDER BY updated_at DESC')
            rcas = []
            for row in cursor.fetchall():
                rca = dict(row)
                for key in ['problems', 'solutions', 'root_causes', 'lessons_learned']:
                    if rca[key]:
                        rca[key] = json.loads(rca[key])
                rcas.append(rca)
            return rcas