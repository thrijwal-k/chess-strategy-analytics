# Endgames explained

## What an endgame is
An endgame is the last phase, after most pieces have been traded. In this project a position is an endgame when the
pieces left (not counting pawns and kings) add up to 26 points or less using knight and bishop 3, rook 5 and queen 9.
The endgame type is only recorded once the material has stayed the same for four moves, so that a position in the
middle of a trade is not misclassified.

## Endgame types
Endgames are named after the pieces left: a pawn endgame has only kings and pawns, a rook endgame one rook each, a
bishop-versus-knight endgame one bishop against one knight, and so on. This project tracks ten types.

## Converting an advantage
Converting means turning an advantage, such as an extra pawn, into a win. How easy that is depends heavily on the
endgame type. In rapid and classical games in this project, one extra pawn wins 66% of the time in pawn endgames but
only 43% with opposite-coloured bishops.

## Opposite-coloured bishops
An opposite-coloured bishop endgame has one bishop each, on squares of different colours, so the bishops can never
fight for the same squares. The defending side can blockade on squares the attacking bishop cannot reach, which makes
these endings very drawish. In this project they have the highest draw rate of any type: 46% with equal material and
40% even when one side is a pawn up (rapid and classical games).

## Rook endgames
Rook endgames are the most common type. A well-known saying claims that "all rook endings are drawn" because the
defending rook is so active. In practice, at Lichess level, one extra pawn in a rook ending wins 57% of the time and
draws only 21% (rapid and classical), so the saying does not hold for ordinary players.

## Pawn endgames
In a pawn endgame only kings and pawns remain. They are the most decisive type: one extra pawn wins 66% of the time and
two extra pawns 84% (rapid and classical), because a passed pawn is so hard to stop without pieces.

## Queen endgames
Queen endgames are hard to convert because the defending queen can give endless checks. An extra pawn wins 52% of the
time here, less than in rook endgames.

## Draw rate
The draw rate is the share of games that end in a draw. On Lichess only about 4% of all games are drawn, but endgames
with equal material are drawn far more often, from 16% to 46% depending on the type in rapid and classical games.
