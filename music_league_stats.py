"""
Music League Statistics Calculator
===================================
Calculates a wide range of stats from Music League CSV exports.

Supports a single league folder OR multiple league folders merged together
for cumulative cross-league statistics.

CSV files expected in each folder:
    competitors.csv  – ID, Name
    rounds.csv       – ID, Created, Name, Description, Playlist URL
    submissions.csv  – Spotify URI, Title, Album, Artist(s), Submitter ID,
                       Created, Comment, Round ID, Visible To Voters
    votes.csv        – Spotify URI, Voter ID, Created, Points Assigned,
                       Comment, Round ID

Usage (CLI):
    # Single league
    python music_league_stats.py path/to/league1

    # Cumulative (two or more leagues)
    python music_league_stats.py path/to/league1 path/to/league2

    # Cumulative with a specific target player for Fan/Compat sections
    python music_league_stats.py path/to/league1 path/to/league2 --target "Alice"
"""

from __future__ import annotations

import io
import os
import re
import sys
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# New Metrics: Player Round Averages, Most Submitted Songs, Most Artist Appearances
# ---------------------------------------------------------------------------


import pandas as pd

# Ensure stdout can handle Unicode (emoji) on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class LeagueData:
    """
    Holds the four core DataFrames for one or more merged leagues.

    When built from multiple directories the DataFrames are concatenated:
      - competitors: de-duplicated by ID (same person, same ID across leagues)
      - rounds:      all rounds from every league (IDs are GUIDs – no collisions)
      - submissions: all submissions from every league

      - votes:       all votes from every league

    The ``league_rounds`` attribute is a list of per-league rounds DataFrames,
    used by stats that must be scoped within a single league
    (e.g. most_improved, biggest_blowout).
    """
    competitors:   pd.DataFrame
    rounds:        pd.DataFrame
    submissions:   pd.DataFrame
    votes:         pd.DataFrame
    league_rounds: list[pd.DataFrame]   # one entry per source directory
    league_names:  list[str]            # display name (folder basename) per league


# ---------------------------------------------------------------------------

# Data loading
# ---------------------------------------------------------------------------

def _load_single_dir(data_dir: str) -> dict[str, pd.DataFrame]:
    """Load and normalise the four CSVs from one directory."""
    paths = {
        "competitors": os.path.join(data_dir, "competitors.csv"),
        "rounds":      os.path.join(data_dir, "rounds.csv"),
        "submissions": os.path.join(data_dir, "submissions.csv"),
        "votes":       os.path.join(data_dir, "votes.csv"),
    }
    dfs: dict[str, pd.DataFrame] = {}
    for key, path in paths.items():
        dfs[key] = pd.read_csv(path)
        dfs[key].columns = dfs[key].columns.str.strip()

    dfs["submissions"].rename(columns={"Spotify URI": "SpotifyURI"}, inplace=True)
    dfs["votes"].rename(columns={
        "Spotify URI":     "SpotifyURI",
        "Points Assigned": "Points",
    }, inplace=True)

    return dfs


def load_data(data_dir: str) -> LeagueData:
    """
    Load a single league directory and return a LeagueData object.
    Kept for backwards compatibility.
    """
    return load_data_from_dirs([data_dir])


def load_data_from_dirs(data_dirs: list[str]) -> LeagueData:
    """
    Load one or more league directories and merge them into a single
    LeagueData object.

    Args:
        data_dirs: List of paths to league data folders.  Pass a list with
                   one entry for single-league mode.

    Returns:
        A LeagueData instance whose DataFrames span all supplied leagues.
    """
    if not data_dirs:
        raise ValueError("At least one data directory must be supplied.")

    all_dfs: list[dict[str, pd.DataFrame]] = [_load_single_dir(d) for d in data_dirs]

    # Merge each table
    competitors = (
        pd.concat([d["competitors"] for d in all_dfs], ignore_index=True)
        .drop_duplicates(subset="ID")          # same person appears in both leagues
        .reset_index(drop=True)
    )
    rounds = pd.concat(
        [d["rounds"] for d in all_dfs], ignore_index=True
    ).drop_duplicates(subset="ID").reset_index(drop=True)

    submissions = pd.concat(
        [d["submissions"] for d in all_dfs], ignore_index=True
    ).drop_duplicates(subset=["SpotifyURI", "Round ID"]).reset_index(drop=True)

    votes = pd.concat(
        [d["votes"] for d in all_dfs], ignore_index=True
    ).drop_duplicates(subset=["SpotifyURI", "Voter ID", "Round ID"]).reset_index(drop=True)

    return LeagueData(
        competitors   = competitors,
        rounds        = rounds,
        submissions   = submissions,
        votes         = votes,
        league_rounds = [d["rounds"] for d in all_dfs],
        league_names  = [os.path.basename(os.path.normpath(d)) for d in data_dirs],
    )


