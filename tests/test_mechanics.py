import numpy as np

from figgie_rl.envs.mechanics import COLOR_PAIR, INDEX_TO_SUIT, deal_round, draw_suit_distribution


def test_draw_distribution_shape_and_totals() -> None:
    rng = np.random.default_rng(123)
    dist = draw_suit_distribution(rng)
    assert int(np.sum(dist)) == 40
    assert sorted(dist.tolist()) == [8, 10, 10, 12]


def test_deal_round_inventories_and_goal_consistency() -> None:
    rng = np.random.default_rng(99)
    deal = deal_round(rng, num_players=4, hand_size=10)

    assert deal.inventories.shape == (4, 4)
    assert int(np.sum(deal.inventories)) == 40
    assert int(np.max(deal.suit_distribution)) == 12
    assert int(np.argmax(deal.suit_distribution)) == deal.heavy_suit_idx

    heavy = INDEX_TO_SUIT[deal.heavy_suit_idx]
    goal = INDEX_TO_SUIT[deal.goal_suit_idx]
    assert COLOR_PAIR[heavy] == goal
