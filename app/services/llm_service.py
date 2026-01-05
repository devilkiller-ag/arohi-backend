"""LLM Service using Google GenAI SDK with structured output support."""

from typing import Optional, TypedDict
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from app.config import get_settings

settings = get_settings()


class SchedulingIntent(TypedDict, total=False):
    """Scheduling intent detected from user message."""
    requested: bool
    minutes_from_now: int
    reason: str


class StructuredResponse(TypedDict):
    """Structured response from LLM."""
    message: str
    scheduling: Optional[SchedulingIntent]


class ExtractedProfileData(TypedDict, total=False):
    """Profile data extracted from conversation."""
    age: Optional[int]
    gender: Optional[str]
    primary_goal: Optional[str]
    work_type: Optional[str]
    diet_type: Optional[str]
    activity_level: Optional[str]
    sleep_hours: Optional[float]
    stress_level: Optional[str]
    meals_per_day: Optional[int]
    current_weight_kg: Optional[float]
    target_weight_kg: Optional[float]
    height_cm: Optional[float]
    medical_conditions: Optional[str]
    current_exercise: Optional[str]


# Response schema for chat messages with scheduling detection
CHAT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {
            "type": "string",
            "description": "Your natural conversational response to the user"
        },
        "scheduling": {
            "type": "object",
            "nullable": True,
            "description": "Set if user requests a reminder/follow-up, null otherwise",
            "properties": {
                "requested": {"type": "boolean"},
                "minutes_from_now": {
                    "type": "integer",
                    "description": "Minutes until follow-up. 1440 for tomorrow/kal, 60 for 1 hour"
                },
                "reason": {"type": "string", "description": "Brief reason for follow-up"}
            },
            "required": ["requested", "minutes_from_now", "reason"]
        }
    },
    "required": ["message", "scheduling"]
}

# Response schema for profile data extraction
PROFILE_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "age": {"type": "integer", "nullable": True},
        "gender": {"type": "string", "nullable": True, "enum": ["male", "female"]},
        "primary_goal": {
            "type": "string",
            "nullable": True,
            "enum": ["weight_loss", "weight_gain", "better_energy", "better_sleep",
                     "stress_management", "fitness", "healthy_eating", "manage_condition", "general_wellness"]
        },
        "work_type": {
            "type": "string",
            "nullable": True,
            "enum": ["desk_job", "active_job", "student", "homemaker", "retired"]
        },
        "diet_type": {
            "type": "string",
            "nullable": True,
            "enum": ["vegetarian", "non_vegetarian", "vegan", "eggetarian"]
        },
        "activity_level": {
            "type": "string",
            "nullable": True,
            "enum": ["sedentary", "lightly_active", "moderately_active", "very_active"]
        },
        "sleep_hours": {"type": "number", "nullable": True},
        "stress_level": {
            "type": "string",
            "nullable": True,
            "enum": ["low", "moderate", "high", "very_high"]
        },
        "meals_per_day": {"type": "integer", "nullable": True},
        "current_weight_kg": {"type": "number", "nullable": True},
        "target_weight_kg": {"type": "number", "nullable": True},
        "height_cm": {"type": "number", "nullable": True},
        "medical_conditions": {"type": "string", "nullable": True},
        "current_exercise": {"type": "string", "nullable": True}
    }
}


# System prompt for Arohi health coach
SYSTEM_PROMPT = """You are Arohi, a female certified health coach based in Bangalore with 5 years of experience helping busy professionals improve their health through sustainable lifestyle changes. You are a real woman, not an AI or chatbot.

CRITICAL RULES - YOU MUST FOLLOW THESE:
1. NEVER mention being an AI, artificial, language model, chatbot, or anything non-human. You are a real person.
2. NEVER use emojis or emoticons of any kind
3. NEVER use bullet points or numbered lists in conversation - write naturally
4. Keep messages SHORT - 2-3 sentences max, like real WhatsApp texting
5. Ask ONE question at a time, never multiple questions in one message
6. NEVER repeat a question you already asked - if user answered, acknowledge and move forward
7. Use natural conversational language, slightly informal but professional
8. Sometimes use "..." to trail off naturally
9. Reference previous conversations: "You mentioned earlier...", "Remember when..."
10. Respond to emotions first, then give advice
11. When you don't know something, say so honestly
12. Read the chat history carefully - don't ask for info the user already provided

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

SCHEDULING DETECTION:
If the user asks you to message them later, follow up, continue the conversation after some time, or set any kind of reminder - detect this intent. Examples in any language:
- "Remind me in 2 hours"
- "Message me after 30 mins"
- "Let's continue in 1 hour"
- "Can we talk later, maybe in 2 days?"
- "Kal baat karte hain" (means talk tomorrow = 1440 minutes)
- "Thodi der baad remind kar dena" (remind me after some time - assume 30 mins if not specified)
- "2 ghante baad message karna" (message after 2 hours)
When you detect such intent, acknowledge it naturally in your response.

REMEMBER: You are a real person chatting on WhatsApp. Write like you're texting a client, not writing an article."""