def _format_name(full_name: str) -> str:
    """
    Shorten a full name to "First L." format.
    Handles names separated by a space (e.g. "Julie Fainberg")
    or a dot (e.g. "julie.fainberg").
    If the name has only one part, it is returned as-is.
    """
    # Split on either whitespace or a literal dot
    parts = [p for p in re.split(r'[\s.]+', full_name.strip()) if p]
    if len(parts) < 2:
        return full_name.capitalize()
    return f"{parts[0].capitalize()} {parts[-1][0].upper()}."


def _name_map(competitors: pd.DataFrame) -> dict[str, str]:
    """Return {competitor_id: shortened display name} dict."""
    return {cid: _format_name(name) for cid, name in zip(competitors["ID"], competitors["Name"])}


# ---------------------------------------------------------------------------
# Helper: build the core "points per submission per round" table
# ---------------------------------------------------------------------------

def _points_per_submission(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
) -> pd.DataFrame:
    """
    Returns a DataFrame with one row per (Round ID, SpotifyURI, Submitter ID)
    containing the total points that submission received in that round.
    """
    pts = (
        votes.groupby(["Round ID", "SpotifyURI"])["Points"]
        .sum()
        .reset_index()
        .rename(columns={"Points": "TotalPoints"})
    )
    merged = submissions.merge(pts, on=["SpotifyURI", "Round ID"], how="left")
    merged["TotalPoints"] = merged["TotalPoints"].fillna(0).astype(int)
    return merged


def _voter_count_per_submission(votes: pd.DataFrame) -> pd.DataFrame:
    """Returns {(Round ID, SpotifyURI): voter_count}."""
    vc = (
        votes[votes["Points"] > 0]
        .groupby(["Round ID", "SpotifyURI"])["Voter ID"]
        .nunique()
        .reset_index()
        .rename(columns={"Voter ID": "VoterCount"})
    )
    return vc


# ---------------------------------------------------------------------------
# New Metrics: Player Round Averages, Most Submitted Songs, Most Artist Appearances
# ---------------------------------------------------------------------------

