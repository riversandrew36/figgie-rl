import numpy as np

from figgie_rl.envs.mechanics import settle_round


def test_settlement_majority_bonus_single_winner() -> None:
    inventories = np.array(
        [
            [3, 1, 0, 0],
            [1, 2, 0, 0],
            [0, 3, 0, 0],
            [2, 1, 0, 0],
        ],
        dtype=np.int32,
    )
    cash = np.array([10.0, 10.0, 10.0, 10.0], dtype=np.float64)
    final_bankroll = settle_round(
        inventories=inventories,
        cash=cash,
        goal_suit_idx=0,
        goal_card_value=10.0,
        goal_majority_bonus=40.0,
    )

    expected = np.array([80.0, 20.0, 10.0, 30.0], dtype=np.float64)
    np.testing.assert_allclose(final_bankroll, expected, atol=1e-8)


def test_settlement_bonus_split_on_tie() -> None:
    inventories = np.array(
        [
            [2, 0, 0, 0],
            [2, 0, 0, 0],
            [1, 0, 0, 0],
            [0, 0, 0, 0],
        ],
        dtype=np.int32,
    )
    cash = np.zeros(4, dtype=np.float64)
    final_bankroll = settle_round(
        inventories=inventories,
        cash=cash,
        goal_suit_idx=0,
        goal_card_value=10.0,
        goal_majority_bonus=40.0,
    )

    # Two winners split bonus equally: 2*10 + 20 each.
    expected = np.array([40.0, 40.0, 10.0, 0.0], dtype=np.float64)
    np.testing.assert_allclose(final_bankroll, expected, atol=1e-8)


def test_pot_conserving_settlement_distributes_exact_total() -> None:
    inventories = np.array(
        [[3, 0, 0, 0], [2, 0, 0, 0], [1, 0, 0, 0], [2, 0, 0, 0]],
        dtype=np.int32,
    )
    cash = np.full(4, 300.0, dtype=np.float64)
    final_bankroll = settle_round(
        inventories,
        cash,
        goal_suit_idx=0,
        goal_card_value=10.0,
        total_pot=200.0,
    )

    assert np.isclose(np.sum(final_bankroll - cash), 200.0)


def test_official_figgie_pot_example() -> None:
    """figgie.com example: goal counts 1, 3, 5, 1 pay $10 each, and 5 takes $100."""
    inventories = np.zeros((4, 4), dtype=np.int32)
    inventories[:, 0] = np.array([1, 3, 5, 1])
    cash = np.zeros(4, dtype=np.float64)
    final_bankroll = settle_round(
        inventories=inventories,
        cash=cash,
        goal_suit_idx=0,
        goal_card_value=10.0,
        total_pot=200.0,
    )

    np.testing.assert_allclose(final_bankroll, [10.0, 30.0, 150.0, 10.0])
    assert np.isclose(final_bankroll.sum(), 200.0)