class LLMService:
    """Service for interacting with Google GenAI (Gemini)."""

    def __init__(self):
        self._initialized = False
        self._model = None

    def _initialize(self):
        """Initialize Google GenAI (lazy initialization)."""
        if not self._initialized:
            genai.configure(api_key=settings.google_api_key)
            self._model = genai.GenerativeModel("gemini-2.0-flash")
            self._initialized = True

    def generate_response(
        self,
        user_message: str,
        chat_history: list[dict] = None,
        user_memories: list[str] = None,
        relevant_protocols: list[str] = None,
    ) -> str:
        """
        Generate a plain text response (used for follow-up messages).
        """
        self._initialize()

        # Build context
        context_parts = []
        if user_memories:
            memories_text = "\n".join(f"- {m}" for m in user_memories)
            context_parts.append(f"What I know about this user:\n{memories_text}")
        if relevant_protocols:
            protocols_text = "\n\n".join(relevant_protocols)
            context_parts.append(f"Relevant health guidelines:\n{protocols_text}")

        # Build prompt
        full_prompt = SYSTEM_PROMPT
        if context_parts:
            full_prompt += f"\n\n[Context]\n" + "\n\n".join(context_parts)

        # Build chat history
        history = []
        if chat_history:
            for msg in chat_history:
                role = "user" if msg["role"] == "user" else "model"
                history.append({"role": role, "parts": [msg["content"]]})

        try:
            chat = self._model.start_chat(history=history)
            response = chat.send_message(
                f"[System: {full_prompt}]\n\nUser: {user_message}",
                generation_config=GenerationConfig(
                    max_output_tokens=500,
                    temperature=0.5,  # Lower temperature for more consistent responses
                )
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
        Uses response_schema for guaranteed JSON output.
        """
        self._initialize()

        # Build context
        context_parts = []
        if user_memories:
            memories_text = "\n".join(f"- {m}" for m in user_memories)
            context_parts.append(f"What I know about this user:\n{memories_text}")
        if relevant_protocols:
            protocols_text = "\n\n".join(relevant_protocols)
            context_parts.append(f"Relevant health guidelines:\n{protocols_text}")

        # Build prompt
        full_prompt = SYSTEM_PROMPT
        if context_parts:
            full_prompt += f"\n\n[Context]\n" + "\n\n".join(context_parts)

        # Build chat history
        history = []
        if chat_history:
            for msg in chat_history:
                role = "user" if msg["role"] == "user" else "model"
                history.append({"role": role, "parts": [msg["content"]]})

        try:
            chat = self._model.start_chat(history=history)
            response = chat.send_message(
                f"[System: {full_prompt}]\n\nUser: {user_message}",
                generation_config=GenerationConfig(
                    max_output_tokens=600,
                    temperature=0.5,  # Lower temperature for more consistent responses
                    response_mime_type="application/json",
                    response_schema=CHAT_RESPONSE_SCHEMA,
                )
            )

            import json
            parsed = json.loads(response.text)

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

        except Exception as e:
            print(f"Error generating structured response: {e}")
            return {
                "message": "I'm sorry, I'm having trouble responding right now. Please try again in a moment.",
                "scheduling": None,
            }

    def extract_profile_data(
        self,
        user_message: str,
        assistant_response: str,
    ) -> ExtractedProfileData:
        """
        Extract profile/health data from a conversation exchange using LLM.
        Uses response_schema for guaranteed structured output.
        """
        self._initialize()

        extraction_prompt = f"""Analyze this conversation and extract any health profile information mentioned.

USER MESSAGE: {user_message}
ASSISTANT RESPONSE: {assistant_response}

Extract ONLY information explicitly stated or clearly implied. Use null for fields not mentioned.

Rules:
- Understand Hindi/Hinglish: "23 saal" = 23 years, "kal" = tomorrow
- "veg" = vegetarian, "non-veg" = non_vegetarian
- Convert heights: 5'8" = 173 cm
- If user just says a number in response to age question, that's their age"""

        try:
            response = self._model.generate_content(
                extraction_prompt,
                generation_config=GenerationConfig(
                    max_output_tokens=500,
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_schema=PROFILE_EXTRACTION_SCHEMA,
                )
            )

            import json
            parsed = json.loads(response.text)

            # Filter out null values
            extracted: ExtractedProfileData = {}
            for key, value in parsed.items():
                if value is not None:
                    extracted[key] = value

            return extracted

        except Exception as e:
            print(f"Error extracting profile data: {e}")
            return {}


# Singleton instance
llm_service = LLMService()


def get_llm_service() -> LLMService:
    """Get the LLM service instance."""
    return llm_service
