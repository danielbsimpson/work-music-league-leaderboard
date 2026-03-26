"""
Music League Stats — Streamlit App
====================================
Thin orchestrator: sidebar, data loading, tab dispatch, and report download.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import os
import streamlit as st

from music_league_stats import (
    LeagueData,
    load_data_from_dirs,
)
from ui.components import inject_css
from ui import (
    tab_leaderboard,
    tab_fan_map,
    tab_trends,
    tab_blowouts,
    tab_comments,
    tab_economy,
)

# ---------------------------------------------------------------------------
# Page config & global CSS
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="🎵 Daniel's Work Music Leagues",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

# ---------------------------------------------------------------------------
# League discovery (region-aware)
# ---------------------------------------------------------------------------
REQUIRED_FILES = {"competitors.csv", "rounds.csv", "submissions.csv", "votes.csv"}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")


def _discover_leagues(root: str) -> list[str]:
    """Return sorted list of league folder paths under *root* that have all CSVs."""
    results: list[str] = []
    if os.path.isdir(root):
        for entry in sorted(os.scandir(root), key=lambda e: e.name):
            if entry.is_dir():
                present = {f.name for f in os.scandir(entry.path) if f.is_file()}
                if REQUIRED_FILES.issubset(present):
                    results.append(entry.path)
    return results


def _discover_regions(data_dir: str) -> dict[str, list[str]]:
    """
    Return a mapping of {region_name: [league_path, ...]} by scanning
    sub-folders of *data_dir*.  A sub-folder is treated as a *region* if it
    contains at least one league folder (i.e. no CSVs directly inside it).
    Folders that contain CSVs directly are treated as legacy flat leagues and
    grouped under a synthetic "Default" region.
    """
    regions: dict[str, list[str]] = {}
    if not os.path.isdir(data_dir):
        return regions
    for entry in sorted(os.scandir(data_dir), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        direct_files = {f.name for f in os.scandir(entry.path) if f.is_file()}
        if REQUIRED_FILES.issubset(direct_files):
            # Legacy flat layout – bucket under "Default"
            regions.setdefault("Default", []).append(entry.path)
        else:
            leagues = _discover_leagues(entry.path)
            if leagues:
                regions[entry.name] = leagues
    return regions


region_map = _discover_regions(DATA_DIR)   # e.g. {"UK_Leagues": [...], "US_Leagues": [...]}

if not region_map:
    st.error(
        "No league data found inside the `data/` directory. "
        "Organise your data as `data/<Region>/<league>/` with each league "
        "folder containing competitors.csv, rounds.csv, submissions.csv, "
        "and votes.csv."
    )
    st.stop()

region_names = list(region_map.keys())

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("🎵 Daniel's Work Music Leagues")
st.sidebar.markdown("---")

# -- Region picker --
st.sidebar.subheader("Region")
selected_region = st.sidebar.radio("Select region", region_names, index=0)

region_leagues      = region_map[selected_region]          # full paths
region_league_names = [os.path.basename(d) for d in region_leagues]

st.sidebar.markdown("---")

# -- League mode within the chosen region --
st.sidebar.subheader("League Selection")
mode = st.sidebar.radio(
    "View",
    ["Single League", "All Leagues (cumulative)"],
    index=1,
)

if mode == "Single League":
    chosen_name = st.sidebar.selectbox("Select league", region_league_names)
    chosen_dirs = [region_leagues[region_league_names.index(chosen_name)]]
else:
    chosen_dirs = region_leagues
    if not chosen_dirs:
        st.warning("No leagues found for the selected region.")
        st.stop()

st.sidebar.markdown("---")

# ---------------------------------------------------------------------------
# Data loading (cached — switching tabs is instant)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading league data...")
def get_data(dirs: tuple[str, ...]) -> LeagueData:
    return load_data_from_dirs(list(dirs))


data  = get_data(tuple(chosen_dirs))
comp  = data.competitors
subs  = data.submissions
vts   = data.votes

scope_label = (
    " + ".join(os.path.basename(d) for d in chosen_dirs)
    if len(chosen_dirs) > 1
    else os.path.basename(chosen_dirs[0])
)

st.sidebar.markdown("---")
st.sidebar.info("Tip: switch tabs above to explore each stat category.")

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
st.title("🎵 Daniel's Work Music Leagues")
st.caption(
    f"**{selected_region}** — {len(chosen_dirs)} league(s)  ·  "
    f"{len(data.rounds)} rounds  ·  "
    f"{data.competitors['ID'].nunique()} competitors  ·  "
    f"{len(data.submissions)} submissions  ·  "
    f"{int(data.votes['Points'].sum()):,} points given"
)

# ---------------------------------------------------------------------------
# Tabs -- each delegates entirely to its own module
# ---------------------------------------------------------------------------
tabs = st.tabs([
    "Leaderboard",
    "Song Stats",
    "Fan Map",
    "Trends",
    "Comments",
    "Economy",
])

with tabs[0]:
    tab_leaderboard.render(data)

with tabs[1]:
    tab_blowouts.render(data)

with tabs[2]:
    tab_fan_map.render(data)

with tabs[3]:
    tab_trends.render(data)

with tabs[4]:
    tab_comments.render(data)

with tabs[5]:
    tab_economy.render(data)
