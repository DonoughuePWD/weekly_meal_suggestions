#!/usr/bin/env python3
"""
Weekly dinner suggestions (LLM-powered) + email sender.

What it does
- Takes a list of recipe links (URLs) you curate (recipes.txt).
- Sends those links (plus scraped page titles) to an LLM to propose:
  1) Seven *suggestions* for dinners (using only the provided links)
  2) A "things we'd need to have" list (non-staples only; no quantities)
- Emails the result once per week (schedule externally via Windows Task Scheduler).

OpenAI API (Responses API)
- POST https://api.openai.com/v1/responses
- Bearer auth with OPENAI_API_KEY

Config (env vars)
- OPENAI_API_KEY          (required)
- OPENAI_MODEL            (optional) default: gpt-5.2
- EMAIL_USER              (required) SMTP username
- EMAIL_PASS              (required) SMTP password / app password
- EMAIL_TO                (required) recipient email
- SMTP_HOST               (optional) default: smtp.gmail.com
- SMTP_PORT               (optional) default: 587
- EMAIL_SUBJECT_PREFIX    (optional) default: "Suggestions for things to eat this week"
- MEALS_PER_WEEK          (optional) default: 7
- RECIPES_FILE            (optional) path to text file with one URL per line.
                           default: recipes.txt beside this script.
- INCLUDE_SWEETS          (optional) set to "1" to include dessert/sweet links. default: exclude.
"""

from __future__ import annotations

import os
import json
import time
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import List
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# -------------------------- URL list + filtering


DEFAULT_URLS: List[str] = [
    # Optional fallback list if you don't want to use recipes.txt.
]

DESSERT_KEYWORDS = {
    "cookie", "cookies", "cake", "brownie", "brownies", "muffin", "muffins",
    "banana-bread", "bananabread", "banana_bread", "loaf", "cupcake", "cupcakes",
    "slice", "biscuit", "biscuits", "pudding", "pie", "tart", "donut", "doughnut",
    "fudge", "ice-cream", "icecream", "gelato", "sweet", "dessert",
    "chocolate", "nutella", "caramel", "smoothie",
}

def is_probably_sweet_url(url: str) -> bool:
    p = urlparse(url)
    hay = (p.path + " " + p.query).lower()
    return any(k in hay for k in DESSERT_KEYWORDS)

def load_recipe_urls() -> List[str]:
    recipes_file = os.getenv("RECIPES_FILE")
    if not recipes_file:
        recipes_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recipes.txt")

    urls: List[str] = []
    if os.path.exists(recipes_file):
        with open(recipes_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                urls.append(line)
    else:
        urls = list(DEFAULT_URLS)

    urls = [u.strip() for u in urls if u and u.strip().startswith("http")]

    include_sweets = os.getenv("INCLUDE_SWEETS", "").strip() == "1"
    if not include_sweets:
        urls = [u for u in urls if not is_probably_sweet_url(u)]

    # De-dupe preserving order
    seen = set()
    out: List[str] = []
    for u in urls:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out

# ------------- Fetch page titles (helps the LLM)


@dataclass
class LinkMeta:
    url: str
    title: str

def fetch_title(url: str, timeout: int = 12) -> str:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"].strip()
        if soup.title and soup.title.string:
            return soup.title.string.strip()
    except Exception:
        pass
    return ""

def build_link_metas(urls: List[str], max_to_fetch: int = 60) -> List[LinkMeta]:
    metas: List[LinkMeta] = []
    for u in urls[:max_to_fetch]:
        metas.append(LinkMeta(url=u, title=fetch_title(u)))
        time.sleep(0.2)
    for u in urls[max_to_fetch:]:
        metas.append(LinkMeta(url=u, title=""))
    return metas

# -------------------------- ----API call (using Open AI)

def call_openai_suggestions(link_metas: List[LinkMeta], meals_per_week: int) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable must be set.")
    model = os.getenv("OPENAI_MODEL", "gpt-5.2").strip()

    link_lines = []
    for m in link_metas:
        if m.title:
            link_lines.append(f"- {m.title} — {m.url}")
        else:
            link_lines.append(f"- {m.url}")
    links_block = "\n".join(link_lines)

    staples = [
        "salt", "pepper", "oil", "olive oil", "vegetable oil",
        "butter", "flour", "sugar", "rice", "pasta", "noodles",
        "bread", "stock cubes", "soy sauce", "vinegar",
        "garlic", "onion", "lemon", "water",
    ]

    prompt = f"""
You are helping a household with dinner ideas. You will be given a curated list of recipe links (titles included when available).

Produce:

1) Seven *suggestions* for dinners (exactly {meals_per_week}).
   For each suggestion:
   - Include the recipe title
   - Include the URL
   - Add ONE short sentence (max ~18 words) summarising what the dish is (e.g., protein + style + key flavour/ingredient).

Rules:
- Choose from the provided links ONLY (do not invent URLs).
- Avoid desserts/sweets and avoid non-recipe pages.
- Keep the tone casual and framed as suggestions (not a strict day-by-day plan).

2) A section titled "Things we'd need to have" with NO quantities.
   - Include only *non-staples* that someone might need to buy specially (e.g., chicken thighs, salmon, fresh herbs, coconut milk).
   - Do NOT include common pantry staples like: {", ".join(staples)}.
   - Do NOT include measurements (no grams/ml/cups/tbsp).
   - Group into exactly these headings:
     - Protein
     - Produce
     - Other
   - If unsure, omit.

Output format (exact):
- Start with a one-line greeting.
- Then a section header: "Suggestions"
- Then suggestions as a numbered list 1..{meals_per_week}, each on ONE line:
  "1. <Title> — <URL> — <one-sentence summary>"
- Then a blank line and the header: "Things we'd need to have"
- Then the three group headings with bullet lists.
- Refer to it as "our" recipe list, not "your" recipe list
- Use Australian names for produce, e.g. eggplant, not aubergine 

Recipe links:
{links_block}
""".strip()

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
    }

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI API error {resp.status_code}: {resp.text}")

    data = resp.json()

    chunks: List[str] = []
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") in ("output_text", "text"):
                chunks.append(c.get("text", ""))
    text = "\n".join(chunks).strip()
    if not text:
        text = (data.get("output_text") or "").strip()
    if not text:
        raise RuntimeError("OpenAI API returned no text output.")
    return text

# --------- the email part 


def send_email(body: str) -> None:
    email_user = os.getenv("EMAIL_USER", "").strip()
    email_pass = os.getenv("EMAIL_PASS", "").strip()
    email_to = os.getenv("EMAIL_TO", "").strip()

    if not (email_user and email_pass and email_to):
        raise RuntimeError("EMAIL_USER, EMAIL_PASS and EMAIL_TO environment variables must be set.")

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587").strip())

    subject_prefix = os.getenv("EMAIL_SUBJECT_PREFIX", "Suggestions for things to eat this week").strip()
    subject = f"{subject_prefix} — {time.strftime('%Y-%m-%d')}"

    msg = EmailMessage()
    msg["From"] = email_user
    msg["To"] = email_to
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(email_user, email_pass)
        server.send_message(msg)

# -------------------- main (running program)


def main() -> int:
    urls = load_recipe_urls()
    if not urls:
        print("No recipe URLs found. Add URLs to recipes.txt (one per line) or DEFAULT_URLS in the script.")
        return 2

    meals_per_week = int(os.getenv("MEALS_PER_WEEK", "7").strip())
    metas = build_link_metas(urls)
    body = call_openai_suggestions(metas, meals_per_week)
    send_email(body)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
