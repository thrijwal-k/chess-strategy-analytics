# Chess basics

## The board and the goal
Chess is played by two players, White and Black, on a board of 64 squares arranged in 8 rows (ranks, numbered 1 to 8)
and 8 columns (files, lettered a to h). Each player starts with 16 pieces. White always moves first, then the players
take turns. The goal is to checkmate the opponent's king: to attack it so that it cannot escape.

## The pieces and how they move
- King: one square in any direction. It must never be left under attack.
- Queen: any number of squares in a straight line, along ranks, files or diagonals. The most powerful piece.
- Rook: any number of squares along a rank or file.
- Bishop: any number of squares diagonally, so it always stays on squares of one colour.
- Knight: jumps in an L shape (two squares one way, one square sideways) and is the only piece that can jump over others.
- Pawn: moves forward one square (two on its first move) and captures one square diagonally forward. A pawn that
  reaches the last rank is promoted, usually to a queen.

## Piece values and material
Players count material with rough values: pawn 1, knight 3, bishop 3, rook 5, queen 9. The king has no value because
it can never be captured. Being "up material" means having more points of pieces than the opponent. In this project a
material difference is always White's total minus Black's total.

## Check, checkmate and resigning
A king that is attacked is in check, and the player must deal with it at once. Checkmate is a check that cannot be
escaped, and it ends the game. Most online games end before checkmate: a player resigns when the position is lost, or
loses because their clock runs out.

## How a game can be drawn
A draw (a tie, worth half a point to each player) happens by agreement, by stalemate (the player to move has no legal
move but is not in check), by threefold repetition of the same position, by the 50-move rule, by insufficient material
to checkmate, or when one player runs out of time but the opponent has no way to checkmate.

## Castling
Castling is a special move in which the king moves two squares towards a rook and the rook jumps to the other side of
it. It is the only move where two pieces move at once. Players usually castle early to tuck the king behind pawns and
bring the rook towards the centre. Kingside castling goes towards the h-file rook, queenside towards the a-file rook.

## Phases of the game
A game has three rough phases. The opening is the first 10 to 15 moves, when players develop their pieces and fight
for the centre. The middlegame is the main battle with most pieces still on the board. The endgame starts once many
pieces have been traded and the kings become active. This project studies all three.

## Scores and results
A win counts 1 point, a draw half a point and a loss 0. A player's score is their points divided by the number of
games, so scoring 52% means 0.52 points per game. In this project White's score is measured from White's point of
view: 1 for a White win, 0.5 for a draw, 0 for a Black win.

## Ratings
Every Lichess player has a rating that goes up when they win and down when they lose. A beginner is often around 1000
to 1200, a solid club player around 1600 to 1800 and a strong player 2200 or more. The difference between two
players' ratings predicts the result: the larger the gap, the more likely the higher-rated player wins. Lichess uses
the Glicko-2 rating system, a refinement of the Elo system.

## Time controls
Online games are played with a clock, and the time control sets the speed of the game. Bullet chess is the fastest:
under 3 minutes per player. Blitz chess is 3 to 8 minutes, rapid chess 8 to 25 minutes and classical chess longer. A time control such as 180+2 means 180 seconds each plus 2 seconds added after every
move. A player whose clock reaches zero loses, unless the opponent cannot possibly checkmate, in which case it is a
draw.

## Chess notation
Moves are written in algebraic notation: the piece letter (K king, Q queen, R rook, B bishop, N knight, nothing for a
pawn) followed by the square it moves to. "Nf3" means a knight moves to f3, "e4" means a pawn moves to e4, "x" marks a
capture, "+" a check and "O-O" castling. "1.d4 d5 2.c4" means White played d4, Black d5, then White c4.

## Lichess
Lichess is a free, open-source chess website. It publishes every rated game played on it, which is where this
project's data comes from.
