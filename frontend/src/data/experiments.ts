export const experiments = [
  {
    name: "sermon_stats.py",
    title: "Sermon timing",
    about: "Calculate the average, median, and range of sample sermon lengths.",
    code: `# %% Sermon duration summary
from statistics import mean, median

minutes = [17.4, 22.0, 19.5, 24.1, 20.2]
summary = {
    "average": round(mean(minutes), 1),
    "median": median(minutes),
    "shortest": min(minutes),
    "longest": max(minutes),
}
for label, value in summary.items():
    print(f"{label.title():8} {value:5.1f} min")

# %% Compare a service slot with a sample sermon
sermon_minutes = 22
slot_minutes = 30
minutes_left = slot_minutes - sermon_minutes
print(f"Time remaining in the slot: {minutes_left} minutes")
`,
  },
  {
    name: "scripture_scan.py",
    title: "Scripture reference scan",
    about: "Explore how a regular expression finds references in a short transcript.",
    code: `# %% Find reference patterns
import re

transcript = "Today we read Luke 10:33 and Romans 12:13. Come back to Luke 10:33."
pattern = r"\\b(?:[1-3] )?(?:Luke|Romans|John|Peter) \\d{1,3}:\\d{1,3}\\b"
matches = re.findall(pattern, transcript)
unique_references = list(dict.fromkeys(matches))
print("References:", ", ".join(unique_references))
`,
  },
  {
    name: "transcript_terms.py",
    title: "Transcript term counts",
    about: "Compare recurring words in a fictional transcript after excluding filler words.",
    code: `# %% Count meaningful words
import re
from collections import Counter

transcript = """We make room by listening. Listening takes time.
Leave room in your week to listen, ask a question, and offer care."""
stop_words = {"a", "and", "by", "in", "to", "we", "your"}
words = re.findall(r"[a-z]+", transcript.casefold())
counts = Counter(word for word in words if word not in stop_words)
top_terms = counts.most_common(6)
for word, count in top_terms:
    print(f"{word:10} {'#' * count} ({count})")
`,
  },
  {
    name: "volunteer_coverage.py",
    title: "Volunteer coverage",
    about: "Read a sample CSV and identify teams that still need help.",
    code: `# %% Compare sign-ups with targets
import csv
from io import StringIO

sample_csv = """team,needed,confirmed
Welcome,3,4
Setup,6,4
Cleanup,4,2
"""
teams = list(csv.DictReader(StringIO(sample_csv)))
needs_help = {
    row["team"]: max(0, int(row["needed"]) - int(row["confirmed"]))
    for row in teams
}
for team, openings in needs_help.items():
    print(f"{team}: {openings} open")
`,
  },
  {
    name: "announcement_schedule.py",
    title: "Announcement schedule",
    about: "Calculate email, bulletin, and reminder dates from a fictional event date.",
    code: `# %% Plan publication dates
from datetime import date, timedelta

event = date(2027, 1, 16)
days_ahead = {"Email": 10, "Bulletin": 6, "Reminder": 2}
schedule = {channel: (event - timedelta(days=lead)).isoformat()
            for channel, lead in days_ahead.items()}
for channel, day in schedule.items():
    print(f"{channel:8} {day}")
`,
  },
  {
    name: "audio_levels.py",
    title: "Audio level experiment",
    about: "Compare peak and RMS levels of a generated tone without using a recording.",
    code: `# %% Measure a synthetic waveform
from math import pi, sin, sqrt, log10

rate = 16000
frequency = 440
amplitude = 0.25
samples = [amplitude * sin(2 * pi * frequency * n / rate) for n in range(rate // 10)]
peak = max(abs(sample) for sample in samples)
rms = sqrt(sum(sample ** 2 for sample in samples) / len(samples))
dbfs = round(20 * log10(rms), 1)
print(f"Peak: {peak:.3f} · RMS: {rms:.3f} · RMS dBFS: {dbfs}")
`,
  },
];
