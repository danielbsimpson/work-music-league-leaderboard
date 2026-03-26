"""
ui/tab_trends.py
-----------------
Renders the 📈 Trends & Consistency tab.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from music_league_stats import (
    LeagueData,
    most_consistent_submitter,
    most_volatile_submitter,
    most_improved,
    _points_per_submission,
    _name_map,
)
from ui.components import bar_chart, CHART_BASE, ACCENT


def render(data: LeagueData) -> None:
    comp  = data.competitors
    rds   = data.rounds
    subs  = data.submissions
    vts   = data.votes
    names = _name_map(comp)

    st.header("📈 Trends & Consistency")

    # ----------------------------------------- consistency / volatility
    col_con, col_vol = st.columns(2)

    with col_con:
        st.subheader("📏 Most Consistent (Lowest Variance)")
        con = most_consistent_submitter(subs, vts, comp)
        con_df = pd.DataFrame(con).rename(columns={"name": "Player", "variance": "Variance"})
        st.plotly_chart(
            bar_chart(con_df["Player"].tolist(), con_df["Variance"].tolist(),
                      "Points variance (lower = more consistent)", color=ACCENT,
                      x_label="Variance", y_label="Player"),
            width="stretch",
            key="trends_consistent",
        )

    with col_vol:
        st.subheader("🎢 Most Volatile (Highest Variance)")
        vol = most_volatile_submitter(subs, vts, comp)
        vol_df = pd.DataFrame(vol).rename(columns={"name": "Player", "variance": "Variance"})
        st.plotly_chart(
            bar_chart(vol_df["Player"].tolist(), vol_df["Variance"].tolist(),
                      "Points variance (higher = more volatile)", color="#e05252",
                      x_label="Variance", y_label="Player"),
            width="stretch",
            key="trends_volatile",
        )

    st.divider()

    # ---------------------------------------------------- most improved
    st.subheader("📈 Most Improved")
    improved = most_improved(subs, vts, comp, rds, league_rounds=data.league_rounds)
    imp_df = pd.DataFrame(improved).rename(columns={
        "name": "Player", "first_avg": "Early Avg",
        "last_avg": "Late Avg", "improvement": "Improvement",
    })

    fig_imp = go.Figure()
    fig_imp.add_trace(go.Bar(
        name="Early rounds avg", x=imp_df["Player"], y=imp_df["Early Avg"],
        marker_color="#888",
    ))
    fig_imp.add_trace(go.Bar(
        name="Late rounds avg", x=imp_df["Player"], y=imp_df["Late Avg"],
        marker_color=ACCENT,
    ))
    fig_imp.update_layout(
        **CHART_BASE,
        barmode="group",
        title="First 5 vs Last 5 rounds average per league",
        xaxis=dict(title=""),
        yaxis=dict(title=""),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig_imp, width="stretch", key="trends_improved")
    st.dataframe(
        imp_df.sort_values("Improvement", ascending=False),
        width="stretch", hide_index=True,
    )

    st.divider()

    # ---------------------------------------- points over time (line)
    st.subheader("📉 Points Over Time (per player)")
    pps = _points_per_submission(subs, vts)
    rounds_sorted = rds.sort_values("Created")[["ID", "Name"]].rename(
        columns={"ID": "Round ID", "Name": "RoundName"}
    )
    pps_time = (
        pps.merge(rounds_sorted, on="Round ID")
        .assign(Player=lambda df: df["Submitter ID"].map(names))
    )
    fig_line = px.line(
        pps_time,
        x="RoundName", y="TotalPoints", color="Player",
        markers=True,
        category_orders={"RoundName": rounds_sorted["RoundName"].tolist()},
        title="Points scored each round",
    )
    fig_line.update_layout(
        **CHART_BASE,
        xaxis=dict(tickangle=-40, title=""),
        yaxis=dict(title=""),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig_line, width="stretch", key="trends_over_time")
