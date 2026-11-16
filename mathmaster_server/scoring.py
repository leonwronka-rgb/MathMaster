from __future__ import annotations


def calculate_rating_changes(ratings: list[int], places: list[int]) -> list[int]:
    """Pairwise Elo change with the server-resolved final places."""
    changes: list[int] = []
    for index, rating in enumerate(ratings):
        change = 0.0
        for opponent_index, opponent_rating in enumerate(ratings):
            if index == opponent_index:
                continue
            expected = 1 / (1 + 10 ** ((opponent_rating - rating) / 400))
            actual = 1.0 if places[index] < places[opponent_index] else 0.0
            change += 24 * (actual - expected) / (len(ratings) - 1)
        changes.append(round(change))
    return changes

