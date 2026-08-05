from __future__ import annotations
import discord
from discord.ext import commands
import discord.app_commands
from typing import Optional, Tuple
import random
import datetime
import asyncio
import db
import modlog as modlog_helper  # optional logging to mod-log

# Config
MIN_BET = 1
CONFIRM_THRESHOLD = 1000         # bets >= this require button confirmation
JACKPOT_PERCENT = 0.01           # 1% of each bet goes to jackpot (rounded down)
JACKPOT_TRIGGER_SYMBOL = "7️⃣"   # slots jackpot symbol
GAME_COOLDOWNS = {
    "coinflip": 5,   # seconds
    "slots": 10,
    "roulette": 10,
    "dice": 5,
}
# multipliers
COINFLIP_MULTIPLIER = 2
SLOTS_PAYOUTS = {"jackpot": 15, "three": 5, "two": 2}
ROULETTE_COLOR_MULTIPLIER = 2
ROULETTE_NUMBER_MULTIPLIER = 36
DICE_MULTIPLIER = 6


# Confirmation UI
class ConfirmBetView(discord.ui.View):
    def __init__(self, user_id: int, timeout: int = 20):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.result: Optional[bool] = None
        self.event = asyncio.Event()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the betting user can confirm/cancel.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        await interaction.response.edit_message(content="Bet confirmed.", view=None)
        self.event.set()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        await interaction.response.edit_message(content="Bet cancelled.", view=None)
        self.event.set()


