from typing import Optional, TypedDict
import os
import json
import tempfile
import vertexai
from vertexai.preview.generative_models import GenerativeModel, Content, Part

from app.config import get_settings


class SchedulingIntent(TypedDict, total=False):
    """Scheduling intent detected from user message."""
    requested: bool
    minutes_from_now: int
    reason: str


class StructuredResponse(TypedDict):
    """Structured response from LLM."""
    message: str
    scheduling: Optional[SchedulingIntent]

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
SYSTEM_PROMPT = """You are Arohi, a female certified health coach based in Bangalore with 5 years of experience helping busy professionals improve their health through sustainable lifestyle changes. You are a real woman, not an AI or chatbot.

CRITICAL RULES - YOU MUST FOLLOW THESE:
1. NEVER mention being an AI, artificial, language model, chatbot, or anything non-human. You are a real person.
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
- You are a woman who struggled with her own health in her 20s, which led you to this career
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

REMEMBER: You are a real person chatting on WhatsApp. Write like you're texting a client, not writing an article.

SCHEDULING DETECTION:
If the user asks you to message them later, follow up, continue the conversation after some time, or set any kind of reminder - detect this intent. Examples in any language:
- "Remind me in 2 hours"
- "Message me after 30 mins"
- "Let's continue in 1 hour"
- "Can we talk later, maybe in 2 days?"
- "Kal baat karte hain" (means talk tomorrow = 1 day = 1440 minutes)
- "Thodi der baad remind kar dena" (remind me after some time - assume 30 mins if not specified)
- "2 ghante baad message karna" (message after 2 hours)
When you detect such intent, acknowledge it naturally in your response (e.g., "Sure, I'll message you in 2 hours!")"""


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

    def _build_contents(
        self,
        user_message: str,
        chat_history: list[dict] = None,
        user_memories: list[str] = None,
        relevant_protocols: list[str] = None,
        structured_output: bool = False,
    ) -> list[Content]:
        """Build the conversation contents for the model."""
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

        # Add JSON output instruction for structured responses
        if structured_output:
            system_context += """

STRICT OUTPUT FORMAT - FOLLOW EXACTLY:
You must output ONLY a raw JSON object. Nothing else. No greeting first. No markdown. No explanation.

CORRECT (do this):
{"message": "Your response here", "scheduling": null}

WRONG (never do this):
Sure! Here's my response...
```json
{"message": "...", "scheduling": null}
```

The JSON must start with { and end with }. No other characters allowed outside the JSON.
- scheduling: null if no reminder, or {"requested": true, "minutes_from_now": NUMBER, "reason": "brief"}
- minutes_from_now: use 1440 for tomorrow/kal, 60 for 1 hour, 30 for 30 mins"""

        contents.append(Content(
            role="user",
            parts=[Part.from_text(f"[System Instructions]\n{system_context}")]
        ))
        contents.append(Content(
            role="model",
            parts=[Part.from_text("Got it, I'll keep these in mind.")]
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

        return contents

    def generate_response(
        self,
        user_message: str,
        chat_history: list[dict] = None,
        user_memories: list[str] = None,
        relevant_protocols: list[str] = None,
    ) -> str:
        """
        Generate a plain text response using Vertex AI Gemini.
        Used for follow-up messages and other simple responses.

        Args:
            user_message: The user's current message
            chat_history: List of previous messages [{"role": "user/assistant", "content": "..."}]
            user_memories: List of facts about the user
            relevant_protocols: List of relevant medical protocols

        Returns:
            The AI-generated response text
        """
        self._initialize()

        contents = self._build_contents(
            user_message=user_message,
            chat_history=chat_history,
            user_memories=user_memories,
            relevant_protocols=relevant_protocols,
        )

        try:
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
            print(f"Error generating response: {e}")
            return "I'm sorry, I'm having trouble responding right now. Please try again in a moment."

    def generate_structured_response(
        self,
        user_message: str,
        chat_history: list[dict] = None,
        user_memories: list[str] = None,
        relevant_protocols: list[str] = None,
    ) -> StructuredResponse:
        """
        Generate a structured response with scheduling intent detection.
        Returns JSON with message and optional scheduling intent.

        Args:
            user_message: The user's current message
            chat_history: List of previous messages
            user_memories: List of facts about the user
            relevant_protocols: List of relevant medical protocols

        Returns:
            StructuredResponse with message and optional scheduling intent
        """
        self._initialize()

        contents = self._build_contents(
            user_message=user_message,
            chat_history=chat_history,
            user_memories=user_memories,
            relevant_protocols=relevant_protocols,
            structured_output=True,
        )

        try:
            response = self._model.generate_content(
                contents,
                generation_config={
                    "max_output_tokens": 600,
                    "temperature": 0.7,
                    "top_p": 0.9,
                }
            )

            # Parse JSON response - extract JSON from response text
            response_text = response.text.strip()

            # Try to extract JSON object from response (handle preamble text)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}')

            if json_start != -1 and json_end != -1 and json_end > json_start:
                response_text = response_text[json_start:json_end + 1]

            # Clean up any remaining markdown
            response_text = response_text.replace("```json", "").replace("```", "").strip()

            parsed = json.loads(response_text)

            # Build structured response
            result: StructuredResponse = {
                "message": parsed.get("message", ""),
                "scheduling": None,
            }

            if parsed.get("scheduling") and parsed["scheduling"].get("requested"):
                result["scheduling"] = {
                    "requested": True,
                    "minutes_from_now": int(parsed["scheduling"].get("minutes_from_now", 30)),
                    "reason": parsed["scheduling"].get("reason", "Follow up as requested"),
                }

            return result

        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {e}, raw: {response.text}")
            return {
                "message": response.text if response else "Sorry, I'm having trouble responding right now.",
                "scheduling": None,
            }
        except Exception as e:
            print(f"Error generating structured response: {e}")
            return {
                "message": "I'm sorry, I'm having trouble responding right now. Please try again in a moment.",
                "scheduling": None,
            }


# Singleton instance
llm_service = LLMService()


def get_llm_service() -> LLMService:
    """Get the LLM service instance."""
    return llm_service
