import pytest

from app.rollover import get_state, initialise, settle_leg


def test_four_odds_win_compounds_full_return_and_recalculates_stake(tmp_path):
    db = tmp_path / "rollover.sqlite3"
    initialise(db)
    state = get_state(db)
    assert state["equity_usd"] == 20.0
    assert state["next_cycle_stake_usd"] == 5.0
    assert state["reserve_usd"] == 15.0

    state = settle_leg("Madrid vs Getafe", "Madrid win", 4.0, "won", db)
    assert state["last_event"] == "target_hit"
    # $15 reserve + $20 returned stake = $35 equity.
    assert state["equity_usd"] == 35.0
    assert state["next_cycle_stake_usd"] == 8.75
    assert state["reserve_usd"] == 26.25
    assert state["pilot_ready"] is True
    assert state["execution_mode"] == "paper"
    assert state["orders_placed"] == 0


def test_sequential_legs_roll_the_full_return_until_four_odds(tmp_path):
    db = tmp_path / "rollover.sqlite3"
    initialise(db)
    state = settle_leg("Match 1", "Home win", 1.25, "won", db)
    assert state["last_event"] == "leg_recorded"
    assert state["equity_usd"] == 20.0
    assert state["cycle"]["cumulative_odds"] == pytest.approx(1.25)
    assert state["cycle"]["current_rollover_stake"] == pytest.approx(6.25)

    state = settle_leg("Match 2", "Home win", 1.4, "won", db)
    assert state["cycle"]["cumulative_odds"] == pytest.approx(1.75)
    assert state["cycle"]["current_rollover_stake"] == pytest.approx(8.75)

    state = settle_leg("Match 3", "Home win", 1.5, "won", db)
    assert state["cycle"]["cumulative_odds"] == pytest.approx(2.625)
    assert state["cycle"]["current_rollover_stake"] == pytest.approx(13.125)

    state = settle_leg("Match 4", "Home win", 1.55, "won", db)
    assert state["last_event"] == "target_hit"
    assert state["last_completed_cycle"]["cumulative_odds"] == pytest.approx(4.06875)
    assert state["equity_usd"] == pytest.approx(35.34375)


def test_loss_deducts_cycle_principal_and_recalculates_from_remaining_equity(tmp_path):
    db = tmp_path / "rollover.sqlite3"
    initialise(db)
    state = settle_leg("Match 1", "Home win", 1.5, "lost", db)
    assert state["last_event"] == "cycle_lost"
    assert state["equity_usd"] == 15.0
    assert state["next_cycle_stake_usd"] == 3.75
    assert state["reserve_usd"] == 11.25
    assert state["pilot_ready"] is False


def test_void_leg_does_not_advance_odds_or_change_equity(tmp_path):
    db = tmp_path / "rollover.sqlite3"
    initialise(db)
    state = settle_leg("Match abandoned", "Home win", 1.8, "void", db)
    assert state["equity_usd"] == 20.0
    assert state["cycle"]["cumulative_odds"] == 1.0
    assert state["cycle"]["current_rollover_stake"] == 5.0


def test_rejects_invalid_settlement_result(tmp_path):
    db = tmp_path / "rollover.sqlite3"
    initialise(db)
    with pytest.raises(ValueError, match="Result"):
        settle_leg("Match", "Home win", 2.0, "pending", db)
