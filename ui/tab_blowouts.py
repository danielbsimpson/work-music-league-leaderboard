"""
ui/tab_blowouts.py
-------------------
Renders the 🎵 Song Stats tab — most liked songs, blowouts, repeated songs, artist appearances.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from music_league_stats import (
    LeagueData,
    most_universally_liked,
    biggest_blowout,
    most_submitted_songs,
    most_artist_appearances,
)
from ui.components import bar_chart, ACCENT


def render(data: LeagueData) -> None:
    comp = data.competitors
    rds  = data.rounds
    subs = data.submissions
    vts  = data.votes

    st.header("🎵 Song Stats")

    # --------------------------------------------------- most universally liked
    st.subheader("❤️ Most Universally Liked Songs")
    top_n = st.slider("Show top N songs", min_value=3, max_value=20, value=10, key="top_n_songs")
    liked = most_universally_liked(subs, vts, comp, top_n=top_n)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**By Total Points**")
        bp = pd.DataFrame(liked["by_points"])
        st.plotly_chart(
            bar_chart(
                (bp["title"] + " — " + bp["artist"]).tolist(),
                bp["total_points"].tolist(),
                "Most points received",
                x_label="Points", y_label="Song",
            ),
            width="stretch",
            key="songs_liked_by_pts",
        )
        st.dataframe(
            bp.rename(columns={
                "title":        "Title",
                "artist":       "Artist",
                "submitted_by": "Submitted By",
                "total_points": "Points",
                "voter_count":  "Voters",
            })[["Title", "Artist", "Submitted By", "Points", "Voters"]],
            width="stretch", hide_index=True,
        )

    with col2:
        st.markdown("**By Number of Voters**")
        bv = pd.DataFrame(liked["by_voters"])
        st.plotly_chart(
            bar_chart(
                (bv["title"] + " — " + bv["artist"]).tolist(),
                bv["voter_count"].tolist(),
                "Most distinct voters",
                color="#b47bff",
                x_label="Voters", y_label="Song",
            ),
            width="stretch",
            key="songs_liked_by_voters",
        )
        st.dataframe(
            bv.rename(columns={
                "title":        "Title",
                "artist":       "Artist",
                "submitted_by": "Submitted By",
                "total_points": "Points",
                "voter_count":  "Voters",
            })[["Title", "Artist", "Submitted By", "Points", "Voters"]],
            width="stretch", hide_index=True,
        )

    st.divider()

    # --------------------------------------------------- biggest blowouts
    st.subheader("💥 Biggest Blowouts")
    st.caption("Rounds where the winner had the largest margin over 2nd place.")

    blowouts = biggest_blowout(subs, vts, rds, comp)
    blow_df = pd.DataFrame(blowouts).rename(columns={
        "round":         "Round",
        "winner":        "Winner",
        "winner_song":   "Winning Song",
        "winner_points": "Winner Pts",
        "second_place":  "2nd Place",
        "second_points": "2nd Pts",
        "margin":        "Margin",
    })

    st.plotly_chart(
        bar_chart(
            blow_df["Round"].tolist(),
            blow_df["Margin"].tolist(),
            "Winning margin per round (1st − 2nd place points)",
            color="#ffd166",
            x_label="Margin (pts)", y_label="Round",
        ),
        width="stretch",
        key="songs_blowouts",
    )
    st.dataframe(blow_df, width="stretch", hide_index=True)

    st.divider()

    # --------------------------------------------------- most submitted songs
    st.subheader("🔁 Most Submitted Songs")
    st.caption("Songs that appeared in submissions more than once across all rounds.")

    repeated = most_submitted_songs(subs)
    if repeated:
        rep_df = pd.DataFrame(repeated).rename(columns={
            "rank":   "Rank",
            "title":  "Title",
            "artist": "Artist(s)",
            "count":  "Times Submitted",
        })
        st.plotly_chart(
            bar_chart(
                (rep_df["Title"] + " — " + rep_df["Artist(s)"]).tolist(),
                rep_df["Times Submitted"].tolist(),
                "Most Submitted Songs",
                color="#c77dff",
                x_label="Times Submitted", y_label="Song",
            ),
            width="stretch",
            key="songs_repeated",
        )
        st.dataframe(rep_df, hide_index=True, width="stretch")
    else:
        st.info("No song was submitted more than once. 🎉")

    st.divider()

    # --------------------------------------------------- most artist appearances
    st.subheader("🎤 Most Artist Appearances")
    st.caption("Artists whose songs appear most frequently across all submissions.")

    artists = most_artist_appearances(subs)
    if artists:
        art_df = pd.DataFrame(artists).rename(columns={
            "rank":   "Rank",
            "artist": "Artist",
            "count":  "Appearances",
        })
        st.plotly_chart(
            bar_chart(
                art_df["Artist"].tolist(),
                art_df["Appearances"].tolist(),
                "Most Frequent Artists",
                color="#f4a261",
                x_label="Appearances", y_label="Artist",
            ),
            width="stretch",
            key="songs_artists",
        )
        st.dataframe(art_df, hide_index=True, width="stretch")
    else:
        st.info("No artist data available.")