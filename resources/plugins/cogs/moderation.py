from __future__ import annotations

from datetime import UTC, datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from resources.core.base_cog import BaseCog, UserCommandError


class Moderation(BaseCog):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)

    purge = app_commands.Group(name="purge", description="Purge commands.")

    @purge.command(
        name="user",
        description="Purges by-user. Will ignore messages older than 14 days.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def purge_user(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        count: app_commands.Range[int, 1, 1000],
        reason: str | None = None,
    ) -> None:
        await interaction.response.defer()

        if not isinstance(
            interaction.channel,
            (discord.TextChannel, discord.Thread),
        ):
            raise UserCommandError(
                "This command can only be used in text channels or threads."
            )

        messages = []

        after = datetime.now(UTC) - timedelta(days=14)

        async for message in interaction.channel.history(after=after):
            if message.author == user:
                messages.append(message)

                if len(messages) >= count:
                    break

        for i in range(0, len(messages), 100):
            batch = messages[i : i + 100]
            await interaction.channel.delete_messages(
                messages=batch,
                reason=reason,
            )

        await interaction.followup.send(
            f"Deleted {len(messages)} messages.",
            ephemeral=True,
        )

    @purge.command(
        name="general",
        description="Purges generally. Will ignore messages older than 14 days.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def purge_general(
        self,
        interaction: discord.Interaction,
        count: app_commands.Range[int, 1, 1000],
        reason: str | None = None,
    ) -> None:
        await interaction.response.defer()

        if not isinstance(
            interaction.channel,
            (discord.TextChannel, discord.Thread),
        ):
            raise UserCommandError(
                "This command can only be used in text channels or threads."
            )

        messages = []

        after = datetime.now(UTC) - timedelta(days=14)

        async for message in interaction.channel.history(after=after):
            messages.append(message)

            if len(messages) >= count:
                break

        for i in range(0, len(messages), 100):
            batch = messages[i : i + 100]
            await interaction.channel.delete_messages(
                messages=batch,
                reason=reason,
            )

        await interaction.followup.send(
            f"Deleted {len(messages)} messages.",
            ephemeral=True,
        )

    @staticmethod
    def parse_timestamp(value: str) -> datetime:
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))

            if timestamp.tzinfo is None:
                raise UserCommandError("Timezone information is required.")

            return timestamp.astimezone(UTC)
        except ValueError:
            raise UserCommandError(
                "Invalid timestamp. Use ISO 8601, e.g. 2026-11-12T14:30:00Z"
            )

    @purge.command(
        name="time", description="Purges between two supplied timestamps."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        before="Timestamp to delete messages before. Use ISO 8601 incl. timezone, e.g. 2026-11-12T14:30:00Z",
        after="Timestamp to delete messages after. Use ISO 8601 incl. timezone, e.g. 2026-11-12T14:30:00Z",
    )
    @app_commands.guild_only()
    async def purge_time(
        self,
        interaction: discord.Interaction,
        before: str,
        after: str,
        reason: str | None = None,
    ) -> None:
        await interaction.response.defer()

        messages = []

        beforedt = Moderation.parse_timestamp(before)
        afterdt = Moderation.parse_timestamp(after)
        now = datetime.now(UTC)
        dtlimit = now - timedelta(days=14)

        if not isinstance(
            interaction.channel,
            (discord.TextChannel, discord.Thread),
        ):
            raise UserCommandError(
                "This command can only be used in text channels or threads."
            )

        if afterdt < dtlimit:
            raise UserCommandError(
                "Time window cannot include messages older than 14 days."
            )

        if afterdt >= beforedt:
            raise UserCommandError(
                "The 'after' timestamp must be earlier than the 'before' timestamp."
            )

        if beforedt > now or afterdt > now:
            raise UserCommandError(
                "Time window cannot include messages that have yet to be sent."
            )

        

        async for message in interaction.channel.history(
            before=beforedt, after=afterdt
        ):
            messages.append(message)

        for i in range(0, len(messages), 100):
            batch = messages[i : i + 100]
            await interaction.channel.delete_messages(
                messages=batch,
                reason=reason,
            )

        await interaction.followup.send(
            f"Deleted {len(messages)} messages.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
