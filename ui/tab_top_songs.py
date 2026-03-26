"""
ui/tab_top_songs.py
--------------------
Renders the ❤️ Top Songs tab.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from music_league_stats import LeagueData, most_universally_liked
from ui.components import bar_chart, ACCENT


def render(data: LeagueData) -> None:
    subs = data.submissions
    vts  = data.votes

    st.header("❤️ Most Universally Liked Songs")

    top_n = st.slider("Show top N songs", min_value=3, max_value=20, value=10, key="top_n_songs")
    liked = most_universally_liked(subs, vts, top_n=top_n)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("By Total Points")
        bp = pd.DataFrame(liked["by_points"])
        st.plotly_chart(
            bar_chart(
                (bp["title"] + " — " + bp["artist"]).tolist(),
                bp["total_points"].tolist(),
                "Most points received",
            ),
            width="stretch",
        )
        st.dataframe(
            bp.rename(columns={"title": "Title", "artist": "Artist",
                                "total_points": "Points", "voter_count": "Voters"}),
            width="stretch", hide_index=True,
        )

    with col2:
        st.subheader("By Number of Voters")
        bv = pd.DataFrame(liked["by_voters"])
        st.plotly_chart(
            bar_chart(
                (bv["title"] + " — " + bv["artist"]).tolist(),
                bv["voter_count"].tolist(),
                "Most distinct voters",
                color="#b47bff",
            ),
            width="stretch",
        )
        st.dataframe(
            bv.rename(columns={"title": "Title", "artist": "Artist",
                                "total_points": "Points", "voter_count": "Voters"}),
            width="stretch", hide_index=True,
        )
