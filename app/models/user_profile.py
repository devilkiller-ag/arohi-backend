"""User profile model for storing onboarding and health data."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Boolean, Integer, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class OnboardingStage(str, Enum):
    """Onboarding stages - tracks where user is in the intake process."""
    NOT_STARTED = "not_started"
    BASIC_INFO = "basic_info"           # Name, age, gender, occupation
    HEALTH_GOALS = "health_goals"       # Primary goals, timeline
    LIFESTYLE = "lifestyle"             # Work type, sleep, stress
    DIET_HABITS = "diet_habits"         # Eating patterns, restrictions
    PHYSICAL_ACTIVITY = "physical_activity"  # Exercise, activity level
    HEALTH_HISTORY = "health_history"   # Conditions, medications
    COMPLETED = "completed"             # All data collected


class HealthGoal(str, Enum):
    """Primary health goals."""
    WEIGHT_LOSS = "weight_loss"
    WEIGHT_GAIN = "weight_gain"
    BETTER_ENERGY = "better_energy"
    BETTER_SLEEP = "better_sleep"
    STRESS_MANAGEMENT = "stress_management"
    FITNESS = "fitness"
    HEALTHY_EATING = "healthy_eating"
    MANAGE_CONDITION = "manage_condition"
    GENERAL_WELLNESS = "general_wellness"


class WorkType(str, Enum):
    """Type of work/occupation."""
    DESK_JOB = "desk_job"           # Office, WFH
    ACTIVE_JOB = "active_job"       # Field work, standing
    HYBRID = "hybrid"               # Mix of both
    STUDENT = "student"
    HOMEMAKER = "homemaker"
    RETIRED = "retired"


class ActivityLevel(str, Enum):
    """Current physical activity level."""
    SEDENTARY = "sedentary"         # Little to no exercise
    LIGHTLY_ACTIVE = "lightly_active"  # Light exercise 1-3 days/week
    MODERATELY_ACTIVE = "moderately_active"  # Moderate exercise 3-5 days/week
    VERY_ACTIVE = "very_active"     # Hard exercise 6-7 days/week
    ATHLETE = "athlete"             # Professional/intense training


class DietType(str, Enum):
    """Dietary preferences."""
    VEGETARIAN = "vegetarian"
    NON_VEGETARIAN = "non_vegetarian"
    VEGAN = "vegan"
    EGGETARIAN = "eggetarian"
    PESCATARIAN = "pescatarian"
    NO_PREFERENCE = "no_preference"


class UserProfile(Base):
    """
    Stores comprehensive user health profile data collected during onboarding.
    This ensures Arohi has all the context needed to provide personalized advice.
    """

    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # ===== ONBOARDING TRACKING =====
    onboarding_stage = Column(String(50), default=OnboardingStage.NOT_STARTED.value)
    onboarding_started_at = Column(DateTime, nullable=True)
    onboarding_completed_at = Column(DateTime, nullable=True)

    # Questions asked in each stage (to avoid repeating)
    questions_asked = Column(JSON, default=dict)  # {"basic_info": ["age", "gender"], "diet": [...]}

    # ===== BASIC INFO =====
    age = Column(Integer, nullable=True)
    gender = Column(String(20), nullable=True)  # male, female, other, prefer_not_to_say
    location_city = Column(String(100), nullable=True)
    occupation = Column(String(100), nullable=True)
    work_type = Column(String(50), nullable=True)  # WorkType enum value

    # ===== HEALTH GOALS =====
    primary_goal = Column(String(50), nullable=True)  # HealthGoal enum value
    secondary_goals = Column(JSON, default=list)  # List of additional goals
    goal_timeline = Column(String(50), nullable=True)  # "1_month", "3_months", "6_months", "1_year", "no_rush"
    goal_motivation = Column(Text, nullable=True)  # Why they want to achieve this
    previous_attempts = Column(Text, nullable=True)  # What they've tried before

    # ===== LIFESTYLE =====
    work_hours_per_day = Column(Integer, nullable=True)
    work_schedule = Column(String(50), nullable=True)  # "regular_9_to_5", "shifts", "flexible", "irregular"
    sleep_hours = Column(Float, nullable=True)
    sleep_quality = Column(String(20), nullable=True)  # "poor", "average", "good", "excellent"
    sleep_time = Column(String(20), nullable=True)  # "before_10pm", "10pm_12am", "after_12am"
    wake_time = Column(String(20), nullable=True)  # "before_6am", "6am_8am", "after_8am"
    stress_level = Column(String(20), nullable=True)  # "low", "moderate", "high", "very_high"
    stress_triggers = Column(Text, nullable=True)

    # ===== DIET HABITS =====
    diet_type = Column(String(30), nullable=True)  # DietType enum value
    meals_per_day = Column(Integer, nullable=True)
    breakfast_habit = Column(String(20), nullable=True)  # "always", "sometimes", "rarely", "never"
    cooking_frequency = Column(String(20), nullable=True)  # "daily", "few_times_week", "rarely", "never"
    eating_out_frequency = Column(String(20), nullable=True)  # "daily", "few_times_week", "weekly", "rarely"
    water_intake_liters = Column(Float, nullable=True)
    snacking_habit = Column(String(20), nullable=True)  # "none", "healthy", "unhealthy", "mixed"
    food_allergies = Column(JSON, default=list)  # List of allergies
    food_dislikes = Column(JSON, default=list)  # Foods they don't like

    # ===== PHYSICAL ACTIVITY =====
    activity_level = Column(String(30), nullable=True)  # ActivityLevel enum value
    current_exercise = Column(Text, nullable=True)  # What they currently do
    exercise_frequency = Column(String(20), nullable=True)  # "none", "1-2_times", "3-4_times", "5+_times"
    preferred_exercise = Column(JSON, default=list)  # Types they enjoy
    physical_limitations = Column(Text, nullable=True)  # Injuries, conditions affecting exercise
    has_gym_access = Column(Boolean, nullable=True)

    # ===== HEALTH HISTORY =====
    medical_conditions = Column(JSON, default=list)  # Diabetes, hypertension, thyroid, etc.
    medications = Column(JSON, default=list)  # Current medications
    supplements = Column(JSON, default=list)  # Current supplements
    family_health_history = Column(Text, nullable=True)
    recent_health_checkup = Column(Boolean, nullable=True)

    # ===== BODY METRICS (optional) =====
    height_cm = Column(Float, nullable=True)
    current_weight_kg = Column(Float, nullable=True)
    target_weight_kg = Column(Float, nullable=True)

    # ===== PREFERENCES =====
    preferred_contact_time = Column(String(20), nullable=True)  # "morning", "afternoon", "evening", "anytime"
    motivation_style = Column(String(30), nullable=True)  # "gentle", "firm", "data_driven", "supportive"
    budget_constraints = Column(Boolean, default=False)

    # ===== TIMESTAMPS =====
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="profile")

    def __repr__(self):
        return f"<UserProfile for user {self.user_id}, stage: {self.onboarding_stage}>"

    def get_completion_percentage(self) -> int:
        """Calculate how much of the profile is filled."""
        important_fields = [
            self.age, self.gender, self.occupation, self.primary_goal,
            self.work_type, self.sleep_hours, self.stress_level,
            self.diet_type, self.meals_per_day, self.activity_level
        ]
        filled = sum(1 for f in important_fields if f is not None)
        return int((filled / len(important_fields)) * 100)

    def get_missing_essential_data(self) -> list:
        """Return list of essential data that's still missing."""
        missing = []
        if not self.age:
            missing.append("age")
        if not self.primary_goal:
            missing.append("health_goal")
        if not self.work_type:
            missing.append("work_type")
        if not self.diet_type:
            missing.append("diet_type")
        if not self.activity_level:
            missing.append("activity_level")
        if not self.sleep_hours:
            missing.append("sleep_pattern")
        if not self.stress_level:
            missing.append("stress_level")
        return missing

    def to_context_string(self) -> str:
        """Convert profile to a context string for LLM."""
        parts = []

        if self.age:
            parts.append(f"Age: {self.age}")
        if self.gender:
            parts.append(f"Gender: {self.gender}")
        if self.occupation:
            parts.append(f"Occupation: {self.occupation}")
        if self.work_type:
            parts.append(f"Work type: {self.work_type.replace('_', ' ')}")
        if self.primary_goal:
            parts.append(f"Primary goal: {self.primary_goal.replace('_', ' ')}")
        if self.goal_motivation:
            parts.append(f"Motivation: {self.goal_motivation}")
        if self.sleep_hours:
            parts.append(f"Sleep: {self.sleep_hours} hours/night")
        if self.stress_level:
            parts.append(f"Stress level: {self.stress_level}")
        if self.diet_type:
            parts.append(f"Diet: {self.diet_type.replace('_', ' ')}")
        if self.activity_level:
            parts.append(f"Activity level: {self.activity_level.replace('_', ' ')}")
        if self.medical_conditions:
            parts.append(f"Medical conditions: {', '.join(self.medical_conditions)}")
        if self.physical_limitations:
            parts.append(f"Physical limitations: {self.physical_limitations}")
        if self.height_cm and self.current_weight_kg:
            bmi = self.current_weight_kg / ((self.height_cm / 100) ** 2)
            parts.append(f"BMI: {bmi:.1f}")
        if self.target_weight_kg:
            parts.append(f"Target weight: {self.target_weight_kg} kg")

        return "\n".join(parts) if parts else "No profile data collected yet."
