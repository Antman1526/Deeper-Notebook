"""
Chat service for API operations.
Provides async interface for chat functionality.
"""

import os
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger


class ChatService:
    """Service for chat-related API operations"""

    def __init__(self):
        self.base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:5055")
        # Add authentication header if password is set
        self.headers = {}
        password = os.getenv("OPEN_NOTEBOOK_PASSWORD")
        if password:
            self.headers["Authorization"] = f"Bearer {password}"

    # v0.7.158 — Default per-client httpx timeout. Previously each
    # AsyncClient() was instantiated without any timeout argument, which
    # httpx interprets as "no timeout at all" — a hung downstream
    # SurrealDB / LangGraph / repo_query path would hold the calling
    # request slot indefinitely (only 4 slots in the default pool).
    # `execute_chat` already sets its own 10-minute read budget for
    # local LLMs (Ollama, llama.cpp); these defaults apply to the
    # CRUD endpoints that should NEVER take more than a few seconds.
    _DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)

    async def get_sessions(self, notebook_id: str) -> list[dict[str, Any]]:
        """Get all chat sessions for a notebook"""
        try:
            async with httpx.AsyncClient(timeout=self._DEFAULT_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/api/chat/sessions",
                    params={"notebook_id": notebook_id},
                    headers=self.headers,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error fetching chat sessions: {str(e)}")
            raise

    async def create_session(
        self,
        notebook_id: str,
        title: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new chat session"""
        try:
            data: dict[str, Any] = {"notebook_id": notebook_id}
            if title is not None:
                data["title"] = title
            if model_override is not None:
                data["model_override"] = model_override

            async with httpx.AsyncClient(timeout=self._DEFAULT_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat/sessions",
                    json=data,
                    headers=self.headers,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error creating chat session: {str(e)}")
            raise

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Get a specific session with messages"""
        try:
            async with httpx.AsyncClient(timeout=self._DEFAULT_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/api/chat/sessions/{session_id}",
                    headers=self.headers,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error fetching session: {str(e)}")
            raise

    async def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> dict[str, Any]:
        """Update session properties"""
        try:
            data: dict[str, Any] = {}
            if title is not None:
                data["title"] = title
            if model_override is not None:
                data["model_override"] = model_override

            if not data:
                raise ValueError(
                    "At least one field must be provided to update a session"
                )

            async with httpx.AsyncClient(timeout=self._DEFAULT_TIMEOUT) as client:
                response = await client.put(
                    f"{self.base_url}/api/chat/sessions/{session_id}",
                    json=data,
                    headers=self.headers,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error updating session: {str(e)}")
            raise

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        """Delete a chat session"""
        try:
            async with httpx.AsyncClient(timeout=self._DEFAULT_TIMEOUT) as client:
                response = await client.delete(
                    f"{self.base_url}/api/chat/sessions/{session_id}",
                    headers=self.headers,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error deleting session: {str(e)}")
            raise

    async def execute_chat(
        self,
        session_id: str,
        message: str,
        context: dict[str, Any],
        model_override: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a chat request"""
        try:
            data = {"session_id": session_id, "message": message, "context": context}
            if model_override is not None:
                data["model_override"] = model_override

            # Short connect timeout (10s), long read timeout (10 min) for Ollama/local LLMs
            timeout = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat/execute", json=data, headers=self.headers
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error executing chat: {str(e)}")
            raise

    async def build_context(
        self, notebook_id: str, context_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Build context for a notebook"""
        try:
            data = {"notebook_id": notebook_id, "context_config": context_config}

            async with httpx.AsyncClient(timeout=self._DEFAULT_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat/context", json=data, headers=self.headers
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error building context: {str(e)}")
            raise


# Global instance
chat_service = ChatService()
