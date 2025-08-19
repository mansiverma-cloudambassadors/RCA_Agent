// src/ChatPage.js

import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Send, User, Bot, Loader, Trash2, Square, Copy, Pencil, Check, X } from 'lucide-react';

const API_URL = 'http://127.0.0.1:8000';

// Use axios for simple, non-streaming requests
const apiClient = axios.create({ baseURL: API_URL });

const fetchSessions = async (setSessions) => {
  try {
    const response = await apiClient.get('/sessions');
    setSessions(response.data);
  } catch (error) {
    console.error("Error fetching sessions:", error);
  }
};

// --- Component for Rendering Code Blocks ---
const CodeBlock = ({ node, inline, className, children, ...props }) => {
  const [isCopied, setIsCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || '');
  const codeText = String(children).replace(/\n$/, '');

  const handleCopy = () => {
    navigator.clipboard.writeText(codeText);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  return !inline && match ? (
    <div style={{ position: 'relative', margin: '1em 0', fontSize: '0.9em' }}>
      <div style={{ background: '#3a404d', color: '#ffffff', padding: '0.5em 1em', borderTopLeftRadius: '8px', borderTopRightRadius: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>{match[1]}</span>
        <button onClick={handleCopy} style={{ background: 'none', border: 'none', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
          {isCopied ? <><Copy size={16} style={{marginRight: '8px'}} /> Copied!</> : <><Copy size={16} style={{marginRight: '8px'}} /> Copy code</>}
        </button>
      </div>
      <SyntaxHighlighter
        style={atomDark}
        language={match[1]}
        PreTag="div"
        {...props}
      >
        {codeText}
      </SyntaxHighlighter>
    </div>
  ) : (
    <code className={className} {...props}>
      {children}
    </code>
  );
};


function ChatPage() {
  const [sessions, setSessions] = useState([]);
  const [messages, setMessages] = useState([]);
  const [currentInput, setCurrentInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [abortController, setAbortController] = useState(null);
  // 💡 NEW: State for handling the rename functionality
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editingTitle, setEditingTitle] = useState('');

  const { sessionId } = useParams();
  const navigate = useNavigate();
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => { fetchSessions(setSessions); }, []);

  useEffect(() => {
    const fetchMessages = async () => {
      if (sessionId && sessionId !== 'new') {
        setIsLoading(true);
        try {
          const response = await apiClient.get(`/sessions/${sessionId}`);
          setMessages(response.data);
        } catch (error) { console.error("Error fetching messages:", error); setMessages([]); }
        finally { setIsLoading(false); }
      } else {
        setMessages([]);
      }
    };
    fetchMessages();
  }, [sessionId]);

  useEffect(() => { scrollToBottom(); }, [messages]);

  // 💡 IMPROVED: New Chat now creates a session immediately
const handleNewChat = async () => {
  // Show a loading state to the user while we talk to the backend
  setIsLoading(true); 
  try {
    // Call the backend to create a new session row with a default title
    const response = await apiClient.post('/sessions', { title: 'New Chat' });
    const newSession = { id: response.data.session_id, title: 'New Chat' };

    // Instantly add the new session to the top of our list in the UI
    setSessions(prev => [newSession, ...prev]);
    // Navigate the user to the new chat page
    navigate(`/chat/${newSession.id}`);
  } catch (error) {
    console.error("Error creating new session:", error);
  } finally {
    // Hide the loading state
    setIsLoading(false); 
  }
};
  
  const handleDeleteSession = async (e, sessionIdToDelete) => {
    e.stopPropagation();
    try {
      await apiClient.delete(`/sessions/${sessionIdToDelete}`);
      setSessions(prevSessions => prevSessions.filter(session => session.id !== sessionIdToDelete));
      if (sessionId === sessionIdToDelete) {
        setMessages([]);
        navigate('/chat/new');
      }
    } catch (error) { console.error("Error deleting session:", error); }
  };

  // 💡 NEW: Handlers for the rename functionality
  const handleRenameInitiate = (e, session) => {
    e.stopPropagation(); // Prevents navigating when clicking the edit icon
    setEditingSessionId(session.id);
    setEditingTitle(session.title);
  };

  const handleRenameConfirm = async (e) => {
    e.stopPropagation();
    if (!editingTitle.trim() || !editingSessionId) return;

    try {
      // Call our new PUT endpoint on the backend
      await apiClient.put(`/sessions/${editingSessionId}`, { title: editingTitle });
      // Update the list in our UI to show the new title
      setSessions(prev => prev.map(s => s.id === editingSessionId ? { ...s, title: editingTitle } : s));
    } catch (error) {
      console.error("Error renaming session:", error);
    } finally {
      // Exit editing mode
      setEditingSessionId(null);
      setEditingTitle('');
    }
  };

const handleRenameCancel = (e) => {
  e.stopPropagation();
  setEditingSessionId(null);
  setEditingTitle('');
};

const handleRenameKeyDown = (e) => {
  if (e.key === 'Enter') {
    handleRenameConfirm(e);
  } else if (e.key === 'Escape') {
    handleRenameCancel(e);
  }
};

  const handleStopGeneration = () => {
    if (abortController) {
      abortController.abort();
      setIsLoading(false);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!currentInput.trim() || isLoading) return;

    setIsLoading(true);
    const textToSend = currentInput;
    const userMessage = { message_type: 'user', content: textToSend };
    
    const newMessages = (sessionId === 'new' || messages.length === 0) ? [userMessage] : [...messages, userMessage];
    setMessages(newMessages);
    setCurrentInput('');
    
    const controller = new AbortController();
    setAbortController(controller);

    try {
      let currentSessionId = sessionId;

      if (sessionId === 'new') {
        const response = await apiClient.post('/sessions', { title: textToSend.substring(0, 50) });
        currentSessionId = response.data.session_id;
        await fetchSessions(setSessions);
        navigate(`/chat/${currentSessionId}`, { replace: true });
      }

      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: currentSessionId,
          problem_description: textToSend
        }),
        signal: controller.signal
      });

      if (!response.body) throw new Error("No response body.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantMessage = { message_type: 'assistant', content: '' };
      setMessages([...newMessages, assistantMessage]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value, { stream: true });
        assistantMessage.content += chunk;
        
        setMessages(prev => [...prev.slice(0, -1), { ...assistantMessage }]);
      }

    } catch (error) {
      if (error.name === 'AbortError') {
        console.log("Stream stopped by user.");
      } else {
        console.error("Error sending message:", error);
        const errorMessage = { message_type: 'assistant', content: 'Sorry, I encountered an error.' };
        setMessages([...newMessages, errorMessage]);
      }
    } finally {
      setIsLoading(false);
      setAbortController(null);
    }
  };

  // --- This is the complete and correct JSX structure for rendering the UI ---
  return (
    <>
      <div className="sidebar">
        <h1>RCA Agent</h1>
        <button className="new-chat-btn" onClick={handleNewChat} disabled={isLoading}>+ New Chat</button>
        <div className="sessions-list">
        {sessions.map(session => (
          <div
            key={session.id}
            className={`session-item ${session.id === sessionId ? 'active' : ''}`}
            // Only allow navigation if we are NOT editing this item
            onClick={() => editingSessionId !== session.id && navigate(`/chat/${session.id}`)}
          >
            {/* 💡 NEW: This is a conditional render. It checks if this session is the one being edited. */}
            {editingSessionId === session.id ? (
              // IF EDITING, show an input box and save/cancel buttons
              <div className="session-edit-container">
                <input
                  type="text"
                  value={editingTitle}
                  onChange={(e) => setEditingTitle(e.target.value)}
                  onKeyDown={handleRenameKeyDown}
                  onBlur={handleRenameCancel} // Cancel if the user clicks away
                  autoFocus
                  className="session-edit-input"
                  onClick={(e) => e.stopPropagation()} // Prevent parent onClick
                />
                <button className="session-edit-btn" onClick={handleRenameConfirm}><Check size={16}/></button>
                <button className="session-edit-btn" onClick={handleRenameCancel}><X size={16}/></button>
              </div>
            ) : (
              // IF NOT EDITING, show the title and action icons
              <>
                <span className="session-title">{session.title || 'New Chat'}</span>
                <div className="session-actions">
                  <button className="session-action-btn" onClick={(e) => handleRenameInitiate(e, session)}><Pencil size={16} /></button>
                  <button className="session-action-btn" onClick={(e) => handleDeleteSession(e, session.id)}><Trash2 size={16} /></button>
                </div>
              </>
            )}
          </div>
        ))}
        </div>
      </div>

      <div className="chat-page">
        <div className="chat-messages">
          {messages.length === 0 && !isLoading && (
            <div className="empty-chat">
              <h2>How can I help you today?</h2>
            </div>
          )}
          {messages.map((msg, index) => (
            <ChatMessage key={index} message={msg} />
          ))}
          <div ref={messagesEndRef} />
        </div>
        
        <div className="chat-input-area">
          {isLoading && (
            <div style={{maxWidth: '800px', margin: '0 auto 16px auto', textAlign: 'center'}}>
                <button onClick={handleStopGeneration} style={{padding: '8px 16px', border: '1px solid var(--border-color)', borderRadius: '8px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center'}}>
                    <Square size={16} style={{marginRight: '8px'}} /> Stop generating
                </button>
            </div>
          )}
          <form className="chat-input-form" onSubmit={handleSendMessage}>
            <input
              type="text"
              className="chat-input"
              value={currentInput}
              onChange={(e) => setCurrentInput(e.target.value)}
              placeholder="Describe your problem..."
              disabled={isLoading}
            />
            <button type="submit" className="send-btn" disabled={isLoading}>
              <Send size={20} />
            </button>
          </form>
        </div>
      </div>
    </>
  );
}


function ChatMessage({ message }) {
  const isUser = message.message_type === 'user';
  return (
    <div className={`message ${isUser ? 'user-message' : 'assistant-message'}`}>
      <div className={`message-header ${isUser ? 'user-header' : 'assistant-header'}`}>
        <span>{isUser ? <User size={20}/> : <Bot size={20}/>}</span>
        {isUser ? 'You' : 'RCA Assistant'}
      </div>
      <div className="message-content">
        <ReactMarkdown 
          remarkPlugins={[remarkGfm]}
          components={{ code: CodeBlock }}
        >
          {message.content}
        </ReactMarkdown>
      </div>
    </div>
  );
}

export default ChatPage;