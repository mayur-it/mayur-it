#!/usr/bin/env python3
"""Fetches WakaTime (all-time) + GitHub stats and updates README.md."""

import os
import re
import base64
import requests
from collections import defaultdict
from datetime import datetime, timezone

WAKATIME_API_KEY = os.environ["WAKATIME_API_KEY"]
GH_TOKEN = os.environ["GH_TOKEN"]
GH_USERNAME = os.environ.get("GH_USERNAME", "mayur-it")
README_PATH = "README.md"
START_MARKER = "<!--START_SECTION:waka-->"
END_MARKER = "<!--END_SECTION:waka-->"

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TIME_SLOTS = ["Morning", "Daytime", "Evening", "Night"]
TIME_ICONS = {"Morning": "🌞", "Daytime": "🌆", "Evening": "🌃", "Night": "🌙"}


def waka_headers():
    encoded = base64.b64encode(WAKATIME_API_KEY.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def gh_headers():
    return {"Authorization": f"Bearer {GH_TOKEN}"}


def progress_bar(pct, width=25):
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


# ── WakaTime ─────────────────────────────────────────────────────────────────

def get_waka_alltime():
    r = requests.get(
        "https://wakatime.com/api/v1/users/current/stats/all_time",
        headers=waka_headers(),
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("data", {})


# ── GitHub ────────────────────────────────────────────────────────────────────

def get_day_distribution():
    """Commits by day-of-week from the GitHub contribution calendar (last year)."""
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays { weekday contributionCount }
            }
          }
        }
      }
    }
    """
    r = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": {"login": GH_USERNAME}},
        headers=gh_headers(),
        timeout=30,
    )
    r.raise_for_status()
    weeks = (
        r.json()["data"]["user"]["contributionsCollection"]
        ["contributionCalendar"]["weeks"]
    )
    counts = defaultdict(int)
    for week in weeks:
        for day in week["contributionDays"]:
            # GitHub weekday: 0=Sunday → convert to 0=Monday
            idx = (day["weekday"] - 1) % 7
            counts[idx] += day["contributionCount"]
    return counts


def get_time_distribution():
    """Commits by time-of-day from recent GitHub push events (last 100 events)."""
    r = requests.get(
        f"https://api.github.com/users/{GH_USERNAME}/events?per_page=100",
        headers=gh_headers(),
        timeout=30,
    )
    r.raise_for_status()
    counts = defaultdict(int)
    for event in r.json():
        if event.get("type") != "PushEvent":
            continue
        hour = datetime.fromisoformat(
            event["created_at"].replace("Z", "+00:00")
        ).hour
        if 6 <= hour < 12:
            counts["Morning"] += 1
        elif 12 <= hour < 18:
            counts["Daytime"] += 1
        elif 18 <= hour < 24:
            counts["Evening"] += 1
        else:
            counts["Night"] += 1
    return counts


# ── Formatting ────────────────────────────────────────────────────────────────

def build_section(waka, day_counts, time_counts):
    lines = []

    # Total all-time coding time badge
    total = waka.get(
        "human_readable_total_including_other_language",
        waka.get("human_readable_total", "N/A"),
    )
    safe_total = total.replace(" ", "%20")
    lines += [
        f"![All Time Code](https://img.shields.io/badge/All%20Time%20Coding-{safe_total}-blue?style=flat)",
        "",
    ]

    # Time-of-day distribution
    total_time = sum(time_counts.values()) or 1
    if total_time > 1:
        peak = max(time_counts, key=time_counts.get)
        label = {"Morning": "Early 🐤", "Daytime": "Day Worker 🦅",
                 "Evening": "Evening Coder 🌆", "Night": "Night Owl 🦉"}
        lines += [f"**I'm an {label.get(peak, peak)}**", "", "```text"]
        for slot in TIME_SLOTS:
            count = time_counts.get(slot, 0)
            pct = count / total_time * 100
            lines.append(
                f"{TIME_ICONS[slot]} {slot:<20} {count:<5} commits    "
                f"{progress_bar(pct)}   {pct:05.2f} %"
            )
        lines += ["```", ""]

    # Day-of-week distribution (GitHub contribution calendar, last year)
    total_days = sum(day_counts.values()) or 1
    if total_days > 0:
        peak_day = max(day_counts, key=day_counts.get)
        lines += [
            f"📅 **I'm Most Productive on {DAY_NAMES[peak_day]}**",
            "",
            "```text",
        ]
        for i, name in enumerate(DAY_NAMES):
            count = day_counts.get(i, 0)
            pct = count / total_days * 100
            lines.append(
                f"{name:<25} {count:<4} commits    "
                f"{progress_bar(pct)}   {pct:05.2f} %"
            )
        lines += ["```", ""]

    # Top languages all-time from WakaTime
    languages = waka.get("languages", [])[:6]
    if languages:
        lines += ["💬 **Top Languages (All Time)**", "", "```text"]
        for lang in languages:
            name = lang["name"]
            text = lang.get("text", "")
            pct = lang.get("percent", 0)
            lines.append(
                f"{name:<20} {text:<22} {progress_bar(pct)}   {pct:05.2f} %"
            )
        lines += ["```", ""]

    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S UTC")
    lines.append(f" Last Updated on {now}")
    return "\n".join(lines)


# ── README update ─────────────────────────────────────────────────────────────

def update_readme(content):
    with open(README_PATH) as f:
        readme = f.read()
    new_block = f"{START_MARKER}\n{content}\n{END_MARKER}"
    updated = re.sub(
        re.escape(START_MARKER) + ".*?" + re.escape(END_MARKER),
        new_block,
        readme,
        flags=re.DOTALL,
    )
    with open(README_PATH, "w") as f:
        f.write(updated)


if __name__ == "__main__":
    print("Fetching WakaTime all-time stats...")
    waka = get_waka_alltime()

    print("Fetching GitHub day-of-week distribution...")
    day_counts = get_day_distribution()

    print("Fetching GitHub time-of-day distribution...")
    time_counts = get_time_distribution()

    print("Building section and updating README...")
    section = build_section(waka, day_counts, time_counts)
    update_readme(section)
    print("Done!")
