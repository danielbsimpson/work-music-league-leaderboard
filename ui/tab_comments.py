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
    _name_map,
)
from ui.components import bar_chart, ACCENT


def render(data: LeagueData) -> None:
    comp = data.competitors
    subs = data.submissions
    vts  = data.votes

    names = _name_map(comp)

    st.header("💬 Comments")

    # Build a complete player roster so both charts always have the same rows
    all_players = pd.DataFrame({
        "Player": [names.get(pid, pid) for pid in comp["ID"].unique()]
    })

    # --- Most Talkative raw data ---
    talk_raw = most_talkative_commenter(vts, subs, comp)
    talk_df = (
        all_players
        .merge(
            pd.DataFrame(talk_raw).rename(columns={
                "name": "Player", "vote_comments": "Vote Comments",
                "sub_comments": "Sub Comments", "total": "Total",
            }),
            on="Player", how="left",
        )
        .fillna({"Vote Comments": 0, "Sub Comments": 0, "Total": 0})
        .astype({"Vote Comments": int, "Sub Comments": int, "Total": int})
        .sort_values("Total", ascending=False)
        .reset_index(drop=True)
    )

    # --- Most Comments Received raw data ---
    recv_raw = top_3_comment_winners(subs, vts, comp, top_n=len(comp))
    recv_df = (
        all_players
        .merge(
            pd.DataFrame(recv_raw).rename(columns={
                "rank": "Rank", "name": "Player", "comments_received": "Comments Received",
            }),
            on="Player", how="left",
        )
        .fillna({"Comments Received": 0})
        .astype({"Comments Received": int})
        .sort_values("Comments Received", ascending=False)
        .reset_index(drop=True)
    )
    recv_df["Rank"] = recv_df.index + 1

    col_talk, col_recv = st.columns(2)

    with col_talk:
        st.subheader("🗣️ Most Talkative")
        st.plotly_chart(
            bar_chart(talk_df["Player"].tolist(), talk_df["Total"].tolist(),
                      "Total comments made", color="#b47bff",
                      x_label="Comments Made", y_label="Player"),
            width="stretch",
            key="comments_talkative",
        )
        st.dataframe(talk_df[["Player", "Vote Comments", "Sub Comments", "Total"]],
                     width="stretch", hide_index=True)

    with col_recv:
        st.subheader("📬 Most Comments Received")
        st.plotly_chart(
            bar_chart(recv_df["Player"].tolist(), recv_df["Comments Received"].tolist(),
                      "Comments received on submitted songs", color=ACCENT,
                      x_label="Comments Received", y_label="Player"),
            width="stretch",
            key="comments_received",
        )
        st.dataframe(recv_df[["Rank", "Player", "Comments Received"]],
                     width="stretch", hide_index=True)

    st.divider()

    # ------------------------------------------------- most commented songs
    st.subheader("🎵 Songs with Most Comments Received")

    uri_to_title  = dict(zip(subs["SpotifyURI"], subs["Title"] + " – " + subs["Artist(s)"]))
    uri_to_sub    = dict(zip(subs["SpotifyURI"], subs["Submitter ID"]))

    commented_votes = vts[vts["Comment"].notna() & (vts["Comment"].str.strip() != "")].copy()
    commented_votes["Song"]      = commented_votes["SpotifyURI"].map(uri_to_title)
    commented_votes["Submitter"] = commented_votes["SpotifyURI"].map(uri_to_sub).map(names)

    top_songs = (
        commented_votes.groupby(["SpotifyURI", "Song", "Submitter"])
        .size()
        .reset_index(name="Comment Count")
        .sort_values("Comment Count", ascending=False)
        .head(5)
    )

    st.plotly_chart(
        bar_chart(
            top_songs["Song"].tolist(),
            top_songs["Comment Count"].tolist(),
            "Top 5 most commented-on songs",
            color="#ffd166",
            x_label="Comments Received", y_label="Song",
        ),
        width="stretch",
        key="comments_top_songs",
    )

    for _, song_row in top_songs.iterrows():
        song_comments = (
            commented_votes[commented_votes["SpotifyURI"] == song_row["SpotifyURI"]]
            [["Song", "Submitter", "Comment"]]
            .rename(columns={"Comment": "Comment Text"})
            .reset_index(drop=True)
        )
        with st.expander(
            f"💬 {song_row['Song']}  ·  submitted by {song_row['Submitter']}  "
            f"·  {song_row['Comment Count']} comment(s)"
        ):
            st.dataframe(song_comments[["Comment Text"]], hide_index=True, width="stretch")

    st.divider()

    st.subheader("😂 All Comments")
    search = st.text_input("🔍 Search comments", placeholder="Type to filter…")
    all_comments = funniest_comment(vts, subs, comp)
    comments_df = pd.DataFrame(all_comments).rename(columns={
        "author": "Author", "source": "Source",
        "context": "Song", "comment": "Comment",
    })
    if search:
        mask = comments_df.apply(
            lambda col: col.astype(str).str.contains(search, case=False)
        ).any(axis=1)
        comments_df = comments_df[mask]

    st.dataframe(comments_df, width="stretch", hide_index=True)
