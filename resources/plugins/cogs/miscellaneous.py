from __future__ import annotations

import discord
import random

from discord import app_commands
from discord.ext import commands

from resources.core.base_cog import BaseCog, UserCommandError
from resources.core.discord_formatter import DiscordFormatter
from resources.core.dicebot_canned_responses import CannedResponses

class Miscellaneous(BaseCog):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)

    topicwheel = app_commands.Group(name="topicwheel", description="Wheel of things to talk about.")

    @topicwheel.command(name="spin", description="Something new to talk about.")
    @app_commands.guild_only()
    async def topic_wheel_spin(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        topic_wheel = await self.stores.guilds.get(f"#/prefs/{interaction.guild.id}/topicwheel", None)
        if topic_wheel:
            topic = random.choice(topic_wheel)

            if topic.lower() in ["dicebot", "dice bot"]:
                bot_comment = CannedResponses.topicwheel_selfdiscuss_response(user=interaction.user)
            else:
                bot_comment = CannedResponses.topicwheel_discuss_response(choice=topic, user=interaction.user)
        else:
            bot_comment = CannedResponses.topicwheel_empty_response(user=interaction.user)

        await interaction.followup.send(bot_comment)

    @topicwheel.command(name="add", description="Puts a new topic on the topic wheel.")
    @app_commands.guild_only()
    async def topic_wheel_add(self, interaction: discord.Interaction, choice: str) -> None:
        await interaction.response.defer()

        topic_wheel = await self.stores.guilds.setdefault(f"#/prefs/{interaction.guild.id}/topicwheel", [])
        await self.stores.guilds.list_append(f"#/prefs/{interaction.guild.id}/topicwheel", choice)
        await self.stores.guilds.wait_for_flush()

        bot_comment = CannedResponses.topic_wheel_add_response(choice=choice, user=interaction.user)
        await interaction.followup.send(bot_comment)

    @topicwheel.command(name="remove", description="Removes a topic from the topic wheel.")
    @app_commands.guild_only()
    async def topic_wheel_remove(self, interaction: discord.Interaction, choice: str) -> None:
        await interaction.response.defer()

        topic_wheel = await self.stores.guilds.setdefault(f"#/prefs/{interaction.guild.id}/topicwheel", [])
        conf = await self.stores.guilds.list_remove(f"#/prefs/{interaction.guild.id}/topicwheel", choice)
        await self.stores.guilds.wait_for_flush()

        if removed:
            bot_comment = CannedResponses.topic_wheel_remove_response(choice=choice, user=interaction.user)
            await interaction.followup.send(bot_comment)
        else:
            raise UserCommandError("That topic doesn't exist on the wheel.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Miscellaneous(bot))
