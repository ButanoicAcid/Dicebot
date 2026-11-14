import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import utcnow

from resources.core.base_cog import BaseCog
from resources.core.discord_formatter import Colour, DiscordFormatter
from resources.core.dicebot_canned_responses import CannedResponses
from resources.plugins.engines.dice import DiceEngine


class Dice(BaseCog):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        self.engine = DiceEngine(gm_ids=self.consts.gm_ids)

    @app_commands.command(name="roll", description="Is luck on your side?")
    @app_commands.describe(roll="Dice expression.")
    async def roll(self, interaction: discord.Interaction, roll: str) -> None:
        await interaction.response.defer()

        result = self.engine.roll(roll, interaction.user.id)
        fields = [
            ("Roll:", result.roll_string_text, True),
            ("Modifier:", result.modifier_text, True),
            ("Total:", result.modified_total, True),
            ("Rolls:", result.rolls_text, True),
        ]

        if result.is_crit:
            fields.extend(
                [
                    ("Critical:", "**SUCCESS**", True),
                    ("\u200b", "\u200b", True),
                ]
            )

        if result.is_fumble:
            fields.extend(
                [
                    ("Critical:", "**FAILURE**", True),
                    ("\u200b", "\u200b", True),
                ]
            )

        action = "Supergamble" if result.flag == "g" else "Roll"
        author_name = f"{
            interaction.user.display_name or interaction.user.name
        }'s {action}"
        author_url = f"{interaction.user.display_avatar.url}"
        footer_text = f"User ID: {interaction.user.id}"

        if result.is_crit:
            colour = Colour.DICE_CRIT_SUCCESS
        elif result.is_fumble:
            colour = Colour.DICE_CRIT_LOSS
        else:
            ratio = int(result.modified_total) / (result.sides * result.count)
            if ratio > 0.7:
                colour = Colour.DICE_WIN
            elif ratio < 0.3:
                colour = Colour.DICE_LOSS
            else:
                colour = Colour.DICE_GENERIC

        embed = DiscordFormatter.formatter_embed(
            title=None,
            description=None,
            colour=colour,
            timestamp=utcnow(),
            fields=fields,
            author_name=author_name,
            author_icon_url=author_url,
            footer_text=footer_text,
            footer_icon_url=author_url,
        )

        await interaction.followup.send(embed=embed)

    skillcheck = app_commands.Group(
        name="skillcheck", description="Skillchecks."
    )

    @skillcheck.command(name="d20", description="Let Chaos decide your fate.")
    @app_commands.choices(
        check=[
            app_commands.Choice(name="Very Easy (DC 5)", value="5"),
            app_commands.Choice(name="Easy (DC 8)", value="8"),
            app_commands.Choice(name="Medium (DC 10)", value="10"),
            app_commands.Choice(name="Hard (DC 12)", value="12"),
            app_commands.Choice(name="Very Hard (DC 15)", value="15"),
            app_commands.Choice(name="Impossible (DC 20)", value="20"),
            app_commands.Choice(name="??? (DC 33)", value="33"),
        ]
    )
    @app_commands.choices(
        advdis=[
            app_commands.Choice(name="Advantage", value="adv"),
            app_commands.Choice(name="Disadvantage", value="dis"),
        ]
    )
    @app_commands.describe(
        check="The difficulty of the roll, and the number to beat.",
        modifier="Customisable modifier for the roll.",
        advdis="Allows you to select advantage or disadvantage for the check.",
    )
    async def d20(
        self,
        interaction: discord.Interaction,
        check: app_commands.Choice[str],
        modifier: int | None = None,
        advdis: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer()

        if modifier:
            modifier = f"{modifier:+}"

        result = self.engine.roll(
            f"d20{advdis.value if advdis else ''}{modifier if modifier else ''}",
            interaction.user.id,
        )

        success = int(result.modified_total) >= int(check.value)

        if result.is_crit:
            colour = Colour.DICE_CRIT_SUCCESS
        elif result.is_fumble:
            colour = Colour.DICE_CRIT_LOSS
        else:
            colour = Colour.DICE_WIN if success else Colour.DICE_LOSS

        author_name = f"{
            interaction.user.display_name or interaction.user.name
        }'s Skillcheck (d20)"
        author_url = f"{interaction.user.display_avatar.url}"
        footer_text = f"User ID: {interaction.user.id}"
        passfail = "Passed!" if success else "Failed!"

        fields = [
            ("Check:", f"{check.name}", True),
            ("Result:", passfail, True),
            ("\u200b", "\u200b", True),
            ("Rolls:", result.rolls_text, True),
            ("Total:", result.modified_total, True),
            ("\u200b", "\u200b", True),
            ("Modifier:", result.modifier_text, True),
        ]

        if result.is_crit and success:
            fields.append(("Critical:", "**SUCCESS**", True))
        if result.is_fumble:
            fields.append(("Critical:", "**FAILURE**", True))

        embed = DiscordFormatter.formatter_embed(
            title=None,
            description=None,
            colour=colour,
            timestamp=utcnow(),
            fields=fields,
            author_name=author_name,
            author_icon_url=author_url,
            footer_text=footer_text,
            footer_icon_url=author_url,
        )

        await interaction.followup.send(embed=embed)

    @skillcheck.command(name="d100", description="Let Chaos decide your fate.")
    @app_commands.choices(
        check=[
            app_commands.Choice(name="Very Easy (DC 10)", value="10"),
            app_commands.Choice(name="Easy (DC 25)", value="25"),
            app_commands.Choice(name="Medium (DC 50)", value="50"),
            app_commands.Choice(name="Hard (DC 75)", value="75"),
            app_commands.Choice(name="Very Hard (DC 90)", value="90"),
            app_commands.Choice(name="Impossible (DC 100)", value="100"),
        ]
    )
    @app_commands.choices(
        advdis=[
            app_commands.Choice(name="Advantage", value="adv"),
            app_commands.Choice(name="Disadvantage", value="dis"),
        ]
    )
    @app_commands.describe(
        check="The difficulty of the roll, and the number to beat.",
        modifier="Customisable modifier for the roll.",
        advdis="Allows you to select advantage or disadvantage for the check.",
    )
    async def d100(
        self,
        interaction: discord.Interaction,
        check: app_commands.Choice[str],
        modifier: int | None = None,
        advdis: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer()

        if modifier:
            modifier = f"{modifier:+}"

        result = self.engine.roll(
            f"d100{advdis.value if advdis else ''}{modifier if modifier else ''}",
            interaction.user.id,
        )

        success = int(result.modified_total) >= int(check.value)

        if result.is_crit:
            colour = Colour.DICE_CRIT_SUCCESS
        elif result.is_fumble:
            colour = Colour.DICE_CRIT_LOSS
        else:
            colour = Colour.DICE_WIN if success else Colour.DICE_LOSS

        author_name = f"{
            interaction.user.display_name or interaction.user.name
        }'s Skillcheck (d100)"
        author_url = f"{interaction.user.display_avatar.url}"
        footer_text = f"User ID: {interaction.user.id}"
        passfail = "Passed!" if success else "Failed!"

        fields = [
            ("Check:", f"{check.name}", True),
            ("Result:", passfail, True),
            ("\u200b", "\u200b", True),
            ("Rolls:", result.rolls_text, True),
            ("Total:", result.modified_total, True),
            ("\u200b", "\u200b", True),
            ("Modifier:", result.modifier_text, True),
        ]

        if result.is_crit and success:
            fields.append(("Critical:", "**SUCCESS**", True))
        if result.is_fumble:
            fields.append(("Critical:", "**FAILURE**", True))

        embed = DiscordFormatter.formatter_embed(
            title=None,
            description=None,
            colour=colour,
            timestamp=utcnow(),
            fields=fields,
            author_name=author_name,
            author_icon_url=author_url,
            footer_text=footer_text,
            footer_icon_url=author_url,
        )

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="coinflip", description="A toss of the coin.")
    @app_commands.describe(count="Number of coins to flip.")
    async def coinflip(
        self, interaction: discord.Interaction, count: int
    ) -> None:
        await interaction.response.defer()

        results = self.engine.coinflip(count)

        if len(results) == 1:
            output = f"{results[0]}..."
        else:
            heads = 0
            tails = 0
            for result in results:
                if result == "Heads":
                    heads += 1
                else:
                    tails += 1
            output = CannedResponses.coinflip_responses(heads=heads, tails=tails, user=interaction.user)

        await interaction.followup.send(output)

    @app_commands.command(
        name="eightball",
        description="Nought but vague and usually unhelpful wisdoms.",
    )
    async def eightball(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        result = self.engine.eightball()
        await interaction.followup.send(result)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Dice(bot))
