from __future__ import annotations

import logging
import uuid
import discord
import random 

from textwrap import dedent
from discord import app_commands
from discord.ext import commands

from resources.core.dicebot_canned_responses import CannedResponses

class UserCommandError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class BaseCog(commands.Cog):
    bot: commands.Bot

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def services(self):
        return self.bot.services

    @property
    def logger(self) -> logging.Logger:
        return self.services.logger

    @property
    def paths(self):
        return self.services.paths

    @property
    def stores(self):
        return self.services.stores

    @property
    def users(self):
        return self.stores.users

    @property
    def guilds(self):
        return self.stores.guilds

    @property
    def config(self):
        return self.stores.config

    @property
    def consts(self):
        return self.services.consts

    @staticmethod
    def new_uuid() -> str:
        return uuid.uuid4().hex[:8].upper()

    def _log_unhandled_exception(
        self,
        cog: str,
        command: str,
        user,
        guild,
        channel,
        session: str,
        error: Exception,
    ) -> str:

        original = getattr(error, "original", error)

        error_id = BaseCog.new_uuid()

        self.logger.exception(
            dedent(f"""
        Unhandled command exception

        Error ID : {error_id}
        Cog      : {cog}
        Command  : {command}
        User     : {user}
        Guild    : {guild}
        Channel  : {channel}
        Session  : {session}
        """),
            exc_info=original,
        )

        return error_id

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:

        original = getattr(error, "original", error)

        if isinstance(original, app_commands.MissingPermissions):
            message = CannedResponses.no_perms_response(user=interaction.user)
        elif isinstance(
            original, (commands.NotOwner, app_commands.CheckFailure)
        ):
            message = CannedResponses.no_perms_response(user=interaction.user)
        elif isinstance(
            original, (app_commands.BotMissingPermissions, discord.Forbidden)
        ):
            message = CannedResponses.bot_no_perms_response(user=interaction.user)
        elif isinstance(original, UserCommandError):
            message = CannedResponses.user_command_error_response(error=str(original), user=interaction.user)
        else:
            command = (
                interaction.command.qualified_name
                if interaction.command is not None
                else "Unknown"
            )
            cog = type(self).__name__
            session = self.consts.bot_session_id

            error_id = self._log_unhandled_exception(
                cog=cog,
                command=command,
                user=interaction.user,
                guild=interaction.guild,
                channel=interaction.channel,
                session=session,
                error=original,
            )

            message = CannedResponses.generic_error_response(user=interaction.user, id=error_id)

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def cog_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:

        original = getattr(error, "original", error)

        if isinstance(original, (commands.MissingPermissions)):
            message = CannedResponses.no_perms_response(user=ctx.author)
        elif isinstance(original, (commands.NotOwner, commands.CheckFailure)):
            message = CannedResponses.no_perms_response(user=ctx.author)
        elif isinstance(
            original, (commands.BotMissingPermissions, discord.Forbidden)
        ):
            message = CannedResponses.bot_no_perms_response(user=ctx.author)
        elif isinstance(original, UserCommandError):
            message = CannedResponses.user_command_error_response(error=str(original), user=ctx.author)
        else:
            command = (
                ctx.command.qualified_name
                if ctx.command is not None
                else "Unknown"
            )
            cog = type(self).__name__
            session = self.consts.bot_session_id

            error_id = self._log_unhandled_exception(
                cog=cog,
                command=command,
                user=ctx.author,
                guild=ctx.guild,
                channel=ctx.channel,
                session=session,
                error=original,
            )

            message = CannedResponses.generic_error_response(user=ctx.author, id=error_id)

        await ctx.send(message)

    def is_authorised():
        async def predicate(interaction: discord.Interaction) -> bool:
            if interaction.user.id not in interaction.client.consts.gm_ids:
                raise app_commands.CheckFailure(
                    "You are not authorised to use this command."
                )
            return True

        return app_commands.check(predicate)

    def is_authorised_ctx():
        async def predicate(ctx: commands.Context) -> bool:
            if ctx.author.id not in ctx.bot.consts.gm_ids:
                raise commands.CheckFailure(
                    "You are not authorised to use this command."
                )
            return True

        return commands.check(predicate)

    async def retrieve_channel(
        self, id
    ) -> (
        discord.abc.GuildChannel
        | discord.abc.PrivateChannel
        | discord.Thread
        | None
    ):
        try:
            channel = self.bot.get_channel(id)
            if channel is None:
                channel = await self.bot.fetch_channel(id)
            if not isinstance(
                channel,
                (
                    discord.abc.GuildChannel,
                    discord.abc.PrivateChannel,
                    discord.Thread,
                ),
            ):
                raise ValueError(
                    "Provided ID does not point to a valid discord channel."
                )
            return channel
        except Exception as e:
            self.logger.error(f"Failed to retrieve channel {id}: {e}")
            raise

    async def send_message(
        self,
        channelid: int,
        content: str | None = None,
        embed: discord.Embed | None = None,
    ) -> None:
        channel = await self.retrieve_channel(id=channelid)

        if channel is None:
            raise RuntimeError(f"Unable to find channel {channelid}")

        return await channel.send(content=content, embed=embed)