class MiniGames(commands.Cog):
    """Gambling mini-games with jackpot & persistent cooldowns."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Helpers
    async def _check_and_take_jackpot_share(self, guild_id: int, amount: int):
        """Take a percent of bet and add to jackpot (integer)."""
        share = int(amount * JACKPOT_PERCENT)
        if share <= 0:
            return 0
        new_amt = await db.add_to_jackpot(guild_id, share)
        return share

    async def _check_cooldown(self, guild_id: int, user_id: int, game: str) -> Tuple[bool, Optional[int]]:
        cd = GAME_COOLDOWNS.get(game, 0)
        allowed, rem = await db.can_use_game(guild_id, user_id, game, cd)
        return allowed, rem

    async def _set_cooldown(self, guild_id: int, user_id: int, game: str):
        await db.set_game_cooldown(guild_id, user_id, game, datetime.datetime.utcnow())

    async def _require_confirmation(self, ctx_or_interaction, user_id: int, amount: int) -> bool:
        """If amount >= CONFIRM_THRESHOLD, require button confirmation. Accepts Context or Interaction."""
        if amount < CONFIRM_THRESHOLD:
            return True
        view = ConfirmBetView(user_id)
        if isinstance(ctx_or_interaction, commands.Context):
            msg = await ctx_or_interaction.send(f"This is a large bet ({amount:,}). Confirm?", view=view)
        else:
            await ctx_or_interaction.response.send_message(f"This is a large bet ({amount:,}). Confirm?", view=view, ephemeral=True)
            # get the original response to edit if needed
            msg = await ctx_or_interaction.original_response()

        try:
            await asyncio.wait_for(view.event.wait(), timeout=view.timeout)
        except asyncio.TimeoutError:
            # timed out
            try:
                await msg.edit(content="Bet timed out (no confirmation).", view=None)
            except Exception:
                pass
            return False
        return bool(view.result)

    # Generic bet flow
    async def _perform_bet(self, ctx_or_interaction, user, guild, game_name: str, amount: int, bet_callable):
        """
        bet_callable: async function to run the bet logic after balance deduction:
            async def bet_callable():
                # returns tuple (result_message:str, payout:int, extra_embed_data:Optional[dict])
        """
        allowed, rem = await self._check_cooldown(guild.id, user.id, game_name)
        if not allowed:
            msg = f"Cooldown active. Try again in {rem}s."
            if isinstance(ctx_or_interaction, commands.Context):
                await ctx_or_interaction.send(msg)
            else:
                await ctx_or_interaction.response.send_message(msg, ephemeral=True)
            return

        # confirmation UI for large bets
        confirmed = await self._require_confirmation(ctx_or_interaction, user.id, amount)
        if not confirmed:
            return

        # check balance
        bal = await db.get_balance(guild.id, user.id)
        if bal < amount:
            msg = "Insufficient balance."
            if isinstance(ctx_or_interaction, commands.Context):
                await ctx_or_interaction.send(msg)
            else:
                await ctx_or_interaction.followup.send(msg, ephemeral=True)
            return

        # take jackpot share
        share = await self._check_and_take_jackpot_share(guild.id, amount)

        # deduct stake
        await db.add_balance(guild.id, user.id, -int(amount))

        # run bet logic
        try:
            result_msg, payout, modlog_extra = await bet_callable()
        except Exception as e:
            # refund stake & jackpot share if bet callable crashed
            await db.add_balance(guild.id, user.id, amount + share)
            if isinstance(ctx_or_interaction, commands.Context):
                await ctx_or_interaction.send(f"Error during game: {e} (refunded).")
            else:
                await ctx_or_interaction.followup.send(f"Error during game: {e} (refunded).", ephemeral=True)
            return

        # apply payout (could be 0)
        if payout and payout > 0:
            await db.add_balance(guild.id, user.id, int(payout))

        # set cooldown
        await self._set_cooldown(guild.id, user.id, game_name)

        # send result
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(result_msg)
        else:
            await ctx_or_interaction.followup.send(result_msg)

        # Log big wins / jackpot to mod-log if configured
        try:
            if payout and payout >= 1000:
                await modlog_helper.send_modlog(self.bot, guild, "Big Win", user, None, reason=None, extra=f"{game_name} payout {payout:,}")
            # if modlog extra provided, send as well
            if modlog_extra:
                await modlog_helper.send_modlog(self.bot, guild, f"{game_name.capitalize()} Event", user, None, reason=None, extra=modlog_extra)
        except Exception:
            pass

    # -------------------------
    # Games: prefix versions
    # -------------------------
    @commands.command(name="coinflip")
    async def coinflip(self, ctx: commands.Context, amount: int, choice: str):
        guild = ctx.guild
        choice = (choice or "").lower()
        if choice not in ("heads", "tails"):
            await ctx.send("Choose 'heads' or 'tails'.")
            return

        async def run():
            # flip
            result = random.choice(["heads", "tails"])
            if result == choice:
                winnings = amount * COINFLIP_MULTIPLIER
                return f"🎉 It was {result}. You won {winnings:,}!", winnings, None
            return f"😢 It was {result}. You lost {amount:,}.", 0, None

        await self._perform_bet(ctx, ctx.author, guild, "coinflip", amount, run)

    @commands.command(name="slots")
    async def slots(self, ctx: commands.Context, amount: int):
        guild = ctx.guild

        async def run():
            symbols = ["🍒", "🍋", "🍊", "🍇", "⭐", JACKPOT_TRIGGER_SYMBOL]
            reels = [random.choice(symbols) for _ in range(3)]
            # default no win
            payout = 0
            outcome = "No win."
            if reels.count(JACKPOT_TRIGGER_SYMBOL) == 3:
                # jackpot: player gets slot jackpot payout + full jackpot pool
                payout = amount * SLOTS_PAYOUTS["jackpot"]
                jackpot_amount = await db.get_jackpot(guild.id)
                if jackpot_amount > 0:
                    claimed = await db.claim_jackpot(guild.id)
                    payout += claimed
                    extra = f"Jackpot hit! Claimed jackpot {claimed:,}."
                else:
                    extra = "Jackpot triggered but pool was 0."
                outcome = f"JACKPOT! {' '.join(reels)}"
                return f"{outcome} You won {payout:,}!", payout, extra
            if reels[0] == reels[1] == reels[2]:
                payout = amount * SLOTS_PAYOUTS["three"]
                outcome = f"Three of a kind! {' '.join(reels)}"
                return f"{outcome} You won {payout:,}!", payout, None
            if any(reels.count(s) == 2 for s in symbols):
                payout = amount * SLOTS_PAYOUTS["two"]
                outcome = f"Two of a kind! {' '.join(reels)}"
                return f"{outcome} You won {payout:,}!", payout, None
            return f"{' '.join(reels)} — {outcome} You lost {amount:,}.", 0, None

        await self._perform_bet(ctx, ctx.author, guild, "slots", amount, run)

    @commands.command(name="roulette")
    async def roulette(self, ctx: commands.Context, amount: int, bet_type: str, bet_value: Optional[str] = None):
        guild = ctx.guild
        bet_type = bet_type.lower()
        if bet_type not in ("color", "number"):
            await ctx.send("Bet type must be 'color' or 'number'.")
            return
        if bet_type == "color":
            if (bet_value or "").lower() not in ("red", "black"):
                await ctx.send("Color must be 'red' or 'black'.")
                return
        else:
            try:
                num = int(bet_value)
                if not (0 <= num <= 36):
                    raise ValueError()
            except Exception:
                await ctx.send("Number must be between 0 and 36.")
                return

        async def run():
            spin = random.choice(list(range(0, 37)))
            reds = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
            color = "green" if spin == 0 else ("red" if spin in reds else "black")
            if bet_type == "color":
                if color == bet_value.lower():
                    payout = amount * ROULETTE_COLOR_MULTIPLIER
                    return f"🎡 The wheel landed on {spin} ({color}). You won {payout:,}!", payout, None
                return f"🎡 The wheel landed on {spin} ({color}). You lost {amount:,}.", 0, None
            else:
                if spin == num:
                    payout = amount * ROULETTE_NUMBER_MULTIPLIER
                    return f"🎡 The wheel landed on {spin}. Exact hit! You won {payout:,}!", payout, None
                return f"🎡 The wheel landed on {spin}. You lost {amount:,}.", 0, None

        await self._perform_bet(ctx, ctx.author, guild, "roulette", amount, run)

    @commands.command(name="dice")
    async def dice(self, ctx: commands.Context, amount: int, guess: int):
        guild = ctx.guild
        if not (1 <= guess <= 6):
            await ctx.send("Guess must be between 1 and 6.")
            return

        async def run():
            roll = random.randint(1, 6)
            if roll == guess:
                payout = amount * DICE_MULTIPLIER
                return f"🎲 It rolled {roll}. Exact match! You won {payout:,}!", payout, None
            return f"🎲 It rolled {roll}. You lost {amount:,}.", 0, None

        await self._perform_bet(ctx, ctx.author, guild, "dice", amount, run)

    # -------------------------
    # Slash command versions (use persistent cooldowns & confirmation UI)
    # -------------------------
    @discord.app_commands.command(name="coinflip", description="Coinflip: bet on heads or tails")
    async def coinflip_slash(self, interaction: discord.Interaction, amount: int, choice: str):
        await interaction.response.defer()
        await self.coinflip.__call__(interaction, amount, choice)  # reuse prefix logic by calling underlying command

    @discord.app_commands.command(name="slots", description="Play slots")
    async def slots_slash(self, interaction: discord.Interaction, amount: int):
        await interaction.response.defer()
        await self.slots.__call__(interaction, amount)

    @discord.app_commands.command(name="roulette", description="Roulette: bet on color or number")
    async def roulette_slash(self, interaction: discord.Interaction, amount: int, bet_type: str, bet_value: Optional[int] = None, color: Optional[str] = None):
        await interaction.response.defer()
        # adapt inputs: if bet_type == 'color', expect color string; if 'number' expect bet_value
        if bet_type == "color":
            val = color
        else:
            val = str(bet_value)
        await self.roulette.__call__(interaction, amount, bet_type, val)

    @discord.app_commands.command(name="dice", description="Dice: guess a number 1-6")
    async def dice_slash(self, interaction: discord.Interaction, amount: int, guess: int):
        await interaction.response.defer()
        await self.dice.__call__(interaction, amount, guess)


async def setup(bot: commands.Bot):
    await bot.add_cog(MiniGames(bot))