"""Service for managing user profiles and onboarding data extraction."""

import re
from datetime import datetime
from typing import Optional, Dict, List, Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_profile import (
    UserProfile,
    OnboardingStage,
    HealthGoal,
    WorkType,
    ActivityLevel,
    DietType,
)


class ProfileService:
    """Service for managing user health profiles and tracking onboarding progress."""

    # Keywords for extracting data from conversations
    GOAL_KEYWORDS = {
        HealthGoal.WEIGHT_LOSS: ["lose weight", "weight loss", "slim down", "fat loss", "reduce weight", "shed", "kilo", "kg loss"],
        HealthGoal.WEIGHT_GAIN: ["gain weight", "bulk up", "put on weight", "increase weight", "mass gain"],
        HealthGoal.BETTER_ENERGY: ["more energy", "tired", "fatigue", "exhausted", "low energy", "always tired", "energetic"],
        HealthGoal.BETTER_SLEEP: ["sleep better", "insomnia", "can't sleep", "sleep problem", "sleeping", "rest better"],
        HealthGoal.STRESS_MANAGEMENT: ["stress", "anxiety", "anxious", "overwhelmed", "burnout", "mental health", "relax"],
        HealthGoal.FITNESS: ["fit", "fitness", "stronger", "stamina", "endurance", "gym", "workout", "exercise more"],
        HealthGoal.HEALTHY_EATING: ["eat healthy", "better diet", "nutrition", "eating habits", "junk food", "clean eating"],
        HealthGoal.MANAGE_CONDITION: ["diabetes", "bp", "blood pressure", "thyroid", "pcos", "cholesterol", "sugar"],
        HealthGoal.GENERAL_WELLNESS: ["healthy", "wellness", "overall health", "lifestyle", "better life"],
    }

    WORK_TYPE_KEYWORDS = {
        WorkType.DESK_JOB: ["desk job", "office", "wfh", "work from home", "computer", "sitting all day", "it job", "software"],
        WorkType.ACTIVE_JOB: ["field", "standing", "physical work", "labour", "delivery", "sales field", "walking"],
        WorkType.STUDENT: ["student", "studying", "college", "school", "university", "preparing for exam"],
        WorkType.HOMEMAKER: ["homemaker", "housewife", "home maker", "stay at home"],
        WorkType.RETIRED: ["retired", "retirement", "not working anymore"],
    }

    DIET_KEYWORDS = {
        DietType.VEGETARIAN: ["vegetarian", "veg only", "no meat", "pure veg"],
        DietType.NON_VEGETARIAN: ["non-veg", "non veg", "meat", "chicken", "mutton", "fish"],
        DietType.VEGAN: ["vegan", "no dairy", "plant based", "plant-based"],
        DietType.EGGETARIAN: ["egg", "eggetarian", "ovo vegetarian"],
    }

    # Questions to ask for each onboarding stage
    STAGE_QUESTIONS = {
        OnboardingStage.BASIC_INFO: [
            ("age", "Could you tell me your age? It helps me understand your health context better."),
            ("occupation", "What do you do for work? Are you in an office job, or something more active?"),
        ],
        OnboardingStage.HEALTH_GOALS: [
            ("primary_goal", "What's the main health goal you want to work on? Weight management, more energy, better sleep, stress...?"),
            ("goal_motivation", "What's driving you to make this change now?"),
            ("previous_attempts", "Have you tried working on this before? What happened?"),
        ],
        OnboardingStage.LIFESTYLE: [
            ("work_hours", "How many hours do you typically work in a day?"),
            ("sleep_hours", "How's your sleep? How many hours do you usually get?"),
            ("stress_level", "On a scale of low to very high, how would you rate your stress levels these days?"),
        ],
        OnboardingStage.DIET_HABITS: [
            ("diet_type", "Are you vegetarian, non-vegetarian, or do you follow any specific diet?"),
            ("meals_per_day", "How many meals do you typically have in a day?"),
            ("cooking_frequency", "Do you cook at home, or do you eat out more often?"),
            ("water_intake", "How much water do you think you drink in a day?"),
        ],
        OnboardingStage.PHYSICAL_ACTIVITY: [
            ("current_exercise", "What does your physical activity look like right now? Any exercise routine?"),
            ("activity_level", "Would you say you're mostly sedentary, lightly active, or quite active in general?"),
        ],
        OnboardingStage.HEALTH_HISTORY: [
            ("medical_conditions", "Do you have any health conditions I should know about? Diabetes, BP, thyroid, anything like that?"),
            ("medications", "Are you on any medications currently?"),
        ],
    }

    def get_or_create_profile(self, user_id: UUID, db: Session) -> UserProfile:
        """Get existing profile or create a new one."""
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

        if not profile:
            profile = UserProfile(
                user_id=user_id,
                onboarding_stage=OnboardingStage.NOT_STARTED.value,
                onboarding_started_at=datetime.utcnow(),
                questions_asked={},
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)

        return profile

    def extract_profile_data(
        self,
        user_message: str,
        assistant_response: str,
        profile: UserProfile,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Extract profile data from a conversation exchange.
        Returns dict of extracted fields.
        """
        extracted = {}
        message_lower = user_message.lower()

        # Extract age
        age_match = re.search(r'\b(\d{1,2})\s*(?:years?\s*old|yrs?\s*old|yo|y\.o\.?|age)\b', message_lower)
        if not age_match:
            age_match = re.search(r'\b(?:i am|i\'m|im)\s*(\d{1,2})\b', message_lower)
        if not age_match:
            # Check if message is just a number (standalone age response like "23")
            standalone_match = re.match(r'^\s*(\d{1,2})\s*\.?\s*$', user_message)
            if standalone_match:
                age_match = standalone_match
        if age_match:
            age = int(age_match.group(1))
            if 15 <= age <= 100:
                extracted["age"] = age

        # Extract gender
        if any(w in message_lower for w in ["i am a man", "i'm a man", "i am male", "i'm male", "male", "guy"]):
            extracted["gender"] = "male"
        elif any(w in message_lower for w in ["i am a woman", "i'm a woman", "i am female", "i'm female", "female", "girl", "lady"]):
            extracted["gender"] = "female"

        # Extract health goals
        for goal, keywords in self.GOAL_KEYWORDS.items():
            if any(kw in message_lower for kw in keywords):
                if not profile.primary_goal:
                    extracted["primary_goal"] = goal.value
                break

        # Extract work type
        for work_type, keywords in self.WORK_TYPE_KEYWORDS.items():
            if any(kw in message_lower for kw in keywords):
                extracted["work_type"] = work_type.value
                break

        # Extract diet type
        for diet_type, keywords in self.DIET_KEYWORDS.items():
            if any(kw in message_lower for kw in keywords):
                extracted["diet_type"] = diet_type.value
                break

        # Extract sleep hours
        sleep_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\s*(?:of\s*)?(?:sleep|night)', message_lower)
        if sleep_match:
            extracted["sleep_hours"] = float(sleep_match.group(1))

        # Extract stress level
        if "very high stress" in message_lower or "extremely stressed" in message_lower:
            extracted["stress_level"] = "very_high"
        elif "high stress" in message_lower or "very stressed" in message_lower:
            extracted["stress_level"] = "high"
        elif "moderate stress" in message_lower or "somewhat stressed" in message_lower:
            extracted["stress_level"] = "moderate"
        elif "low stress" in message_lower or "not stressed" in message_lower or "relaxed" in message_lower:
            extracted["stress_level"] = "low"

        # Extract meals per day
        meals_match = re.search(r'(\d)\s*(?:meals?\s*(?:a|per)\s*day|times?\s*(?:a|per)\s*day)', message_lower)
        if meals_match:
            extracted["meals_per_day"] = int(meals_match.group(1))

        # Extract water intake
        water_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:liters?|litres?|l)\s*(?:of\s*)?(?:water)?', message_lower)
        if water_match:
            extracted["water_intake_liters"] = float(water_match.group(1))

        # Extract weight
        weight_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:kgs?|kilos?|kg)\b', message_lower)
        if weight_match:
            weight = float(weight_match.group(1))
            if 30 <= weight <= 200:
                if "target" in message_lower or "goal" in message_lower or "want to" in message_lower:
                    extracted["target_weight_kg"] = weight
                else:
                    extracted["current_weight_kg"] = weight

        # Extract height
        height_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:cm|centimeter)', message_lower)
        if height_match:
            height = float(height_match.group(1))
            if 100 <= height <= 250:
                extracted["height_cm"] = height
        else:
            feet_match = re.search(r'(\d)\s*[\'\.]\s*(\d{1,2})\s*(?:\")?', message_lower)
            if feet_match:
                feet = int(feet_match.group(1))
                inches = int(feet_match.group(2))
                extracted["height_cm"] = round((feet * 30.48) + (inches * 2.54), 1)

        # Extract activity level
        if any(w in message_lower for w in ["sedentary", "no exercise", "don't exercise", "sitting all day"]):
            extracted["activity_level"] = ActivityLevel.SEDENTARY.value
        elif any(w in message_lower for w in ["lightly active", "walk sometimes", "occasional"]):
            extracted["activity_level"] = ActivityLevel.LIGHTLY_ACTIVE.value
        elif any(w in message_lower for w in ["moderately active", "exercise regularly", "few times a week"]):
            extracted["activity_level"] = ActivityLevel.MODERATELY_ACTIVE.value
        elif any(w in message_lower for w in ["very active", "daily exercise", "gym daily"]):
            extracted["activity_level"] = ActivityLevel.VERY_ACTIVE.value

        # Update profile with extracted data
        if extracted:
            self.update_profile(profile, extracted, db)

        return extracted

    def update_profile(self, profile: UserProfile, data: Dict[str, Any], db: Session) -> None:
        """Update profile with new data."""
        for key, value in data.items():
            if hasattr(profile, key) and value is not None:
                setattr(profile, key, value)

        # Update onboarding stage based on filled data
        self._update_onboarding_stage(profile)

        profile.updated_at = datetime.utcnow()
        db.commit()

    def _update_onboarding_stage(self, profile: UserProfile) -> None:
        """Update onboarding stage based on data completeness."""
        # Check completion of each stage
        basic_done = profile.age is not None or profile.occupation is not None
        goals_done = profile.primary_goal is not None
        lifestyle_done = profile.sleep_hours is not None or profile.stress_level is not None
        diet_done = profile.diet_type is not None or profile.meals_per_day is not None
        activity_done = profile.activity_level is not None

        if activity_done and diet_done and lifestyle_done and goals_done:
            profile.onboarding_stage = OnboardingStage.COMPLETED.value
            profile.onboarding_completed_at = datetime.utcnow()
        elif activity_done:
            profile.onboarding_stage = OnboardingStage.HEALTH_HISTORY.value
        elif diet_done:
            profile.onboarding_stage = OnboardingStage.PHYSICAL_ACTIVITY.value
        elif lifestyle_done:
            profile.onboarding_stage = OnboardingStage.DIET_HABITS.value
        elif goals_done:
            profile.onboarding_stage = OnboardingStage.LIFESTYLE.value
        elif basic_done:
            profile.onboarding_stage = OnboardingStage.HEALTH_GOALS.value
        else:
            profile.onboarding_stage = OnboardingStage.BASIC_INFO.value

    def get_next_question_context(self, profile: UserProfile) -> Optional[str]:
        """
        Get context for Arohi about what question to ask next.
        Returns None if onboarding is complete.
        """
        if profile.onboarding_stage == OnboardingStage.COMPLETED.value:
            return None

        missing = profile.get_missing_essential_data()
        if not missing:
            return None

        # Build context about what to ask
        context_parts = [
            "\n[ONBOARDING CONTEXT - Ask about these naturally, ONE at a time:]"
        ]

        # Add completion percentage
        completion = profile.get_completion_percentage()
        context_parts.append(f"Profile completion: {completion}%")

        # What we know
        known_parts = []
        if profile.age:
            known_parts.append(f"age ({profile.age})")
        if profile.primary_goal:
            known_parts.append(f"goal ({profile.primary_goal.replace('_', ' ')})")
        if profile.work_type:
            known_parts.append(f"work ({profile.work_type.replace('_', ' ')})")

        if known_parts:
            context_parts.append(f"Already know: {', '.join(known_parts)}")

        # What we need
        need_questions = {
            "age": "their age",
            "health_goal": "what health goal they want to work on",
            "work_type": "what kind of work they do (desk job, active, etc.)",
            "diet_type": "their diet preference (veg/non-veg)",
            "activity_level": "their current activity/exercise level",
            "sleep_pattern": "how many hours they sleep and quality",
            "stress_level": "their stress level",
        }

        still_need = [need_questions.get(m, m) for m in missing[:2]]  # Focus on next 2
        context_parts.append(f"Still need to know: {', '.join(still_need)}")
        context_parts.append("Ask about ONE of these naturally in the conversation - don't make it feel like a questionnaire.")

        return "\n".join(context_parts)

    def get_profile_context_for_llm(self, user_id: UUID, db: Session) -> str:
        """Get full profile context string for LLM."""
        profile = self.get_or_create_profile(user_id, db)

        context_parts = []

        # Add existing profile data
        profile_data = profile.to_context_string()
        if profile_data != "No profile data collected yet.":
            context_parts.append(f"[User Profile]\n{profile_data}")

        # Add onboarding context if not complete
        onboarding_context = self.get_next_question_context(profile)
        if onboarding_context:
            context_parts.append(onboarding_context)

        return "\n\n".join(context_parts) if context_parts else ""


# Singleton instance
profile_service = ProfileService()


def get_profile_service() -> ProfileService:
    """Get the profile service instance."""
    return profile_service
