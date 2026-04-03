"""
ui/tab_fan_map.py
------------------
Renders the 🤝 Fan Map tab.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

    # ------------------------------------------------- full points-given section
    st.subheader("🗺️ Full Points-Given")
    st.caption("Rows = voter  ·  Columns = submitter who received the points")

    uri_to_sub = dict(zip(subs["SpotifyURI"], subs["Submitter ID"]))
    vts_copy = vts.copy()
    vts_copy["ReceiverID"] = vts_copy["SpotifyURI"].map(uri_to_sub)
    vts_copy = vts_copy[
        vts_copy["ReceiverID"].notna()
        & (vts_copy["Voter ID"] != vts_copy["ReceiverID"])
    ]
    edges = (
        vts_copy.groupby(["Voter ID", "ReceiverID"])["Points"]
        .sum()
        .reset_index()
        .assign(
            VoterName    = lambda df: df["Voter ID"].map(names),
            ReceiverName = lambda df: df["ReceiverID"].map(names),
        )
    )

    # --- ordering: sort players by total points received (descending) --------
    total_received = (
        edges.groupby("ReceiverName")["Points"].sum().sort_values(ascending=False)
    )
    total_sent = (
        edges.groupby("VoterName")["Points"].sum().sort_values(ascending=False)
    )
    # Left nodes = voters ordered by total sent; right nodes = receivers by total received
    voter_order    = total_sent.index.tolist()
    receiver_order = total_received.index.tolist()

    # Build Sankey node list: voters on left (0..n-1), receivers on right (n..2n-1)
    left_nodes  = voter_order
    right_nodes = receiver_order
    all_nodes   = left_nodes + right_nodes
    node_idx    = {name: i for i, name in enumerate(all_nodes)}

    sankey_sources = [node_idx[r["VoterName"]]    for _, r in edges.iterrows()]
    sankey_targets = [node_idx[r["ReceiverName"]] + 0 for _, r in edges.iterrows()]
    # targets need offset by len(left_nodes) only if receiver names differ from voter names
    # (they share the same pool, so we split the namespace explicitly)
    left_nodes_offset  = {name: i                        for i, name in enumerate(left_nodes)}
    right_nodes_offset = {name: i + len(left_nodes)      for i, name in enumerate(right_nodes)}
    sankey_sources = [left_nodes_offset[r["VoterName"]]      for _, r in edges.iterrows()]
    sankey_targets = [right_nodes_offset[r["ReceiverName"]]  for _, r in edges.iterrows()]
    sankey_values  = edges["Points"].tolist()

    n_left  = len(left_nodes)
    n_right = len(right_nodes)
    # x positions: left nodes at 0.01, right nodes at 0.99
    node_x = [0.01] * n_left + [0.99] * n_right
    # y positions: evenly spaced top→bottom within each side
    node_y = (
        [round((i + 1) / (n_left  + 1), 3) for i in range(n_left)]
        + [round((i + 1) / (n_right + 1), 3) for i in range(n_right)]
    )

    # Assign each right-side (receiver) node a unique colour from a palette
    _PLAYER_PALETTE = [
        "#1DB954", "#ffd166", "#ef476f", "#118ab2", "#06d6a0",
        "#f4a261", "#e76f51", "#a8dadc", "#c77dff", "#ff6b6b",
        "#4ecdc4", "#ffe66d", "#ff9f1c", "#2ec4b6", "#e71d36",
    ]
    receiver_colors = {
        name: _PLAYER_PALETTE[i % len(_PLAYER_PALETTE)]
        for i, name in enumerate(right_nodes)
    }
    # Left nodes are neutral grey; right nodes get their unique colour
    node_colors = ["#888888"] * n_left + [receiver_colors[n] for n in right_nodes]

    # Links coloured to match the target receiver, with transparency
    def _with_alpha(hex_color: str, alpha: float = 0.4) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    link_colors = [
        _with_alpha(receiver_colors[edges.iloc[i]["ReceiverName"]])
        for i in range(len(edges))
    ]

    fig_sankey = go.Figure(go.Sankey(
        arrangement="fixed",
        node=dict(
            label      = all_nodes,
            x          = node_x,
            y          = node_y,
            color      = node_colors,
            pad        = 12,
            thickness  = 18,
            line       = dict(color="rgba(0,0,0,0)", width=0),
        ),
        link=dict(
            source     = sankey_sources,
            target     = sankey_targets,
            value      = sankey_values,
            color      = link_colors,
        ),
    ))
    fig_sankey.update_layout(
        **{**CHART_BASE, "margin": dict(l=10, r=10, t=50, b=10)},
        title="Points flow: voter (left) → recipient (right), ordered by cumulative points",
        height=520,
    )

    # --- heatmap (kept alongside) -------------------------------------------
    matrix = edges.pivot_table(
        index="VoterName", columns="ReceiverName", values="Points", fill_value=0
    )
    n_players = len(matrix)
    cell_size  = 42          # px per player cell
    label_margin_bottom = max(120, max(len(n) for n in matrix.columns.tolist()) * 7)
    label_margin_left   = max(100, max(len(n) for n in matrix.index.tolist())   * 7)
    heatmap_height = max(400, n_players * cell_size + label_margin_bottom)

    fig_matrix = px.imshow(
        matrix, color_continuous_scale="Greens", aspect="auto",
        title="Total points given (row) → received (column)",
    )
    fig_matrix.update_xaxes(
        tickmode="array",
        tickvals=list(range(len(matrix.columns))),
        ticktext=matrix.columns.tolist(),
        tickangle=-45,
        automargin=True,
    )
    fig_matrix.update_yaxes(
        tickmode="array",
        tickvals=list(range(len(matrix.index))),
        ticktext=matrix.index.tolist(),
        automargin=True,
    )
    fig_matrix.update_layout(
        **{
            **CHART_BASE,
            "height": heatmap_height,
            "margin": dict(
                l=label_margin_left,
                r=20,
                t=60,
                b=label_margin_bottom,
            ),
        }
    )

    tab_sankey, tab_heatmap = st.tabs(["Sankey Flow", "Heatmap"])
    with tab_sankey:
        st.plotly_chart(fig_sankey, width="stretch", key="fan_sankey")
    with tab_heatmap:
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