def player_round_averages(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    competitors: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Returns a list of players with their average points per round, ranked descending."""
    names = _name_map(competitors)
    pps = _points_per_submission(submissions, votes)
    avg = (
        pps.groupby("Submitter ID")["TotalPoints"]
        .mean()
        .reset_index()
        .rename(columns={"TotalPoints": "AvgPoints"})
        .sort_values("AvgPoints", ascending=False)
    )
    return [
        {
            "rank":       i + 1,
            "name":       names.get(row["Submitter ID"], row["Submitter ID"]),
            "avg_points": round(row["AvgPoints"], 2),
        }
        for i, (_, row) in enumerate(avg.iterrows())
    ]


def most_submitted_songs(
    submissions: pd.DataFrame,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """
    Returns a ranked list of songs (by Title + Artist(s)) submitted more than once.
    """
    grouped = (
        submissions.groupby(["Title", "Artist(s)"])
        .size()
        .reset_index(name="Count")
        .sort_values("Count", ascending=False)
    )
    filtered = grouped[grouped["Count"] > 1].head(top_n)
    return [
        {
            "rank":   i + 1,
            "title":  row["Title"],
            "artist": row["Artist(s)"],
            "count":  int(row["Count"]),
        }
        for i, (_, row) in enumerate(filtered.iterrows())
    ]


def most_artist_appearances(
    submissions: pd.DataFrame,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """
    Returns a ranked list of artists by number of appearances across all submissions.
    Handles multiple artists per submission (comma-separated).
    """
    all_artists: list[str] = []
    for artists_str in submissions["Artist(s)"].dropna():
        for artist in artists_str.split(","):
            artist = artist.strip()
            if artist:
                all_artists.append(artist)
    counter: dict[str, int] = defaultdict(int)
    for a in all_artists:
        counter[a] += 1
    ranked = sorted(counter.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [
        {"rank": i + 1, "artist": artist, "count": count}
        for i, (artist, count) in enumerate(ranked)
    ]


# ---------------------------------------------------------------------------
# Individual stat functions
# ---------------------------------------------------------------------------

def top_3_winners(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    competitors: pd.DataFrame,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Top competitors by total points received across all rounds."""
    names = _name_map(competitors)
    pps = _points_per_submission(submissions, votes)
    totals = (
        pps.groupby("Submitter ID")["TotalPoints"]
        .sum()
        .reset_index()
        .sort_values("TotalPoints", ascending=False)
        .head(top_n)
    )
    return [
        {
            "rank":   rank + 1,
            "name":   names.get(row["Submitter ID"], row["Submitter ID"]),
            "points": int(row["TotalPoints"]),
        }
        for rank, (_, row) in enumerate(totals.iterrows())
    ]


def top_podium_appearances(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    competitors: pd.DataFrame,
    rounds: pd.DataFrame,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """
    Count how many times each competitor finished in the top-N
    within a single round.
    """
    names = _name_map(competitors)
    pps   = _points_per_submission(submissions, votes)

    appearances: dict[str, int] = defaultdict(int)
    for _, round_row in rounds.iterrows():
        rid    = round_row["ID"]
        subset = pps[pps["Round ID"] == rid].sort_values(
            "TotalPoints", ascending=False
        )
        podium = subset.head(top_n)["Submitter ID"]
        for sid in podium:
            appearances[sid] += 1

    sorted_apps = sorted(appearances.items(), key=lambda x: x[1], reverse=True)
    return [
        {"name": names.get(sid, sid), "podium_appearances": count}
        for sid, count in sorted_apps
    ]


def most_misunderstood(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    competitors: pd.DataFrame,
    top_n: int = 3,
    league_rounds: list[pd.DataFrame] | None = None,
) -> list[dict[str, Any]]:
    """
    Bottom competitors by total points received (least points = most misunderstood).

    Only players who participated in the most recent league are eligible.
    The most recent league is determined by finding the league whose rounds
    contain the latest submission ``Created`` date.  Total points are still
    calculated across all data (cumulative mode).
    """
    names = _name_map(competitors)
    pps   = _points_per_submission(submissions, votes)

    # --- Identify which submitter IDs are in the most recent league ----------
    if league_rounds and len(league_rounds) > 1:
        # Parse submission dates once
        subs_dated = submissions.copy()
        subs_dated["Created"] = pd.to_datetime(subs_dated["Created"], utc=True, errors="coerce")

        # For each league, find the latest submission date among its rounds
        latest_dates: list[pd.Timestamp] = []
        for lr in league_rounds:
            league_round_ids = set(lr["ID"].tolist())
            mask = subs_dated["Round ID"].isin(league_round_ids)
            if mask.any():
                latest_dates.append(subs_dated.loc[mask, "Created"].max())
            else:
                latest_dates.append(pd.Timestamp.min.tz_localize("UTC"))

        # The most recent league is whichever has the latest submission date
        most_recent_idx = int(pd.Series(latest_dates).argmax())
        recent_round_ids = set(league_rounds[most_recent_idx]["ID"].tolist())
        recent_submitters = set(
            submissions.loc[submissions["Round ID"].isin(recent_round_ids), "Submitter ID"]
        )
    else:
        # Single league — all submitters are eligible
        recent_submitters = set(submissions["Submitter ID"].unique())

    # --- Rank eligible players by total points (ascending) -------------------
    totals = (
        pps.groupby("Submitter ID")["TotalPoints"]
        .sum()
        .reset_index()
    )
    totals = totals[totals["Submitter ID"].isin(recent_submitters)]
    totals = totals.sort_values("TotalPoints", ascending=True).head(top_n)

    return [
        {
            "rank":   rank + 1,
            "name":   names.get(row["Submitter ID"], row["Submitter ID"]),
            "points": int(row["TotalPoints"]),
        }
        for rank, (_, row) in enumerate(totals.iterrows())
    ]


def most_universally_liked(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    competitors: pd.DataFrame,
    top_n: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """
    Returns two top-N lists:
      - by_points:  songs that earned the most total points
      - by_voters:  songs that received points from the most distinct voters
    """
    names = _name_map(competitors)
    pps = _points_per_submission(submissions, votes)
    vc  = _voter_count_per_submission(votes)
    merged = pps.merge(vc, on=["Round ID", "SpotifyURI"], how="left")
    merged["VoterCount"] = merged["VoterCount"].fillna(0).astype(int)

    def _fmt(row: pd.Series) -> dict[str, Any]:
        return {
            "title":        row["Title"],
            "artist":       row["Artist(s)"],
            "submitted_by": names.get(row["Submitter ID"], row["Submitter ID"]),
            "total_points": int(row["TotalPoints"]),
            "voter_count":  int(row["VoterCount"]),
        }

    by_points = merged.sort_values("TotalPoints", ascending=False).head(top_n)
    by_voters = merged.sort_values("VoterCount",  ascending=False).head(top_n)

    return {
        "by_points": [_fmt(r) for _, r in by_points.iterrows()],
        "by_voters": [_fmt(r) for _, r in by_voters.iterrows()],
    }


def biggest_fans(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    competitors: pd.DataFrame,
    target_name: str,
) -> list[dict[str, Any]]:
    """
    For a given competitor (by name), show who gave them the most points
    across the whole league, sorted descending.
    """
    names   = _name_map(competitors)
    inv_map = {v: k for k, v in names.items()}
    target_id = inv_map.get(target_name)
    if target_id is None:
        raise ValueError(f"Competitor '{target_name}' not found.")

    target_tracks = submissions[submissions["Submitter ID"] == target_id]["SpotifyURI"]
    relevant_votes = votes[votes["SpotifyURI"].isin(target_tracks)]

    totals = (
        relevant_votes.groupby("Voter ID")["Points"]
        .sum()
        .reset_index()
        .sort_values("Points", ascending=False)
    )
    return [
        {"voter": names.get(row["Voter ID"], row["Voter ID"]), "points_given": int(row["Points"])}
        for _, row in totals.iterrows()
    ]


def least_compatible(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    competitors: pd.DataFrame,
    target_name: str,
) -> list[dict[str, Any]]:
    """
    For a given competitor (by name), show who gave them the fewest points
    across the whole league, sorted ascending.
    """
    result = biggest_fans(submissions, votes, competitors, target_name)
    return sorted(result, key=lambda x: x["points_given"])


def most_generous_voter(
    votes: pd.DataFrame,
    submissions: pd.DataFrame,
    competitors: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    Each round, count the number of distinct submitters a voter spread points to.
    Average that count across all rounds – highest average = most generous/spread.
    """
    names = _name_map(competitors)
    # Map SpotifyURI → Submitter ID
    uri_to_submitter = dict(zip(submissions["SpotifyURI"], submissions["Submitter ID"]))
    votes = votes.copy()
    votes["SubmitterID"] = votes["SpotifyURI"].map(uri_to_submitter)

    positive_votes = votes[votes["Points"] > 0]

    spread_per_round = (
        positive_votes.groupby(["Round ID", "Voter ID"])["SubmitterID"]
        .nunique()
        .reset_index()
        .rename(columns={"SubmitterID": "DistinctRecipients"})
    )
    avg_spread = (
        spread_per_round.groupby("Voter ID")["DistinctRecipients"]
        .mean()
        .reset_index()
        .sort_values("DistinctRecipients", ascending=False)
    )
    return [
        {
            "voter":           names.get(row["Voter ID"], row["Voter ID"]),
            "avg_distinct_recipients_per_round": round(row["DistinctRecipients"], 2),
        }
        for _, row in avg_spread.iterrows()
    ]


def most_consistent_submitter(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    competitors: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    Variance of weekly points received per submitter.
    Lowest variance = most consistent.
    Requires at least 2 rounds of submissions.
    """
    names = _name_map(competitors)
    pps   = _points_per_submission(submissions, votes)
    variance = (
        pps.groupby("Submitter ID")["TotalPoints"]
        .var()
        .reset_index()
        .rename(columns={"TotalPoints": "Variance"})
        .dropna()
        .sort_values("Variance", ascending=True)
    )
    return [
        {
            "name":     names.get(row["Submitter ID"], row["Submitter ID"]),
            "variance": round(row["Variance"], 2),
        }
        for _, row in variance.iterrows()
    ]


def most_volatile_submitter(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    competitors: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Highest variance of weekly points received = most volatile."""
    result = most_consistent_submitter(submissions, votes, competitors)
    return list(reversed(result))


def most_improved(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    competitors: pd.DataFrame,
    rounds: pd.DataFrame,
    first_n: int = 5,
    last_n:  int = 5,
    league_rounds: list[pd.DataFrame] | None = None,
) -> list[dict[str, Any]]:
    """
    Compare average points in the first N rounds vs the last N rounds.
    Highest improvement = most improved.

    When ``league_rounds`` is supplied (cumulative mode) the first/last N
    rounds are drawn from each individual league independently, then averaged
    together across leagues.  This prevents rounds from different leagues
    being mixed into the same "first 5".
    """
    names = _name_map(competitors)
    pps   = _points_per_submission(submissions, votes)

    # Build the list of per-league (first_ids, last_ids) pairs
    if league_rounds and len(league_rounds) > 1:
        slice_pairs: list[tuple[set[str], set[str]]] = []
        for lr in league_rounds:
            sorted_lr  = lr.sort_values("Created").reset_index(drop=True)
            slice_pairs.append((
                set(sorted_lr.head(first_n)["ID"]),
                set(sorted_lr.tail(last_n)["ID"]),
            ))
    else:
        rounds_sorted = rounds.sort_values("Created").reset_index(drop=True)
        slice_pairs = [(
            set(rounds_sorted.head(first_n)["ID"]),
            set(rounds_sorted.tail(last_n)["ID"]),
        )]

    # Accumulate per-person averages across all leagues then combine
    all_first: list[pd.Series] = []
    all_last:  list[pd.Series] = []
    for first_ids, last_ids in slice_pairs:
        fa = (
            pps[pps["Round ID"].isin(first_ids)]
            .groupby("Submitter ID")["TotalPoints"]
            .mean()
        )
        la = (
            pps[pps["Round ID"].isin(last_ids)]
            .groupby("Submitter ID")["TotalPoints"]
            .mean()
        )
        all_first.append(fa)
        all_last.append(la)

    first_avg = pd.concat(all_first).groupby(level=0).mean().rename("FirstAvg")
    last_avg  = pd.concat(all_last).groupby(level=0).mean().rename("LastAvg")

    combined = pd.concat([first_avg, last_avg], axis=1).dropna()
    combined["Improvement"] = combined["LastAvg"] - combined["FirstAvg"]
    combined = combined.sort_values("Improvement", ascending=False).reset_index()

    return [
        {
            "name":        names.get(row["Submitter ID"], row["Submitter ID"]),
            "first_avg":   round(row["FirstAvg"],    2),
            "last_avg":    round(row["LastAvg"],     2),
            "improvement": round(row["Improvement"], 2),
        }
        for _, row in combined.iterrows()
    ]


def biggest_blowout(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    rounds: pd.DataFrame,
    competitors: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    For each round, find the margin between 1st and 2nd place.
    Returns rounds sorted by margin descending.
    Works identically in single and cumulative mode — all rounds are
    considered and the round name is prefixed with its league when there
    are multiple leagues.
    """
    names = _name_map(competitors)
    pps   = _points_per_submission(submissions, votes)

    results = []
    for _, round_row in rounds.iterrows():
        rid    = round_row["ID"]
        subset = (
            pps[pps["Round ID"] == rid]
            .sort_values("TotalPoints", ascending=False)
            .reset_index(drop=True)
        )
        if len(subset) < 2:
            continue
        first  = subset.iloc[0]
        second = subset.iloc[1]
        margin = int(first["TotalPoints"]) - int(second["TotalPoints"])
        results.append({
            "round":          round_row["Name"],
            "winner":         names.get(first["Submitter ID"],  first["Submitter ID"]),
            "winner_song":    first["Title"],
            "winner_points":  int(first["TotalPoints"]),
            "second_place":   names.get(second["Submitter ID"], second["Submitter ID"]),
            "second_points":  int(second["TotalPoints"]),
            "margin":         margin,
        })

    return sorted(results, key=lambda x: x["margin"], reverse=True)


def most_talkative_commenter(
    votes: pd.DataFrame,
    submissions: pd.DataFrame,
    competitors: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    Count comments made in votes + comments on submissions.
    Returns competitors sorted by total comment count descending.
    """
    names = _name_map(competitors)

    # Comments in votes (non-empty)
    vote_comments = (
        votes[votes["Comment"].notna() & (votes["Comment"].str.strip() != "")]
        .groupby("Voter ID")
        .size()
        .rename("VoteComments")
    )

    # Comments on submissions (non-empty)
    sub_comments = (
        submissions[
            submissions["Comment"].notna() & (submissions["Comment"].str.strip() != "")
        ]
        .groupby("Submitter ID")
        .size()
        .rename("SubComments")
    )

    combined = pd.concat([vote_comments, sub_comments], axis=1).fillna(0)
    combined["Total"] = combined["VoteComments"] + combined["SubComments"]
    combined = combined.sort_values("Total", ascending=False).reset_index()
    combined.rename(columns={"index": "ID"}, inplace=True)
    # Handle both potential index column names
    id_col = "index" if "index" in combined.columns else combined.columns[0]

    return [
        {
            "name":          names.get(combined.iloc[i][id_col], combined.iloc[i][id_col]),
            "vote_comments": int(combined.iloc[i]["VoteComments"]),
            "sub_comments":  int(combined.iloc[i]["SubComments"]),
            "total":         int(combined.iloc[i]["Total"]),
        }
        for i in range(len(combined))
    ]


def funniest_comment(
    votes: pd.DataFrame,
    submissions: pd.DataFrame,
    competitors: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    Returns all comments (from both votes and submissions) with their author,
    so you can manually pick the funniest or feed them into an LLM ranking.
    """
    names = _name_map(competitors)

    vote_rows = votes[votes["Comment"].notna() & (votes["Comment"].str.strip() != "")].copy()
    vote_rows["author_id"] = vote_rows["Voter ID"]
    vote_rows["source"]    = "vote"
    vote_rows["context"]   = vote_rows["SpotifyURI"]

    sub_rows = submissions[
        submissions["Comment"].notna() & (submissions["Comment"].str.strip() != "")
    ].copy()
    sub_rows["author_id"] = sub_rows["Submitter ID"]
    sub_rows["source"]    = "submission"
    sub_rows["context"]   = sub_rows["Title"] + " – " + sub_rows["Artist(s)"]

    all_comments = pd.concat(
        [
            vote_rows[["author_id", "source", "context", "Comment"]],
            sub_rows[["author_id", "source", "context", "Comment"]],
        ],
        ignore_index=True,
    )

    return [
        {
            "author":  names.get(row["author_id"], row["author_id"]),
            "source":  row["source"],
            "context": row["context"],
            "comment": row["Comment"],
        }
        for _, row in all_comments.iterrows()
    ]


def point_economy_summary(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    rounds: pd.DataFrame,
) -> dict[str, Any]:
    """
    Summary of the point economy:
      - total points distributed
      - average points per round
      - average points per submission
      - min / max points in a single round
    """
    pps = _points_per_submission(submissions, votes)

    per_round = pps.groupby("Round ID")["TotalPoints"].sum()

    return {
        "total_points_distributed": int(pps["TotalPoints"].sum()),
        "num_rounds":               len(rounds),
        "avg_points_per_round":     round(per_round.mean(), 2),
        "min_points_in_round":      int(per_round.min()),
        "max_points_in_round":      int(per_round.max()),
        "avg_points_per_submission": round(pps["TotalPoints"].mean(), 2),
    }


def zero_points_incidents(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    competitors: pd.DataFrame,
) -> dict[str, Any]:
    """
    Count how many times each submitter scored zero in a round.
    Returns overall count and a per-person breakdown.
    """
    names = _name_map(competitors)
    pps   = _points_per_submission(submissions, votes)
    zeros = pps[pps["TotalPoints"] == 0]

    per_person = (
        zeros.groupby("Submitter ID")
        .size()
        .reset_index(name="ZeroRounds")
        .sort_values("ZeroRounds", ascending=False)
    )

    return {
        "total_zero_incidents": len(zeros),
        "by_person": [
            {"name": names.get(r["Submitter ID"], r["Submitter ID"]), "zero_rounds": int(r["ZeroRounds"])}
            for _, r in per_person.iterrows()
        ],
    }


def top_3_comment_winners(
    submissions: pd.DataFrame,
    votes: pd.DataFrame,
    competitors: pd.DataFrame,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """
    Count comments received per submitter (comments left on their songs in votes).
    Returns the top N.
    """
    names = _name_map(competitors)

    # Map track → submitter
    uri_to_submitter = dict(zip(submissions["SpotifyURI"], submissions["Submitter ID"]))
    votes = votes.copy()
    votes["SubmitterID"] = votes["SpotifyURI"].map(uri_to_submitter)

    comments_received = (
        votes[votes["Comment"].notna() & (votes["Comment"].str.strip() != "")]
        .groupby("SubmitterID")
        .size()
        .reset_index(name="CommentsReceived")
        .sort_values("CommentsReceived", ascending=False)
        .head(top_n)
    )

    return [
        {
            "rank":              rank + 1,
            "name":              names.get(row["SubmitterID"], row["SubmitterID"]),
            "comments_received": int(row["CommentsReceived"]),
        }
        for rank, (_, row) in enumerate(comments_received.iterrows())
    ]


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_full_report(
    data: LeagueData | str,
    target_name: str | None = None,
) -> None:
    """
    Print a full human-readable report to stdout.

    Args:
        data:        Either a LeagueData object (from load_data_from_dirs) or
                     a single directory path string (backwards compatible).
        target_name: (Optional) A specific competitor name used for the
                     Biggest Fans / Least Compatible sections.
                     If omitted, the top point-scorer is used.
    """
    if isinstance(data, str):
        data = load_data(data)

    comp = data.competitors
    rds  = data.rounds
    subs = data.submissions
    vts  = data.votes

    is_cumulative = len(data.league_names) > 1
    scope_label   = (
        f"Cumulative ({', '.join(data.league_names)})"
        if is_cumulative
        else data.league_names[0]
    )

    print(f"\n{'#'*60}")
    print(f"  MUSIC LEAGUE STATS  —  {scope_label}")
    print(f"{'#'*60}")

    # If no target supplied, use the #1 overall winner
    if target_name is None:
        target_name = top_3_winners(subs, vts, comp)[0]["name"]

    # ---- Top 3 Winners ----
    _section("🏆  Top 3 Winners (Total Points)")
    for entry in top_3_winners(subs, vts, comp):
        print(f"  #{entry['rank']}  {entry['name']:<25}  {entry['points']} pts")

    # ---- Top Podium Appearances ----
    _section("🥇  Top Podium Appearances (Top-3 Finishes)")
    for entry in top_podium_appearances(subs, vts, comp, rds)[:5]:
        print(f"  {entry['name']:<25}  {entry['podium_appearances']} appearances")

    # ---- Most Misunderstood ----
    _section("😢  Most Misunderstood (Lowest Total Points)")
    for entry in most_misunderstood(subs, vts, comp):
        print(f"  #{entry['rank']}  {entry['name']:<25}  {entry['points']} pts")

    # ---- Most Universally Liked ----
    _section("❤️   Most Universally Liked Songs — by Points")
    for i, s in enumerate(most_universally_liked(subs, vts, comp)["by_points"], 1):
        print(f"  #{i}  {s['title']:<40}  {s['artist']:<25}  {s['total_points']} pts")

    _section("❤️   Most Universally Liked Songs — by Voters")
    for i, s in enumerate(most_universally_liked(subs, vts, comp)["by_voters"], 1):
        print(f"  #{i}  {s['title']:<40}  {s['artist']:<25}  {s['voter_count']} voters")

    # ---- Biggest Fans / Least Compatible ----
    _section(f"🤝  Biggest Fans of {target_name}")
    for entry in biggest_fans(subs, vts, comp, target_name)[:5]:
        print(f"  {entry['voter']:<25}  {entry['points_given']} pts given")

    _section(f"💔  Least Compatible with {target_name}")
    for entry in least_compatible(subs, vts, comp, target_name)[:5]:
        print(f"  {entry['voter']:<25}  {entry['points_given']} pts given")

    # ---- Most Generous Voter ----
    _section("🎁  Most Generous Voter (Widest Point Spread Per Round)")
    for entry in most_generous_voter(vts, subs, comp)[:5]:
        print(f"  {entry['voter']:<25}  avg {entry['avg_distinct_recipients_per_round']} distinct recipients/round")

    # ---- Consistency ----
    _section("📏  Most Consistent Submitter (Lowest Points Variance)")
    for entry in most_consistent_submitter(subs, vts, comp)[:5]:
        print(f"  {entry['name']:<25}  variance = {entry['variance']}")

    _section("🎢  Most Volatile Submitter (Highest Points Variance)")
    for entry in most_volatile_submitter(subs, vts, comp)[:5]:
        print(f"  {entry['name']:<25}  variance = {entry['variance']}")

    # ---- Most Improved ----
    _section("📈  Most Improved (First 5 vs Last 5 Rounds per League)")
    for entry in most_improved(subs, vts, comp, rds, league_rounds=data.league_rounds)[:5]:
        print(
            f"  {entry['name']:<25}  "
            f"first avg={entry['first_avg']:>6.1f}  "
            f"last avg={entry['last_avg']:>6.1f}  "
            f"Δ={entry['improvement']:>+.1f}"
        )

    # ---- Biggest Blowout ----
    _section("💥  Biggest Blowout (Largest 1st–2nd Margin)")
    for entry in biggest_blowout(subs, vts, rds, comp)[:3]:
        print(
            f"  {entry['round']:<35}  "
            f"{entry['winner']} ({entry['winner_points']} pts) "
            f"beat {entry['second_place']} ({entry['second_points']} pts) "
            f"by {entry['margin']}"
        )

    # ---- Most Talkative ----
    _section("💬  Most Talkative Commenter")
    for entry in most_talkative_commenter(vts, subs, comp)[:5]:
        print(f"  {entry['name']:<25}  {entry['total']} comments  (votes: {entry['vote_comments']}, subs: {entry['sub_comments']})")

    # ---- Funniest Comment ----
    _section("😂  All Comments (pick your funniest!)")
    for entry in funniest_comment(vts, subs, comp):
        print(f"  [{entry['source']}] {entry['author']:<20} on '{entry['context']}':")
        print(f"      \"{entry['comment']}\"")

    # ---- Point Economy ----
    _section("💰  Point Economy Summary")
    pe = point_economy_summary(subs, vts, rds)
    print(f"  Total points distributed :  {pe['total_points_distributed']}")
    print(f"  Number of rounds         :  {pe['num_rounds']}")
    print(f"  Avg points per round     :  {pe['avg_points_per_round']}")
    print(f"  Min / Max points in round:  {pe['min_points_in_round']} / {pe['max_points_in_round']}")
    print(f"  Avg points per submission:  {pe['avg_points_per_submission']}")

    # ---- Zero Points Incidents ----
    _section("0️⃣   Zero Points Incidents")
    zpi = zero_points_incidents(subs, vts, comp)
    print(f"  Total zero-point rounds: {zpi['total_zero_incidents']}")
    for entry in zpi["by_person"]:
        print(f"  {entry['name']:<25}  {entry['zero_rounds']}x")

    # ---- Top 3 Comment Winners ----
    _section("📝  Top 3 Comment Winners (Most Comments Received)")
    for entry in top_3_comment_winners(subs, vts, comp):
        print(f"  #{entry['rank']}  {entry['name']:<25}  {entry['comments_received']} comments")


# ---------------------------------------------------------------------------
# Text report generator  (used by the Streamlit download button)
# ---------------------------------------------------------------------------

def generate_report_text(data: LeagueData, target_name: str | None = None) -> str:
    """
    Render the full stats report as a plain-text string instead of printing
    to stdout.  Identical content to print_full_report().

    Args:
        data:        A LeagueData object.
        target_name: Optional competitor name for Fans / Compat sections.
                     Defaults to the overall #1 winner.

    Returns:
        A UTF-8 string ready to be written to a file or returned as a
        Streamlit download.
    """
    import io as _io
    buf = _io.StringIO()

    def _p(*args, **kwargs):
        print(*args, **kwargs, file=buf)

    def _sec(title: str):
        _p(f"\n{'='*60}")
        _p(f"  {title}")
        _p(f"{'='*60}")

    comp = data.competitors
    rds  = data.rounds
    subs = data.submissions
    vts  = data.votes

    if target_name is None:
        target_name = top_3_winners(subs, vts, comp)[0]["name"]

    scope = (
        f"Cumulative ({', '.join(data.league_names)})"
        if len(data.league_names) > 1
        else data.league_names[0]
    )
    _p(f"{'#'*60}")
    _p(f"  MUSIC LEAGUE STATS  —  {scope}")
    _p(f"{'#'*60}")

    _sec("Top 3 Winners (Total Points)")
    for e in top_3_winners(subs, vts, comp):
        _p(f"  #{e['rank']}  {e['name']:<25}  {e['points']} pts")

    _sec("Top Podium Appearances (Top-3 Finishes)")
    for e in top_podium_appearances(subs, vts, comp, rds)[:5]:
        _p(f"  {e['name']:<25}  {e['podium_appearances']} appearances")

    _sec("Most Misunderstood (Lowest Total Points)")
    for e in most_misunderstood(subs, vts, comp):
        _p(f"  #{e['rank']}  {e['name']:<25}  {e['points']} pts")

    _sec("Most Universally Liked Songs -- by Points")
    for i, s in enumerate(most_universally_liked(subs, vts, comp)["by_points"], 1):
        _p(f"  #{i}  {s['title']:<40}  {s['artist']:<25}  {s['total_points']} pts")

    _sec("Most Universally Liked Songs -- by Voters")
    for i, s in enumerate(most_universally_liked(subs, vts, comp)["by_voters"], 1):
        _p(f"  #{i}  {s['title']:<40}  {s['artist']:<25}  {s['voter_count']} voters")

    _sec(f"Biggest Fans of {target_name}")
    for e in biggest_fans(subs, vts, comp, target_name)[:5]:
        _p(f"  {e['voter']:<25}  {e['points_given']} pts given")

    _sec(f"Least Compatible with {target_name}")
    for e in least_compatible(subs, vts, comp, target_name)[:5]:
        _p(f"  {e['voter']:<25}  {e['points_given']} pts given")

    _sec("Most Generous Voter (Widest Point Spread Per Round)")
    for e in most_generous_voter(vts, subs, comp)[:5]:
        _p(f"  {e['voter']:<25}  avg {e['avg_distinct_recipients_per_round']} distinct recipients/round")

    _sec("Most Consistent Submitter (Lowest Points Variance)")
    for e in most_consistent_submitter(subs, vts, comp)[:5]:
        _p(f"  {e['name']:<25}  variance = {e['variance']}")

    _sec("Most Volatile Submitter (Highest Points Variance)")
    for e in most_volatile_submitter(subs, vts, comp)[:5]:
        _p(f"  {e['name']:<25}  variance = {e['variance']}")

    _sec("Most Improved (First 5 vs Last 5 Rounds per League)")
    for e in most_improved(subs, vts, comp, rds, league_rounds=data.league_rounds)[:5]:
        _p(f"  {e['name']:<25}  first avg={e['first_avg']:>6.1f}  "
           f"last avg={e['last_avg']:>6.1f}  delta={e['improvement']:>+.1f}")

    _sec("Biggest Blowout (Largest 1st-2nd Margin)")
    for e in biggest_blowout(subs, vts, rds, comp)[:3]:
        _p(f"  {e['round']:<35}  {e['winner']} ({e['winner_points']} pts) "
           f"beat {e['second_place']} ({e['second_points']} pts) by {e['margin']}")

    _sec("Most Talkative Commenter")
    for e in most_talkative_commenter(vts, subs, comp)[:5]:
        _p(f"  {e['name']:<25}  {e['total']} comments  "
           f"(votes: {e['vote_comments']}, subs: {e['sub_comments']})")

    _sec("All Comments")
    for e in funniest_comment(vts, subs, comp):
        _p(f"  [{e['source']}] {e['author']:<20} on '{e['context']}':")
        _p(f"      \"{e['comment']}\"")

    _sec("Point Economy Summary")
    pe = point_economy_summary(subs, vts, rds)
    _p(f"  Total points distributed :  {pe['total_points_distributed']}")
    _p(f"  Number of rounds         :  {pe['num_rounds']}")
    _p(f"  Avg points per round     :  {pe['avg_points_per_round']}")
    _p(f"  Min / Max points in round:  {pe['min_points_in_round']} / {pe['max_points_in_round']}")
    _p(f"  Avg points per submission:  {pe['avg_points_per_submission']}")

    _sec("Zero Points Incidents")
    zpi = zero_points_incidents(subs, vts, comp)
    _p(f"  Total zero-point rounds: {zpi['total_zero_incidents']}")
    for e in zpi["by_person"]:
        _p(f"  {e['name']:<25}  {e['zero_rounds']}x")

    _sec("Top 3 Comment Winners (Most Comments Received)")
    for e in top_3_comment_winners(subs, vts, comp):
        _p(f"  #{e['rank']}  {e['name']:<25}  {e['comments_received']} comments")

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Music League Statistics Calculator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single league
  python music_league_stats.py path/to/league1

  # Cumulative (two leagues merged)
  python music_league_stats.py path/to/league1 path/to/league2

  # Specify a player for the Biggest Fans / Least Compatible sections
  python music_league_stats.py path/to/league1 path/to/league2 --target "Alice"
        """,
    )
    parser.add_argument(
        "dirs",
        nargs="+",
        metavar="DATA_DIR",
        help="One or more paths to league data folders.",
    )
    parser.add_argument(
        "--target",
        default=None,
        metavar="NAME",
        help="Player name for Biggest Fans / Least Compatible sections.",
    )
    args = parser.parse_args()

    league_data = load_data_from_dirs(args.dirs)
    print_full_report(league_data, args.target)
