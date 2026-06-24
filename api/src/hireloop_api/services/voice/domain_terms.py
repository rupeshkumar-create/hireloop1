"""
Domain keyterms for Deepgram nova-3 keyterm prompting.

Boosting these high-value, easily-misheard India-recruiting terms measurably
improves transcription on a noisy phone screen — money units ("LPA", "lakh"),
Indian city/company names, and common tech skills are exactly what a generic
model garbles ("LPA" → "LP a", "Bengaluru" → "Bangalore loo", etc.).

Keep this list tight (Deepgram weights a focused set better than a giant one).
"""

from __future__ import annotations

INDIA_RECRUITING_KEYTERMS: list[str] = [
    # Compensation / process vocabulary
    "LPA",
    "lakh",
    "lakhs",
    "crore",
    "CTC",
    "in-hand",
    "notice period",
    "appraisal",
    "fresher",
    "PPO",
    # Cities / hubs
    "Bengaluru",
    "Gurugram",
    "Noida",
    "Hyderabad",
    "Pune",
    "Chennai",
    "Gurgaon",
    # Common employers candidates name
    "Razorpay",
    "Zerodha",
    "Flipkart",
    "Swiggy",
    "Zomato",
    "Infosys",
    "TCS",
    # High-frequency skills
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "React",
    "Node",
    "FastAPI",
    "Kubernetes",
    "PostgreSQL",
]
