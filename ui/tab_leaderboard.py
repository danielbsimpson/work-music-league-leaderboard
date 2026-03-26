"""
ui/tab_leaderboard.py
----------------------
Renders the 🏆 Leaderboard tab.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from music_league_stats import (
    LeagueData,
    top_3_winners,
    top_podium_appearances,
    most_misunderstood,
    zero_points_incidents,
    player_round_averages,
    _points_per_submission,
    _name_map,
)
from ui.components import bar_chart, stat_tile, tile_group, CHART_BASE


# Soft colour palettes
_WINNER_STYLES = [
    ("#b8952a", "🥇"), ("#8a9ba8", "🥈"), ("#9e6b4a", "🥉"),
    ("#4a9068", "4️⃣"), ("#5aa376", "5️⃣"),
]
_PODIUM_COLORS = ["#2e6b4a", "#3a7d5a", "#4a9068", "#5aa376", "#6ab684"]
_MISUND_COLORS = ["#8b3a3a", "#9e4a4a", "#b25e5e", "#c47070", "#d48484"]
_AVG_COLORS    = ["#1a5276", "#1f618d", "#2471a3", "#2e86c1", "#3498db"]


def render(data: LeagueData) -> None:
    comp  = data.competitors
    rds   = data.rounds
    subs  = data.submissions
    vts   = data.votes
    names = _name_map(comp)

    st.header("🏆 Leaderboard")

    # ------------------------------------------------------------------ tiles
    winners        = top_3_winners(subs, vts, comp, top_n=5)
    podium_entries = top_podium_appearances(subs, vts, comp, rds)[:5]
    misunderstood  = most_misunderstood(subs, vts, comp, top_n=5, league_rounds=data.league_rounds)
    avg_entries    = player_round_averages(subs, vts, comp)[:5]

    winner_tiles = [
        stat_tile(icon, w["name"], f"{w['points']} pts", bg)
        for w, (bg, icon) in zip(winners, _WINNER_STYLES)
    ]
    podium_tiles = [
        stat_tile("🎯", e["name"], f"{e['podium_appearances']}x top-3", bg)
        for e, bg in zip(podium_entries, _PODIUM_COLORS)
    ]
    misund_tiles = [
        stat_tile("💔", e["name"], f"{e['points']} pts", bg)
        for e, bg in zip(misunderstood, _MISUND_COLORS)
    ]
    avg_tiles = [
        stat_tile("📈", e["name"], f"{e['avg_points']} avg pts", bg)
        for e, bg in zip(avg_entries, _AVG_COLORS)
    ]

    col_win, col_pod, col_avg, col_mis  = st.columns([5, 5, 5, 5])
    with col_win:
        st.markdown(tile_group("🏆 Top 5 Winners", winner_tiles), unsafe_allow_html=True)
    with col_pod:
        st.markdown(tile_group("🥇 Top Podium Appearances", podium_tiles), unsafe_allow_html=True)
    with col_avg:
        st.markdown(tile_group("📈 Top 5 by Round Average", avg_tiles), unsafe_allow_html=True)
    with col_mis:
        st.markdown(tile_group("😥 Most Misunderstood", misund_tiles), unsafe_allow_html=True)

    st.divider()

    # --------------------------------------------------------- total pts bar
    pps = _points_per_submission(subs, vts)
    totals = (
        pps.groupby("Submitter ID")["TotalPoints"]
        .sum()
        .reset_index()
        .assign(Name=lambda df: df["Submitter ID"].map(names))
        .sort_values("TotalPoints", ascending=False)
    )
    st.plotly_chart(
        bar_chart(totals["Name"].tolist(), totals["TotalPoints"].tolist(),
                  "Total Points — All Competitors",
                  x_label="Points", y_label="Player"),
        width="stretch",
        key="lb_total_pts",
    )

    st.divider()

    # ------------------------------------------------------ per-round heatmap
    st.subheader("📊 Points Per Round Heatmap")
    pivot = (
        pps.assign(Name=lambda df: df["Submitter ID"].map(names))
        .merge(
            rds[["ID", "Name"]].rename(columns={"ID": "Round ID", "Name": "RoundName"}),
            on="Round ID",
        )
        .pivot_table(index="Name", columns="RoundName", values="TotalPoints", fill_value=0)
    )
    fig_heat = px.imshow(
        pivot, color_continuous_scale="Greens", aspect="auto",
        title="Points earned per player per round",
    )
    fig_heat.update_layout(**CHART_BASE)
    st.plotly_chart(fig_heat, width="stretch", key="lb_heatmap")

    st.divider()

    # --------------------------------------------------- zero-point incidents
    st.subheader("0️⃣ Zero Points Incidents")
    zpi = zero_points_incidents(subs, vts, comp)
    st.metric("Total zero-point rounds across all players", zpi["total_zero_incidents"])
    if zpi["by_person"]:
        zdf = pd.DataFrame(zpi["by_person"])
        st.plotly_chart(
            bar_chart(zdf["name"].tolist(), zdf["zero_rounds"].tolist(),
                      "Zero-point rounds per player", color="#e05252",
                      x_label="Zero-Point Rounds", y_label="Player"),
            width="stretch",
            key="lb_zero_pts",
        )
    else:
        st.success("Nobody scored zero in any round! 🎉")

    st.divider()

    # --------------------------------------------------- round averages
    st.subheader("📈 Average Points Per Round")
    avgs = player_round_averages(subs, vts, comp)
    avg_df = pd.DataFrame(avgs)
    st.plotly_chart(
        bar_chart(
            avg_df["name"].tolist(),
            avg_df["avg_points"].tolist(),
            "Average Points Per Round — All Competitors",
            color="#7ec8e3",
            x_label="Avg Points / Round", y_label="Player",
        ),
        width="stretch",
        key="lb_round_avg",
    )
    st.dataframe(
        avg_df.rename(columns={"rank": "Rank", "name": "Player", "avg_points": "Avg Pts / Round"}),
        hide_index=True,
        width="stretch",
    )
