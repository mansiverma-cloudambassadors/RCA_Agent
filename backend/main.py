import os
from fastapi import FastAPI, HTTPException, Body, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware # Add this import
from fastapi.responses import StreamingResponse # 💡 Add this import at the top
import asyncio # 💡 Add this import at the top

from rca_agent import AdvancedRCAKnowledgeBase

# Load environment variables from .env file
load_dotenv()

# --- Initialize the RCA System ---
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables.")
rca_system = AdvancedRCAKnowledgeBase(api_key=api_key)

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Advanced RCA Agent API",
    description="An API for intelligent Root Cause Analysis using Gemini and Vector Search.",
    version="1.0.0",
)

origins = [
    "http://localhost:3000", # The address of your React frontend
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allow all methods (GET, POST, etc.)
    allow_headers=["*"], # Allow all headers
)

# --- Pydantic Models for API Data Validation ---
class ChatRequest(BaseModel):
    session_id: str = Field(..., description="The unique ID for the chat session.")
    problem_description: str = Field(..., description="The user's description of the current problem.")

class SessionCreateRequest(BaseModel):
    title: Optional[str] = Field(None, description="An optional title for the new chat session.")

class SyncResponse(BaseModel):
    status: str
    stats: Dict[str, int]

class SessionUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, description="The new title for the chat session.")


# --- API Endpoints ---
@app.post("/sync-gcs", response_model=SyncResponse, status_code=status.HTTP_200_OK, tags=["Knowledge Base"])
async def sync_gcs_files():
    """
    Triggers a synchronization process to ingest and index all RCA documents from the GCS bucket.
    """
    try:
        stats = rca_system.sync_gcs_files()
        return {"status": "Sync completed successfully", "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Sync failed: {e}")

@app.get("/rcas", response_model=List[Dict[str, Any]], tags=["Knowledge Base"])
async def get_all_rca_documents():
    """
    Retrieves a list of all RCA documents currently in the knowledge base.
    """
    return rca_system.get_all_rcas()

@app.get("/sessions", response_model=List[Dict[str, Any]], tags=["Chat"])
async def get_sessions():
    """
    Retrieves all existing chat sessions, ordered by most recently updated.
    """
    return rca_system.get_chat_sessions()

@app.get("/sessions/{session_id}", response_model=List[Dict[str, Any]], tags=["Chat Session"])
async def get_messages_for_session(session_id: str):
    """Gets all messages for a specific chat session."""
    return rca_system.get_chat_messages(session_id)

@app.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Chat"])
async def delete_session(session_id: str):
    """
    Deletes a chat session and all its associated messages.
    """
    rca_system.delete_chat_session(session_id)
    return None

@app.post("/sessions", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED, tags=["Chat"])
async def create_session(request: SessionCreateRequest = Body(None)):
    """
    Creates a new chat session.
    """
    title = request.title if request else None
    session_id = rca_system.create_chat_session(title=title)
    return {"session_id": session_id}

# 💡 NEW: This is the new endpoint for renaming a session.
@app.put("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Chat Session"])
async def update_session(session_id: str, request: SessionUpdateRequest):
    """Updates the title of a specific chat session."""
    rca_system.update_session_title(session_id, request.title)
    return None

@app.post("/chat-simple", tags=["Chat"])
async def handle_chat_simple(request: ChatRequest):
    """
    The main chat interaction endpoint.
    Uses a hybrid approach: a specialist for technical problems and a generalist for all other questions.
    """
    try:
        # 1. Add user message to history
        rca_system.add_chat_message(request.session_id, 'user', request.problem_description)

        # 2. Determine the user's high-level intent
        intent = rca_system.get_query_intent(request.problem_description)

        response_text = ""
        similar_rcas = None

        # 3. Route to the correct "agent" based on intent
        if intent == "technical_problem_solving":
            # Path A: Use the Specialist Engineer for technical issues
            print("INFO: Routing to specialist problem-solver.")
            similar_rcas = rca_system.search_similar_problems(request.problem_description)
            response_text = rca_system.generate_solution_recommendation(request.problem_description, similar_rcas)
        else: # This handles "general_knowledge_query"
            # Path B: Use the Knowledgeable Assistant for everything else
            print("INFO: Routing to general knowledge assistant.")
            response_text = rca_system.generate_general_response(request.problem_description)

        # 4. Add the final response to the chat history
        rca_system.add_chat_message(request.session_id, 'assistant', response_text, similar_rcas)
        
        return {"response": response_text, "similar_rcas": similar_rcas}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 💡 NEW: This is the new streaming endpoint for our advanced UI.
@app.post("/chat", tags=["Chat"])
async def handle_chat_stream(request: ChatRequest):
    """
    The main chat interaction endpoint, now with streaming.
    Accepts conversation history for better contextual responses.
    """
    try:
        # The frontend will now send the whole conversation history
        # We can adapt the problem_description to be the last user message
        # and the history to be the full context.
        # For this implementation, we'll keep the hybrid router logic.

        # 1. Add user message to history
        rca_system.add_chat_message(request.session_id, 'user', request.problem_description)

        # 2. Determine intent
        intent = rca_system.get_query_intent(request.problem_description)

        # This async generator function will yield chunks of text
        async def stream_generator():
            full_response_text = ""
            if intent == "technical_problem_solving":
                print("INFO: Routing to specialist problem-solver.")
                similar_rcas = rca_system.search_similar_problems(request.problem_description)
                # We can't stream the recommendation easily with the current setup,
                # so we'll stream it as a single chunk. For true token-by-token of the
                # full RAG, the recommendation function itself would need to be a generator.
                # This is a good starting point.
                response_text = rca_system.generate_solution_recommendation(request.problem_description, similar_rcas)
                full_response_text = response_text
                yield response_text

            else: # general_knowledge_query
                print("INFO: Routing to general knowledge assistant.")
                # We CAN stream this response directly from the model
                response_stream = rca_system.generate_general_response(request.problem_description, stream=True)
                
                try:
                    for chunk in response_stream:
                        full_response_text += chunk.text
                        yield chunk.text
                        await asyncio.sleep(0.01) # Small delay to allow chunks to send
                except Exception as e:
                    print(f"Error during streaming: {e}")
                    yield "Sorry, an error occurred while generating the response."


            # 4. After streaming is complete, save the full response to the database
            # We pass similar_rcas=None for general queries.
            rca_system.add_chat_message(request.session_id, 'assistant', full_response_text, similar_rcas if intent == 'technical_problem_solving' else None)

        return StreamingResponse(stream_generator(), media_type="text/plain")

    except Exception as e:
        print(f"Error in chat stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))
