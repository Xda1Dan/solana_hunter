import secrets
import math

# ------------------------------
# CONFIGURATION
# ------------------------------
START_BALANCE_SOL = 0.5       # starting balance in SOL
BASE_BET_SOL = 0.001          # starting bet
TARGET_PROFIT_SOL = 2.0       # stop when profit reaches this
DICE_SIDES = 100              # dice sides 1-100
ROLL_UNDER = True             # True = win if roll < TARGET_NUMBER
TARGET_NUMBER = 50            # number to roll under or over
MULTIPLIER = 1.98             # payout multiplier
SHOW_EVERY = 10               # show stats every N rounds
MAX_ROLLS = 100000            # safety limit

# ------------------------------
# HELPER FUNCTIONS
# ------------------------------
def crypto_roll_dice():
    """Return a crypto-random dice roll from 1 to DICE_SIDES"""
    return secrets.randbelow(DICE_SIDES) + 1

def ceil_sol(x):
    """Round up to 6 decimals (SOL precision)"""
    return math.ceil(x * 1_000_000) / 1_000_000

def check_win(roll, target, roll_under):
    """Check if dice roll wins"""
    return roll < target if roll_under else roll > target

# ------------------------------
# MARTINGALE SIMULATION
# ------------------------------
def simulate_dice_martingale():
    balance = START_BALANCE_SOL
    bet = BASE_BET_SOL
    rounds = 0
    wins = 0
    losses = 0
    biggest_bankroll = balance
    highest_ever_balance = balance
    largest_single_win = 0.0

    target_balance = START_BALANCE_SOL + TARGET_PROFIT_SOL

    print(f"Starting simulation with {balance:.6f} SOL")
    print(f"Target profit: {TARGET_PROFIT_SOL:.6f} SOL (stop at {target_balance:.6f} SOL)")
    print(f"Betting base: {BASE_BET_SOL:.6f} SOL, target: {'under' if ROLL_UNDER else 'over'} {TARGET_NUMBER}, multiplier: {MULTIPLIER}x")
    print("-----------------------------------------------------")

    while balance >= bet and rounds < MAX_ROLLS and balance < target_balance:
        rounds += 1
        roll = crypto_roll_dice()

        if check_win(roll, TARGET_NUMBER, ROLL_UNDER):
            payout = ceil_sol(bet * MULTIPLIER)
            balance = ceil_sol(balance - bet + payout)
            wins += 1
            largest_single_win = max(largest_single_win, payout - bet)
            bet = BASE_BET_SOL  # reset after win
            outcome = "WIN"
        else:
            balance = ceil_sol(balance - bet)
            losses += 1
            bet = ceil_sol(bet * 2)  # double after loss
            outcome = "LOSS"

        biggest_bankroll = max(biggest_bankroll, balance)
        highest_ever_balance = max(highest_ever_balance, balance)

        # Show output every SHOW_EVERY rounds or on final round
        if rounds % SHOW_EVERY == 0 or balance < bet or balance >= target_balance:
            print(f"Round {rounds}: {outcome}, Roll: {roll}, Balance: {balance:.6f} SOL, Next bet: {bet:.6f} SOL")

        if balance < bet or balance >= target_balance:
            break

    profit = balance - START_BALANCE_SOL

    print("\n=== SIMULATION FINISHED ===")
    print(f"Rounds played: {rounds}")
    print(f"Final balance: {balance:.6f} SOL")
    print(f"Profit: {profit:.6f} SOL")
    print(f"Wins: {wins}, Losses: {losses}")
    print(f"Biggest bankroll during session: {biggest_bankroll:.6f} SOL")
    print(f"Highest ever balance: {highest_ever_balance:.6f} SOL")
    print(f"Largest single win: {largest_single_win:.6f} SOL")
    if balance >= target_balance:
        print("✅ Target profit reached!")

# ------------------------------
# MAIN
# ------------------------------
if __name__ == "__main__":
    simulate_dice_martingale()
