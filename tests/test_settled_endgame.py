"""Settled endgame types: a type counts only once the material has stood still for a few moves."""
import chess

from chessanalytics.endgame import STABLE_PLIES, settled_endgames


def _from(fen: str, moves: list[str]) -> list[str]:
    """Helper: play SAN moves from a FEN and return them (validates the line)."""
    b = chess.Board(fen)
    for m in moves:
        b.push_san(m)
    return moves


def test_rook_endgame_reached_after_queen_trade_settles():
    fen = "3qr1k1/5ppp/8/8/8/8/5PPP/3QR1K1 w - - 0 1"
    moves = _from(fen, ["Qxd8", "Rxd8", "Kf1", "Kf8", "Ke2", "Ke7", "Ke3", "Ke6"])
    out = settled_endgames(moves, fen)
    assert out["rook_ply"] == 2  # material stopped changing after the recapture on move 2
    assert out["rook_pawns"] == 0 and out["rook_material"] == 0
    assert out["settled_type"] == "Rook endgame" and out["final_type"] == "Rook endgame"
    assert out["queen_ply"] is None  # Q+R vs Q+R is not an endgame under the threshold, and it never settled


def test_mid_exchange_position_is_not_recorded():
    # after Qxd8 White is a queen up for one ply only: that must never be recorded as "Queen vs other pieces"
    fen = "3qr1k1/5ppp/8/8/8/8/5PPP/3QR1K1 w - - 0 1"
    out = settled_endgames(["Qxd8", "Rxd8", "Kf1", "Kf8", "Ke2"], fen)
    assert out["settled_type"] == "Rook endgame"


def test_too_short_to_settle():
    fen = "3qr1k1/5ppp/8/8/8/8/5PPP/3QR1K1 w - - 0 1"
    out = settled_endgames(["Qxd8", "Rxd8", "Kf1"], fen)  # rook ending stands for 2 plies only
    assert STABLE_PLIES > 2 and out["settled_type"] == ""


def test_opposite_bishops_with_extra_pawn():
    fen = "2b3k1/5ppp/8/8/8/8/4PPPP/2B3K1 w - - 0 1"  # c1 dark, c8 light: opposite colours, White a pawn up
    out = settled_endgames(_from(fen, ["Kf1", "Kf8", "Ke1", "Ke8", "Kd1"]), fen)
    assert out["ocb_ply"] == 1 and out["ocb_pawns"] == 1 and out["ocb_material"] == 1


def test_recorded_types_hold_for_the_required_plies_on_random_games():
    import random

    from chessanalytics.endgame import KEY_TYPES, _signature, classify

    for seed in range(15):
        rng, b, moves = random.Random(seed), chess.Board(), []
        while not b.is_game_over() and len(moves) < 250:
            legal = list(b.legal_moves)
            caps = [m for m in legal if b.is_capture(m)]
            m = rng.choice(caps if caps and rng.random() < 0.7 else legal)
            moves.append(b.san(m))
            b.push(m)
        out = settled_endgames(moves)
        positions = [chess.Board()]
        for m in moves:
            nb = positions[-1].copy(stack=False)
            nb.push_san(m)
            positions.append(nb)
        for cat, short in KEY_TYPES.items():
            ply = out[f"{short}_ply"]
            if ply is None:
                continue
            assert classify(positions[ply]) == cat
            sigs = {_signature(positions[p]) for p in range(ply, ply + STABLE_PLIES)}
            assert len(sigs) == 1
