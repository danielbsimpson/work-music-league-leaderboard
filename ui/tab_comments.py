"""
ui/tab_comments.py
-------------------
Renders the 💬 Comments tab.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from music_league_stats import (
    LeagueData,
    most_talkative_commenter,
    funniest_comment,
    top_3_comment_winners,
)
from ui.components import bar_chart, ACCENT


def render(data: LeagueData) -> None:
    comp = data.competitors
    subs = data.submissions
    vts  = data.votes

    st.header("💬 Comments")

    col_talk, col_recv = st.columns(2)

    with col_talk:
        st.subheader("🗣️ Most Talkative")
        talk = most_talkative_commenter(vts, subs, comp)
        talk_df = pd.DataFrame(talk).rename(columns={
            "name": "Player", "vote_comments": "Vote Comments",
            "sub_comments": "Sub Comments", "total": "Total",
        })
        st.plotly_chart(
            bar_chart(talk_df["Player"].tolist(), talk_df["Total"].tolist(),
                      "Total comments made", color="#b47bff",
                      x_label="Comments Made", y_label="Player"),
            width="stretch",
            key="comments_talkative",
        )
        st.dataframe(talk_df, width="stretch", hide_index=True)

    with col_recv:
        st.subheader("📬 Most Comments Received")
        recv = top_3_comment_winners(subs, vts, comp, top_n=len(comp))
        recv_df = pd.DataFrame(recv).rename(columns={
            "rank": "Rank", "name": "Player", "comments_received": "Comments Received",
        })
        st.plotly_chart(
            bar_chart(recv_df["Player"].tolist(), recv_df["Comments Received"].tolist(),
                      "Comments received on submitted songs", color=ACCENT,
                      x_label="Comments Received", y_label="Player"),
            width="stretch",
            key="comments_received",
        )
        st.dataframe(recv_df, width="stretch", hide_index=True)

    st.divider()

    st.subheader("😂 All Comments")
    search = st.text_input("🔍 Search comments", placeholder="Type to filter…")
    all_comments = funniest_comment(vts, subs, comp)
    comments_df = pd.DataFrame(all_comments).rename(columns={
        "author": "Author", "source": "Source",
        "context": "Song / Context", "comment": "Comment",
    })
    if search:
        mask = comments_df.apply(
            lambda col: col.astype(str).str.contains(search, case=False)
        ).any(axis=1)
        comments_df = comments_df[mask]

    st.dataframe(comments_df, width="stretch", hide_index=True)
