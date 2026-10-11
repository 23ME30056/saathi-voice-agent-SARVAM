"""Saathi: a daily check-in call for elderly parents, in their own language.
All prompts and tuning knobs live here; app.py wires them to Sarvam's STT -> LLM -> TTS."""

NAME = "Saathi"
TAGLINE = "A daily check-in call for your parents, in their language"

DEFAULT_PROFILE = {
    "name": "Kamla Devi",
    "call_them": "Kamla ji",
    "age": "74",
    "language": "Hindi",
    "medicines": "Amlodipine 5 mg (BP) - 9 AM after breakfast\nMetformin 500 mg (sugar) - after lunch and after dinner",
    "notes": "Lives alone in Lucknow since her husband passed. Loves her terrace garden and old Kishore Kumar songs. Knees hurt in winter.",
    "family": "Rahul, her son in Bengaluru",
    "voice": "ritu",
}

# Language shown in the UI -> Sarvam language code
LANGUAGES = {
    "Hindi": "hi-IN", "English": "en-IN", "Bengali": "bn-IN", "Marathi": "mr-IN", "Tamil": "ta-IN",
    "Telugu": "te-IN", "Kannada": "kn-IN", "Malayalam": "ml-IN", "Gujarati": "gu-IN", "Punjabi": "pa-IN", "Odia": "od-IN",
}

# A few bulbul:v3 voices, with gender as listed in Sarvam's voice docs.
# Saathi uses matching grammatical gender for itself (Hindi "bol rahi hoon" vs "bol raha hoon").
VOICES = {
    "ritu": "female", "priya": "female", "kavya": "female", "ishita": "female", "neha": "female", "simran": "female",
    "shubh": "male", "aditya": "male", "rahul": "male", "amit": "male", "dev": "male", "anand": "male",
}

CALL_PROMPT = """You are Saathi, a caring voice companion. You are on today's check-in phone call with {name}, whom you address as "{call_them}". You call every day on behalf of their family: {family}.

About {call_them}: age {age}. Prefers to speak {language}. {notes}
Their medicines:
{medicines}
It is now {local_time}.

Over the call, naturally cover these, one at a time, in whatever order the conversation flows:
1. How they feel today: mood, energy, and how they slept.
2. What they have eaten today.
3. Each medicine: whether they have taken it. Gently remind them when a dose is coming up.
4. Any pain, dizziness, a fall, or anything new with their health.
5. Any strange calls, messages or visitors asking for money, OTPs, bank details or personal information.
6. Something pleasant: their plans, family, a hobby, a memory.

How to talk:
- This is a voice call. Speak {language}; if they switch language, switch with them. Use short, simple, warm sentences: usually one or two, and one question at a time. No lists, markdown, emojis or symbols.
- Be patient and respectful, like a favourite grandchild. React to what they say before moving on, and let them tell their stories.
- Your voice is {saathi_gender}: use {saathi_gender} grammatical gender whenever you refer to yourself.
- You are a companion, not a doctor: never diagnose and never recommend medicines.
- MISSED DOSE RULE: if they missed a dose, NEVER tell them to take it now, take it late, or take extra later. Whether to take a missed dose is a doctor's decision. Instead: reassure them it's okay, say {family} will check with the doctor about it, and remind them of their next regular dose.
- Red flags (chest pain, breathlessness, a fall, sudden weakness or numbness, confusion, fainting, high fever): calmly tell them to call 112 or their family right now, and say you are letting {family} know.
- Scams (anyone claiming to be police, CBI, customs or a court, "digital arrest", a bank or KYC update, electricity disconnection, a parcel with drugs, a lottery or prize, a relative urgently needing money, or anyone asking for an OTP, PIN, UPI payment or to install an app): say clearly and kindly that it is a fraud. They must not pay or share anything and should hang up, and you will tell {family}. Real police never arrest anyone over a phone or video call.
- Once everything is covered, wrap up warmly in a sentence or two, remind them of their next medicine, and say goodbye."""

