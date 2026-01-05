"""Service for managing user profiles and onboarding data extraction."""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.user_profile import (
    UserProfile,
    OnboardingStage,
)


class ProfileService:
    """Service for managing user health profiles and tracking onboarding progress.

    Profile data extraction is now handled by the LLM service for:
    - Language agnostic extraction (English, Hindi, Hinglish)
    - Better understanding of context and nuance
    - No need to maintain complex regex patterns
    """

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
        Extract profile data from a conversation exchange using LLM.
        Works with any language (English, Hindi, Hinglish).
        """
        from app.services.llm_service import get_llm_service

        llm_service = get_llm_service()
        extracted = llm_service.extract_profile_data(user_message, assistant_response)

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
        activity_done = profile.activity_level is not None or profile.current_exercise is not None

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
        if profile.diet_type:
            known_parts.append(f"diet ({profile.diet_type.replace('_', ' ')})")
        if profile.current_exercise:
            known_parts.append(f"exercise ({profile.current_exercise[:30]})")

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
