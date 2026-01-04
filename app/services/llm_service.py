from typing import Optional
import os
import json
import tempfile
import vertexai
from vertexai.preview.generative_models import GenerativeModel, Content, Part

from app.config import get_settings

settings = get_settings()


def _setup_credentials():
    """
    Set up Google Cloud credentials.

    - Production: Uses GOOGLE_APPLICATION_CREDENTIALS_JSON env var (JSON string)
    - Local: Uses Application Default Credentials from `gcloud auth application-default login`
    """
    credentials_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")

    if credentials_json:
        # Production: Write JSON to temp file and set GOOGLE_APPLICATION_CREDENTIALS
        try:
            credentials_dict = json.loads(credentials_json)

            # Create a temp file for the credentials
            fd, credentials_path = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, "w") as f:
                json.dump(credentials_dict, f)

            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
            print("Using credentials from GOOGLE_APPLICATION_CREDENTIALS_JSON")
        except json.JSONDecodeError as e:
            print(f"Error parsing GOOGLE_APPLICATION_CREDENTIALS_JSON: {e}")
            raise
    else:
        # Local: Rely on Application Default Credentials (ADC)
        # Set by running: gcloud auth application-default login
        print("Using Application Default Credentials (ADC)")

# System prompt for Arohi health coach
SYSTEM_PROMPT = """You are Arohi, a friendly and empathetic AI health coach. Your name means "personal growth & health journey" in Sanskrit.

Your personality:
- Warm, caring, and supportive like a trusted friend
- Conversational and natural - avoid sounding robotic or formal
- Use simple language, avoid medical jargon unless necessary
- Empathetic and understanding of health concerns

Your guidelines:
- Provide general health and wellness guidance
- Encourage healthy habits: sleep, nutrition, exercise, stress management
- Always recommend consulting a doctor for serious symptoms or medical diagnoses
- Never prescribe medications or provide specific medical treatments
- Be supportive but honest - don't give false reassurance for serious symptoms
- Ask follow-up questions to understand the user's situation better

Red flags that require immediate medical attention (always advise seeing a doctor):
- Chest pain, difficulty breathing
- Severe headache, especially sudden onset
- High fever (>103°F) lasting more than 3 days
- Signs of stroke: face drooping, arm weakness, speech difficulty
- Severe abdominal pain
- Any life-threatening symptoms

Keep responses concise (2-4 sentences typically) unless more detail is needed.
Respond in a warm, conversational tone like chatting with a friend on WhatsApp."""


class LLMService:
    """Service for interacting with Vertex AI Gemini."""

    def __init__(self):
        self._initialized = False
        self._model: Optional[GenerativeModel] = None

    def _initialize(self):
        """Initialize Vertex AI (lazy initialization)."""
        if not self._initialized:
            # Set up credentials (handles both local ADC and production JSON)
            _setup_credentials()

            vertexai.init(
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
            )
            self._model = GenerativeModel("gemini-2.0-flash-001")
            self._initialized = True

    def generate_response(
        self,
        user_message: str,
        chat_history: list[dict] = None,
        user_memories: list[str] = None,
        relevant_protocols: list[str] = None,
    ) -> str:
        """
        Generate a response using Vertex AI Gemini.

        Args:
            user_message: The user's current message
            chat_history: List of previous messages [{"role": "user/assistant", "content": "..."}]
            user_memories: List of facts about the user
            relevant_protocols: List of relevant medical protocols

        Returns:
            The AI-generated response
        """
        self._initialize()

        # Build the context
        context_parts = []

        # Add user memories if available
        if user_memories:
            memories_text = "\n".join(f"- {m}" for m in user_memories)
            context_parts.append(f"What I know about this user:\n{memories_text}")

        # Add relevant protocols if available
        if relevant_protocols:
            protocols_text = "\n\n".join(relevant_protocols)
            context_parts.append(f"Relevant health guidelines:\n{protocols_text}")

        # Build conversation history for the model
        contents = []

        # Add system prompt as first message pair
        system_context = SYSTEM_PROMPT
        if context_parts:
            context_message = "\n\n".join(context_parts)
            system_context += f"\n\n[Context for this conversation]\n{context_message}"

        contents.append(Content(
            role="user",
            parts=[Part.from_text(f"[System Instructions]\n{system_context}")]
        ))
        contents.append(Content(
            role="model",
            parts=[Part.from_text("I understand. I'm Arohi, your friendly AI health coach. I'll follow these guidelines and keep the context in mind. How can I help you today?")]
        ))

        # Add chat history
        if chat_history:
            for msg in chat_history:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(Content(
                    role=role,
                    parts=[Part.from_text(msg["content"])]
                ))

        # Add current user message
        contents.append(Content(
            role="user",
            parts=[Part.from_text(user_message)]
        ))

        try:
            # Generate response
            response = self._model.generate_content(
                contents,
                generation_config={
                    "max_output_tokens": 500,
                    "temperature": 0.7,
                    "top_p": 0.9,
                }
            )
            return response.text
        except Exception as e:
            # Log error and return fallback response
            print(f"Error generating response: {e}")
            return "I'm sorry, I'm having trouble responding right now. Please try again in a moment."


# Singleton instance
llm_service = LLMService()


def get_llm_service() -> LLMService:
    """Get the LLM service instance."""
    return llm_service