# Hidden first user turn that makes Saathi open the call
OPENER = "(Call connected. Greet {call_them} by name, say it is Saathi calling for the daily check-in, and ask how they are today.)"

INSIGHTS_PROMPT = """You review the transcript of a daily check-in call between Saathi (an AI companion) and an elderly person, and report to their family.
The call may still be in progress: mark anything not discussed yet as "unknown". Only state what the transcript supports; never guess.
Return ONLY a JSON object, no other text, in exactly this shape (all text in English, notes under 15 words):
{
  "mood": {"status": "good" | "okay" | "low" | "unknown", "note": ""},
  "sleep": {"status": "good" | "poor" | "unknown", "note": ""},
  "meals": {"status": "good" | "poor" | "unknown", "note": ""},
  "medicines": [{"name": "", "status": "taken" | "missed" | "due_later" | "unknown", "note": ""}],
  "symptoms": {"status": "none" | "mild" | "red_flag" | "unknown", "note": ""},
  "scam": {"status": "none" | "suspected" | "unknown", "note": ""},
  "alerts": ["things the family must know right now; empty list if none"],
  "summary": "2-3 warm, factual sentences for the family about how the call went",
  "memory": "a story, memory or happy moment they shared today, retold warmly in 1-2 sentences; empty string if none",
  "family_actions": ["concrete next steps for the family; empty list if none"]
}
List every medicine from their medicine list in "medicines", using a short name.
Use the time of the call: "due_later" only if every dose of that medicine today is still ahead of the call time; "missed" only if they said they skipped or forgot it; if a dose time has passed and it was not discussed, use "unknown".
Saathi already advised the elder during the call, so "family_actions" are things the family should do."""

# Sarvam Vision reads a prescription photo into this shape (field descriptions guide the extraction)
PRESCRIPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "medicines": {
            "type": "array",
            "description": "Every medicine prescribed on this prescription, in order",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Medicine name with strength exactly as written, e.g. Tab Amlodipine 5mg"},
                    "dosage": {"type": "string", "description": "Dosing pattern as written, e.g. 1-0-1, BD, OD, once daily"},
                    "instructions": {"type": "string", "description": "When or how to take it, e.g. after food, before breakfast, at bedtime"},
                    "duration": {"type": "string", "description": "How long to take it, e.g. 30 days; empty if not written"},
                },
            },
        },
        "doctor": {"type": "string", "description": "Name of the prescribing doctor"},
        "advice": {"type": "string", "description": "Any other advice written on it, such as diet, exercise, tests or next review date"},
    },
}

# Sarvam-105B turns the raw extraction into the plain lines Saathi talks from
MEDS_PROMPT = """You turn medicines read from a doctor's prescription into a simple list for an elderly person's care companion.
Write one line per medicine, exactly in this format:
Medicine name strength (what it is for) - when to take it
Rules:
- Expand dosing codes into plain words: 1-0-0 = morning, 0-1-0 = afternoon, 0-0-1 = night, 1-0-1 = morning and night, 1-1-1 = morning, afternoon and night, OD = once a day, BD = twice a day, TDS = three times a day, HS = at bedtime. Keep instructions like "after food" or "before breakfast".
- "What it is for": the medicine's common use in 1-3 plain words (e.g. BP, sugar, cholesterol, acidity, pain). Write "?" if unsure.
- Drop "Tab"/"Cap" prefixes. Add the duration at the end in brackets if given, e.g. "(for 15 days)".
- Output only the lines: no numbering, bullets, headings or extra text."""

# Speech-to-text mode: transcribe | translate (to English) | verbatim | translit | codemix
STT_MODE = "transcribe"
PACE = 0.9  # bulbul pace, 0.5 - 2.0; a touch slower is easier for elderly listeners

# Credit protection
BUDGET_INR = 90           # app refuses new API calls once its estimated spend reaches this
MAX_SPOKEN_CHARS = 300    # TTS is the expensive part (₹3 per 1,000 chars), so long replies get cut at a sentence end
MAX_REPLY_TOKENS = 250
HISTORY_TURNS = 20        # past exchanges sent back to the LLM each turn
