"""
ui/tab_fan_map.py
------------------
Renders the 🤝 Fan Map tab.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from music_league_stats import (
    LeagueData,
    biggest_fans,
    least_compatible,
    most_generous_voter,
    _name_map,
    _format_name,
)
from ui.components import bar_chart, CHART_BASE, ACCENT


def render(data: LeagueData) -> None:
    comp = data.competitors
    subs = data.submissions
    vts  = data.votes
    names = _name_map(comp)

    st.header("🤝 Fan Map")

    # ------------------------------------------------- target player selector
    all_player_names = sorted(_format_name(n) for n in comp["Name"].tolist())
    default_target   = next((n for n in all_player_names if n.startswith("Daniel")), all_player_names[0])
    target_name = st.selectbox(
        "🎯 Target player",
        all_player_names,
        index=all_player_names.index(default_target),
        key="fan_map_target",
    )
    st.caption("Select a player above to see who are their biggest fans and least compatible matches.")

    col_fans, col_compat = st.columns(2)

    with col_fans:
        st.subheader(f"💚 Biggest Fans of {target_name}")
        fans = biggest_fans(subs, vts, comp, target_name)[:5]
        fans_df = pd.DataFrame(fans).rename(
            columns={"voter": "Voter", "points_given": "Points Given"}
        )
        st.plotly_chart(
            bar_chart(fans_df["Voter"].tolist(), fans_df["Points Given"].tolist(),
                      f"Top 5 — points given to {target_name}",
                      x_label="Points Given", y_label="Voter"),
            width="stretch",
            key="fan_biggest_fans",
        )
        st.dataframe(fans_df, width="stretch", hide_index=True)

    with col_compat:
        st.subheader(f"💔 Least Compatible with {target_name}")
        compat = least_compatible(subs, vts, comp, target_name)[:5]
        compat_df = pd.DataFrame(compat).rename(
            columns={"voter": "Voter", "points_given": "Points Given"}
        )
        st.plotly_chart(
            bar_chart(compat_df["Voter"].tolist(), compat_df["Points Given"].tolist(),
                      f"Bottom 5 — points given to {target_name}", color="#e05252",
                      x_label="Points Given", y_label="Voter"),
            width="stretch",
            key="fan_least_compat",
        )
        st.dataframe(compat_df, width="stretch", hide_index=True)

    st.divider()

    # ------------------------------------------------- full points matrix
    st.subheader("🗺️ Full Points-Given Matrix")
    st.caption("Rows = voter  ·  Columns = submitter who received the points")

    uri_to_sub = dict(zip(subs["SpotifyURI"], subs["Submitter ID"]))
    vts_copy = vts.copy()
    vts_copy["ReceiverID"] = vts_copy["SpotifyURI"].map(uri_to_sub)
    vts_copy = vts_copy[
        vts_copy["ReceiverID"].notna()
        & (vts_copy["Voter ID"] != vts_copy["ReceiverID"])
    ]
    matrix = (
        vts_copy.groupby(["Voter ID", "ReceiverID"])["Points"]
        .sum()
        .reset_index()
        .assign(
            VoterName    = lambda df: df["Voter ID"].map(names),
            ReceiverName = lambda df: df["ReceiverID"].map(names),
        )
        .pivot_table(index="VoterName", columns="ReceiverName", values="Points", fill_value=0)
    )
    fig_matrix = px.imshow(
        matrix, color_continuous_scale="Greens", aspect="auto",
        title="Total points given (row) → received (column)",
    )
    fig_matrix.update_layout(**CHART_BASE)
    st.plotly_chart(fig_matrix, width="stretch", key="fan_matrix")

    st.divider()

    # ------------------------------------------------- most generous voter
    st.subheader("🎁 Most Generous Voter")
    gen = most_generous_voter(vts, subs, comp)
    gen_df = pd.DataFrame(gen).rename(columns={
        "voter": "Voter",
        "avg_distinct_recipients_per_round": "Avg Distinct Recipients / Round",
    })
    st.plotly_chart(
        bar_chart(gen_df["Voter"].tolist(),
                  gen_df["Avg Distinct Recipients / Round"].tolist(),
                  "Average distinct recipients per round", color="#ffd166",
                  x_label="Avg Recipients / Round", y_label="Voter"),
        width="stretch",
        key="fan_generous",
    )
