"""
ui/tab_economy.py
------------------
Renders the 💰 Point Economy tab.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from music_league_stats import LeagueData, point_economy_summary, _points_per_submission
from ui.components import CHART_BASE, ACCENT


def render(data: LeagueData) -> None:
    rds  = data.rounds
    subs = data.submissions
    vts  = data.votes

    st.header("💰 Point Economy")

    pe = point_economy_summary(subs, vts, rds)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Points Distributed",  pe["total_points_distributed"])
    m2.metric("Rounds Played",             pe["num_rounds"])
    m3.metric("Avg Points / Round",        pe["avg_points_per_round"])
    m4.metric("Avg Points / Submission",   pe["avg_points_per_submission"])
    m5.metric("Min → Max Per Round",
              f"{pe['min_points_in_round']} → {pe['max_points_in_round']}")

    st.divider()

    # ---------------------------------------- points per round bar
    pps = _points_per_submission(subs, vts)
    per_round = (
        pps.groupby("Round ID")["TotalPoints"]
        .sum()
        .reset_index()
        .merge(
            rds[["ID", "Name", "Created"]].rename(
                columns={"ID": "Round ID", "Name": "RoundName"}
            ),
            on="Round ID",
        )
        .sort_values("Created")
    )
    fig_eco = px.bar(
        per_round, x="RoundName", y="TotalPoints",
        title="Total points distributed per round",
        color_discrete_sequence=[ACCENT],
    )
    fig_eco.update_layout(
        **CHART_BASE,
        xaxis=dict(tickangle=-40, title=""),
        yaxis=dict(title=""),
        showlegend=False,
    )
    st.plotly_chart(fig_eco, width="stretch", key="economy_per_round")

    st.divider()

    # ----------------------------------------- vote distribution bar
    st.subheader("🎲 Vote Distribution")
    vote_dist = vts[vts["Points"] > 0]["Points"].value_counts().sort_index()
    fig_dist = px.bar(
        x=vote_dist.index.astype(str),
        y=vote_dist.values,
        title="How often each point value was used",
        color_discrete_sequence=["#ffd166"],
    )
    fig_dist.update_layout(
        **CHART_BASE,
        xaxis=dict(title=""),
        yaxis=dict(title=""),
        showlegend=False,
    )
    st.plotly_chart(fig_dist, width="stretch", key="economy_vote_dist")
