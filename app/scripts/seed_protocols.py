"""Seed script for initial medical protocols."""

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.protocol import Protocol


INITIAL_PROTOCOLS = [
    {
        "name": "Fever Management",
        "keywords": ["fever", "temperature", "hot", "chills", "shivering"],
        "content": """Fever Management Protocol:
- Rest and stay hydrated with water, oral rehydration solutions, or clear broths
- Take paracetamol (500mg) for adults if temperature exceeds 100.4°F (38°C)
- Use light clothing and cool compresses on forehead
- Seek immediate medical attention if: fever exceeds 103°F (39.4°C), persists more than 3 days, or is accompanied by severe headache, stiff neck, or rash
- For children under 3 months with any fever, seek immediate medical care""",
        "priority": 5,
    },
    {
        "name": "Headache Relief",
        "keywords": ["headache", "head pain", "migraine", "head hurts", "head ache"],
        "content": """Headache Management Protocol:
- Rest in a quiet, dark room if sensitive to light/sound
- Stay hydrated and avoid skipping meals
- Apply cold or warm compress to forehead or neck
- Over-the-counter pain relievers like paracetamol or ibuprofen can help
- Seek immediate care if: sudden severe headache (worst of your life), headache with fever and stiff neck, headache after head injury, or accompanied by confusion, vision changes, or weakness""",
        "priority": 4,
    },
    {
        "name": "Cold and Flu",
        "keywords": ["cold", "flu", "runny nose", "congestion", "cough", "sneezing", "sore throat"],
        "content": """Cold and Flu Management Protocol:
- Rest as much as possible and stay home to prevent spreading
- Drink plenty of warm fluids: water, herbal tea, warm lemon water with honey
- Gargle with warm salt water for sore throat
- Use steam inhalation for congestion (be careful with hot water)
- Over-the-counter medicines can help with symptoms
- Seek medical care if: symptoms last more than 10 days, difficulty breathing, persistent chest pain, or high fever lasting more than 3 days""",
        "priority": 4,
    },
    {
        "name": "Stomach Issues",
        "keywords": ["stomach", "diarrhea", "vomiting", "nausea", "acidity", "indigestion", "gas", "bloating"],
        "content": """Digestive Health Protocol:
- For diarrhea/vomiting: Focus on oral rehydration (ORS), avoid solid food initially, then BRAT diet (bananas, rice, applesauce, toast)
- For acidity: Avoid spicy/oily food, eat smaller frequent meals, don't lie down after eating
- For gas/bloating: Avoid carbonated drinks, eat slowly, limit beans and cruciferous vegetables
- Seek medical care if: blood in stool/vomit, severe abdominal pain, signs of dehydration, or symptoms lasting more than 48 hours""",
        "priority": 4,
    },
    {
        "name": "Sleep Hygiene",
        "keywords": ["sleep", "insomnia", "can't sleep", "sleeping", "tired", "fatigue", "exhausted"],
        "content": """Sleep Hygiene Protocol:
- Maintain consistent sleep and wake times, even on weekends
- Create a relaxing bedtime routine (reading, warm bath, light stretching)
- Keep bedroom cool (65-68°F), dark, and quiet
- Avoid screens (phone, TV) at least 1 hour before bed
- Limit caffeine after 2 PM and avoid heavy meals before bed
- Regular exercise helps, but not within 3 hours of bedtime
- If insomnia persists beyond 2-3 weeks, consult a doctor""",
        "priority": 3,
    },
    {
        "name": "Stress and Anxiety",
        "keywords": ["stress", "anxiety", "anxious", "worried", "panic", "nervous", "overwhelmed", "tension"],
        "content": """Stress and Anxiety Management Protocol:
- Practice deep breathing: 4 seconds inhale, 7 seconds hold, 8 seconds exhale
- Try progressive muscle relaxation or meditation
- Regular physical activity (even a 15-minute walk helps)
- Limit caffeine and alcohol
- Talk to someone you trust about your feelings
- Maintain a regular sleep schedule
- Consider journaling to process thoughts
- If anxiety interferes with daily life or includes panic attacks, consult a mental health professional""",
        "priority": 4,
    },
    {
        "name": "Back Pain",
        "keywords": ["back pain", "back hurts", "lower back", "spine", "back ache"],
        "content": """Back Pain Management Protocol:
- For acute pain: Apply ice for first 48-72 hours, then switch to heat
- Maintain gentle movement - complete bed rest not recommended
- Over-the-counter pain relievers can provide relief
- Practice good posture, especially when sitting for long periods
- Gentle stretching and walking can help
- Seek immediate care if: pain follows an injury, numbness/tingling in legs, loss of bladder/bowel control, or severe pain that doesn't improve with rest""",
        "priority": 4,
    },
    {
        "name": "Diabetes Management",
        "keywords": ["diabetes", "sugar", "blood sugar", "glucose", "diabetic"],
        "content": """Diabetes Care Protocol:
- Monitor blood sugar regularly as advised by your doctor
- Follow a balanced diet: complex carbs, fiber, lean protein, healthy fats
- Limit refined sugars and processed foods
- Regular physical activity helps manage blood sugar
- Take medications as prescribed, never skip doses
- Check feet daily for cuts or sores
- Regular eye and kidney check-ups are important
- Know the signs of low blood sugar: shakiness, sweating, confusion
- Always consult your doctor before making changes to medication or diet""",
        "priority": 5,
    },
    {
        "name": "Hypertension",
        "keywords": ["blood pressure", "bp", "hypertension", "high blood pressure"],
        "content": """Blood Pressure Management Protocol:
- Reduce sodium intake (aim for less than 2,300mg/day)
- Follow DASH diet: fruits, vegetables, whole grains, lean proteins
- Maintain healthy weight
- Regular physical activity: 30 minutes most days
- Limit alcohol and quit smoking
- Manage stress through relaxation techniques
- Take medications exactly as prescribed
- Monitor blood pressure at home regularly
- Seek immediate care if BP exceeds 180/120 with symptoms like chest pain, headache, or shortness of breath""",
        "priority": 5,
    },
    {
        "name": "Emergency Red Flags",
        "keywords": ["chest pain", "breathing", "stroke", "heart attack", "emergency", "severe pain", "unconscious"],
        "content": """EMERGENCY - Seek Immediate Medical Care For:
- Chest pain or pressure, especially with arm pain, jaw pain, or shortness of breath
- Sudden difficulty breathing or severe shortness of breath
- Signs of stroke (FAST): Face drooping, Arm weakness, Speech difficulty, Time to call emergency
- Sudden severe headache (worst headache of your life)
- Severe abdominal pain
- Heavy bleeding that won't stop
- Loss of consciousness
- Severe allergic reaction (difficulty breathing, swelling of throat)
- Suicidal thoughts or self-harm

CALL EMERGENCY SERVICES IMMEDIATELY - In India: 112 or 108""",
        "priority": 10,
    },
]


def seed_protocols(db: Session):
    """Seed the database with initial protocols."""
    # Check if protocols already exist
    existing_count = db.query(Protocol).count()
    if existing_count > 0:
        print(f"Protocols already seeded ({existing_count} found). Skipping...")
        return

    # Add protocols
    for protocol_data in INITIAL_PROTOCOLS:
        protocol = Protocol(**protocol_data)
        db.add(protocol)

    db.commit()
    print(f"Successfully seeded {len(INITIAL_PROTOCOLS)} protocols.")


def main():
    """Run the seeder."""
    db = SessionLocal()
    try:
        seed_protocols(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
