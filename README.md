# 🎵 Daniel's Work Music Leagues

A Streamlit web app for tracking and exploring stats across **work Music League** seasons, split by region.

This project is a fork of [danielbsimpson/music-league-leaderboard](https://github.com/danielbsimpson/music-league-leaderboard) — refer to that repo for full documentation on the underlying stats engine, CSV format reference, tab descriptions, setup instructions, and deployment guidance.

---

## What's Different From the Original

### 1. Regional data structure

The original repo expects all league folders to sit directly inside `data/`:

```
data/
├── season_1/
└── season_2/
```

This fork adds a **region layer** between `data/` and the individual league folders:

```
data/
├── UK_Leagues/
│   ├── uk_league1/
│   └── uk_league2/
└── US_Leagues/
    └── us_league_current/
```

Each leaf folder still contains the same four CSV exports (`competitors.csv`, `rounds.csv`, `submissions.csv`, `votes.csv`). New regions are auto-discovered — just add a new subfolder under `data/` containing at least one valid league folder.

### 2. Region-aware sidebar

The sidebar now has a two-step selection flow:

| Step | Control | Behaviour |
|------|---------|-----------|
| 1 | **Region** radio | Switches between regional groups (e.g. UK Leagues / US Leagues). Populated automatically from the folders inside `data/`. |
| 2 | **League Selection** radio | Within the chosen region, pick **Single League** (selectbox of available leagues) or **All Leagues (cumulative)** (merges every league in that region into one combined view). |

The original repo's cumulative mode required manually selecting leagues from a multiselect. Here, "All Leagues" always means *all leagues in the current region*, keeping the UI simpler.

### 3. App naming

The app is titled **"Daniel's Work Music Leagues"** rather than the generic "T5 Music League Stats" used in the original. This is reflected in:
- The browser tab title (`page_title`)
- The sidebar header
- The main page heading

### 4. Page caption

The caption beneath the main heading now includes the **selected region name** alongside the usual round/competitor/submission counts, e.g.:

> `UK_Leagues — 2 league(s) · 24 rounds · 10 competitors · 240 submissions · 4,800 points given`