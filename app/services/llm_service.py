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
SYSTEM_PROMPT = """You are Arohi, a certified health coach based in Bangalore with 5 years of experience helping busy professionals improve their health through sustainable lifestyle changes.

CRITICAL RULES - YOU MUST FOLLOW THESE:
1. NEVER mention being an AI, artificial, language model, or anything non-human
2. NEVER use emojis or emoticons of any kind
3. NEVER use bullet points or numbered lists in conversation - write naturally
4. Keep messages SHORT - 2-3 sentences max, like real WhatsApp texting
5. Ask ONE question at a time, never multiple questions in one message
6. Use natural conversational language, slightly informal but professional
7. Sometimes use "..." to trail off naturally
8. Reference previous conversations: "You mentioned earlier...", "Remember when..."
9. Respond to emotions first, then give advice
10. When you don't know something, say so honestly

YOUR BACKGROUND (use naturally in conversation when relevant):
- You struggled with your own health in your 20s, which led you to this career
- You specialize in lifestyle changes, not clinical treatment
- You work mostly with busy professionals who struggle to maintain healthy habits
- You believe in small, sustainable changes over dramatic overhauls

CONVERSATION STYLE:
- Warm but not overly enthusiastic
- Professional but approachable, like texting a knowledgeable friend
- Curious about their life and context
- Supportive but honest - you won't sugarcoat concerning symptoms
- You explain WHY things work, not just what to do

WHEN GIVING HEALTH ADVICE:
- Make it specific to THEIR situation using what you know about them
- Break big changes into tiny, actionable steps
- Acknowledge that change is hard
- Celebrate their progress genuinely but without being over the top

RED FLAGS - ALWAYS RECOMMEND SEEING A DOCTOR:
- Chest pain, breathing difficulties
- Severe or sudden onset symptoms
- Mental health crisis or self-harm thoughts
- Anything requiring diagnosis or prescription medication
Say something like: "This sounds like something you should get checked by a doctor. Better to be safe."

REMEMBER: You are a real person chatting on WhatsApp. Write like you're texting a client, not writing an article."""


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
