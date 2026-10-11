# Saathi: a daily check-in call for your parents

Saathi is an AI voice companion that **calls elderly parents every day, talks to them in their own language, and tells the family how they are doing.**

Built with Sarvam AI's speech and language models.

---

## The problem

Many elderly parents in India live alone while their children work in other cities. The family worries, but can't call every day. When they do call, the conversation is usually short, and it often misses things like:

- **Medicines:** did they take their BP or sugar tablet today?
- **Health:** a fall, dizziness or chest pain that they "didn't want to bother anyone about"
- **Loneliness:** a whole day without anyone to talk to
- **Scams:** seniors are a top target for fake calls like *"I am from CBI, you are under digital arrest"*, *"your KYC is expiring, tell me the OTP"* or *"your electricity will be cut tonight"*. Many lose their savings before the family even hears about it.

There is also a language gap: most apps and helplines work in English, but many elderly people are most comfortable in Hindi, Tamil, Bengali, Marathi and other regional languages.

## The idea

This project comes from the **"Elder Companion Agent"** idea in the Sarvam idea library:

> - Check in on seniors daily through friendly voice calls covering wellbeing, mood, meals, and medication in their regional language.
> - Support health and safety by reminding about medicines and appointments, capturing symptoms, and warning against scams and fraudulent calls.
> - Keep families informed with daily wellbeing summaries and proactive alerts for missed calls, health red flags, or emergencies via WhatsApp or phone.

## Our solution: Saathi

**1. The family sets it up once.** They enter the parent's name, language, medicines (with timings), a few personal details (hobbies, health issues), and pick a voice.

**2. Saathi makes the call.** It greets them by name and has a warm, natural conversation like a caring grandchild would. Without making it feel like a checklist, it finds out:
   - how they feel today and how they slept
   - what they ate
   - whether each medicine was taken, with a gentle reminder if one was missed
   - any pain, fall or new health problem
   - whether anyone suspicious called or messaged them
   - something happy: their plans, a hobby, an old memory

**3. It keeps them safe during the call.**
   - **Scam shield:** if they mention a suspicious call (fake police, KYC, OTP, lottery, a "relative" needing money), Saathi immediately and kindly tells them it's a fraud, tells them not to pay or share anything, and flags it for the family.
   - **Health red flags:** for chest pain, a fall, breathlessness or similar, Saathi tells them to call 112 or family right away and raises an alert. *Saathi never diagnoses or suggests medicines.*

**4. The family gets a report.** When the call ends, Saathi writes a short report card with mood, sleep, meals, each medicine, health, scam check, alerts and suggested next steps. It can be sent to the family on **WhatsApp** in one tap.

### What makes it special

| Feature | Why it matters |
|---|---|
| Speaks 11 Indian languages, follows them if they switch | Parents talk the way they're comfortable |
| Live checklist that fills in during the call | You can see the call's progress at a glance |
| Scam shield | Protects against the scams that target seniors most |
| "Memory of the day" | Saves a story they told (e.g. *"the rose your grandfather planted bloomed today"*), so the family gets something to smile about, not just a medical log |
| Voice and grammar match | A male voice says "बोल रहा हूँ", a female voice says "बोल रही हूँ" |
| Slightly slower speech | Easier for elderly listeners |

---

## How it works

```
 Parent speaks        Saaras v3           Sarvam-105B            Bulbul v3         Parent hears
 (any language)  ──►  speech → text  ──►  thinks of a caring ──►  text → voice  ──►  Saathi reply
                                          reply
                                              │
                                              ▼
                                          Sarvam-105B (2nd job)
                                          reads the whole call → live checklist + family report
```

| Sarvam model | What it does in Saathi |
|---|---|
| **Saaras v3** (speech-to-text) | Understands what the parent says, in any Indian language, and detects which language it is |
| **Sarvam-105B** (LLM) | Has the conversation, and separately turns the call into a structured health and safety report |
| **Bulbul v3** (text-to-speech) | Speaks Saathi's replies in a natural Indian voice |

---

## Try it: a 2-minute demo

The form comes pre-filled with a demo grandmother, **Kamla ji (74, Lucknow, speaks Hindi)**. Click **Start today's call** and try saying:

1. **"हाँ बेटा, ठीक हूँ। बस रात को घुटनों में दर्द था, नींद नहीं आई।"**
   *(I'm fine, but my knees hurt at night and I couldn't sleep.)* The checklist updates sleep and health.
2. **"आज एक आदमी का फोन आया, बोला CBI से हूँ, डिजिटल अरेस्ट होगा, OTP बताओ।"**
   *(A man called saying he's from CBI, I'll be under digital arrest, tell him the OTP.)* Saathi warns her it's a scam, and an alert appears.
3. **"सुबह की BP की गोली ले ली, पर शुगर की गोली भूल गई।"**
   *(I took my BP tablet but forgot the sugar one.)* Medicines are marked taken and missed.
4. **"आज छत पर गुलाब में पहला फूल आया।"**
   *(The first rose bloomed on the terrace today.)* This becomes the memory of the day.
5. Click **End call** to see the family report and **Send on WhatsApp**.

---

## Run it on your computer

You need Python 3.10+ and a Sarvam API key from [dashboard.sarvam.ai](https://dashboard.sarvam.ai).

```bash
pip install -r requirements.txt
```

Create a file called `.env` in this folder:

```
SARVAM_API_KEY=your_key_here
```

Start it:

```bash
python app.py
```

Open **http://127.0.0.1:8000** in Chrome or Edge and allow microphone access.

**Tips**
- Tap the mic and talk. Pause for a moment and it sends automatically.
- Tap the mic while Saathi is talking to interrupt.
- No mic? Type in the box instead.

### Cost

New Sarvam accounts get ₹100 of free credits. A full call (8–10 replies) costs about **₹4–6**, and most of that is the voice. To test cheaply, turn off **Voice replies** and type: that costs almost nothing. The app shows estimated spend in the top-right corner and stops making calls once it reaches ₹90 (change `BUDGET_INR` in `persona.py`).

---

## Project files

| File | What's inside |
|---|---|
| `persona.py` | Saathi's personality, conversation rules, report format, demo profile, voices, budget. **Change this to change the agent.** |
| `app.py` | The web server: handles calls, turns and reports |
| `sarvam.py` | Talks to Sarvam's APIs and tracks credit spend |
| `static/index.html` | The web page: setup form, call screen, report |

---

## Limits (v1)

- It runs in a web browser and doesn't place real phone calls yet.
- The report is sent through a WhatsApp share link; automatic alerts aren't built yet.
- Each conversation is kept in memory and disappears if the server restarts.
- Saathi is a companion, not a medical service. It never diagnoses or advises on medicines.

## What's next

- **Real phone calls** at a fixed time every day, so it works on any phone, including feature phones
- **Snap the prescription:** take a photo and Sarvam Vision fills in the medicine list automatically
- **Automatic WhatsApp alerts** to the family the moment a scam or health red flag comes up
- **Weekly trends:** mood, sleep and medicine adherence over time
- **Online deployment** so families can use it from anywhere
