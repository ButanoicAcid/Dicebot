from __future__ import annotations

import discord
import random

from resources.core.base_cog import BaseCog, UserCommandError
from resources.core.discord_formatter import DiscordFormatter

class Miscellaneous(BaseCog):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)

    topicwheel = app_commands.Group(name="topicwheel", description="Wheel of things to talk about.")

    @topicwheel.command(name="spin", description="Something new to talk about.")
    @app_commands.guild_only()
    async def topic_wheel_spin(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        topic_wheel = await self.stores.guild.get(f"#/prefs/{interaction.guild.id}/topicwheel", None)
        if topic_wheel is not None or len(topic_wheel) > 0:
            await interaction.followup.send(f"We are now going to talk about {random.choice(default_topic_wheel)}...")
        else:
            await interaction.followup.send("The topic wheel is empty. There is **nothing** for us to talk about.")

    @topicwheel.command(name="add", description="Puts a new topic on the topic wheel.")
    @app_commands.guild_only()
    async def topic_wheel_add(self, interaction: discord.Interaction, choice: str) -> None:
        await interaction.response.defer()

        topic_wheel = await self.stores.guild.setdefault(f"#/prefs/{interaction.guild.id}/topicwheel", [])
        await self.stores.guild.list_append(f"#/prefs/{interaction.guild.id}/topicwheel", choice)
        await self.stores.guild.wait_for_flush()
        await interaction.followup.send(f"Added {choice} to the topic list. We can talk about it, I guess...")



    @topicwheel.command(name="remove", description="Removes a topic from the topic wheel.")
    @app_commands.guild_only()
    async def topic_wheel_add(self, interaction: discord.Interaction, choice: str) -> None:
        await interaction.response.defer()

        topic_wheel = await self.stores.guild.setdefault(f"#/prefs/{interaction.guild.id}/topicwheel", [])
        await self.stores.guild.list_remove(f"#/prefs/{interaction.guild.id}/topicwheel", choice)
        await interaction.followup.send(f"Removed {choice} from the topic list. What, not a fan?")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Miscellaneous(bot))
