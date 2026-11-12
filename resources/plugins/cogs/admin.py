from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import NoReturn

import discord
from discord.ext import commands

from resources.core.base_cog import BaseCog, UserCommandError


class Administration(BaseCog):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)

    @commands.command()
    @BaseCog.is_authorised_ctx()
    async def ping(self, ctx: commands.Context) -> None:
        await ctx.send(
            f"Pong! Bot latency: {round(self.bot.latency, 1)} seconds."
        )

    @commands.command(name="sync")
    @BaseCog.is_authorised_ctx()
    async def sync(self, ctx: commands.Context) -> None:
        synced = await self.bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} commands globally.")
        synced = await self.bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"Synced {len(synced)} commands locally.")

    @commands.command(name="resetcommands")
    @BaseCog.is_authorised_ctx()
    async def resetcommands(self, ctx: commands.Context) -> None:
        for guild_id in self.consts.guilds_to_sync:
            try:
                guild = discord.Object(id=guild_id)

                self.bot.tree.clear_commands(guild=guild)
                await self.bot.tree.sync(guild=guild)

                self.logger.info(f"Reset guild commands: {guild_id}")
                await ctx.send(f"Reset guild commands in guild id: {guild_id}")
            except discord.Forbidden:
                self.logger.info(
                    f"Unable to reset commands in guild id: {guild_id}, no access."
                )
                await ctx.send(
                    f"Unable to reset commands in guild id: {guild_id}, no access."
                )

    @commands.command()
    @commands.is_owner()
    async def listcogs(self, ctx: commands.Context) -> None:
        cogs = list(self.bot.cogs.keys())
        if cogs:
            await ctx.send(f"Loaded cogs: {', '.join(cogs)}.")
        else:
            await ctx.send("No cogs found.")

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, cog: str) -> None:
        try:
            self.logger.info(
                f"Reloading cog: {self.services.paths.plugin_module}.{cog}."
            )
            await self.bot.reload_extension(
                f"{self.services.paths.plugin_module}.{cog}"
            )
            await ctx.send(
                f"Reloaded {self.services.paths.plugin_module}.{cog}"
            )
            self.logger.info(
                f"Reloaded cog {self.services.paths.plugin_module}.{cog}."
            )
        except commands.ExtensionNotFound:
            raise UserCommandError(
                "Error: Extension is either missing or does not exist."
            )
        except commands.ExtensionNotLoaded:
            raise UserCommandError("Error: Extension is not loaded.")

    @commands.command()
    @commands.is_owner()
    async def unload(self, ctx: commands.Context, cog: str) -> None:
        try:
            self.logger.info(
                f"Unloading cog: {self.services.paths.plugin_module}.{cog}."
            )
            await self.bot.unload_extension(
                f"{self.services.paths.plugin_module}.{cog}"
            )
            self.logger.info(
                f"Unloaded cog {self.services.paths.plugin_module}.{cog}."
            )
            await ctx.send(
                f"Unloaded {self.services.paths.plugin_module}.{cog}"
            )
        except commands.ExtensionNotFound:
            raise UserCommandError(
                "Error: Extension is either missing or does not exist."
            )
        except commands.ExtensionNotLoaded:
            raise UserCommandError("Error: Extension is not loaded.")

    @commands.command()
    @commands.is_owner()
    async def load(self, ctx: commands.Context, cog: str) -> None:
        try:
            self.logger.info(
                f"Loading cog: {self.services.paths.plugin_module}.{cog}."
            )
            await self.bot.load_extension(
                f"{self.services.paths.plugin_module}.{cog}"
            )
            await ctx.send(f"Loaded {self.services.paths.plugin_module}.{cog}")
            self.logger.info(
                f"Loaded cog {self.services.paths.plugin_module}.{cog}."
            )
        except commands.ExtensionNotFound:
            raise UserCommandError(
                "Error: Extension is either missing or does not exist."
            )
        except commands.ExtensionAlreadyLoaded:
            raise UserCommandError("Error: Extension is already loaded.")

    @commands.command()
    @BaseCog.is_authorised_ctx()
    async def restart(
        self, ctx: commands.Context, *, reason: str = "No reason provided."
    ) -> NoReturn | None:
        await ctx.send(
            "Fine, but it's not like I *want* to restart or anything..."
        )
        await self.bot.restart(
            reason=reason, requested_by=ctx.author, module=type(self).__name__
        )

    @commands.command()
    @BaseCog.is_authorised_ctx()
    async def updaterestart(
        self, ctx: commands.Context, *, reason: str = "No reason provided."
    ) -> NoReturn | None:
        await ctx.send("Really? Do I **have** to...")
        await self.bot.update_restart(
            reason=reason, requested_by=ctx.author, module=type(self).__name__
        )

    @commands.command()
    @commands.is_owner()
    async def shutdown(
        self, ctx: commands.Context, *, reason: str = "No reason provided."
    ) -> NoReturn | None:
        await ctx.send("Do you *really* want me to go? Fine then..")
        await self.bot.shutdown(
            reason=reason, requested_by=ctx.author, module=type(self).__name__
        )

    def _parse_time_range(self, range_str: str) -> datetime:
        now = datetime.now()

        match = re.fullmatch(r"-([1-9]\d*)([mhd])", range_str.lower())

        if not match:
            raise UserCommandError(
                "Invalid time range. Use a positive integer followed by m, h, or d."
            )

        amount = int(match.group(1))
        unit = match.group(2)

        if unit == "m":
            return now - timedelta(minutes=amount)
        elif unit == "h":
            return now - timedelta(hours=amount)
        elif unit == "d":
            return now - timedelta(days=amount)

    def _filter_log(
        self, log_path: str, since: datetime
    ) -> tuple[int, str | None]:
        temp_file = tempfile.NamedTemporaryFile(
            delete=False, mode="w", encoding="utf-8", suffix=".log"
        )
        found = False

        try:
            with open(log_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        ts_str = line.split("]")[0][1:]
                        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        continue
                    if ts >= since:
                        temp_file.write(line)
                        found = True

        except FileNotFoundError:
            Path(temp_file.name).unlink()
            raise

        finally:
            temp_file.close()

        if found:
            return 0, temp_file.name
        else:
            Path(temp_file.name).unlink()
            return 1, None

    @commands.command()
    @commands.is_owner()
    async def getlog(
        self, ctx: commands.Context, log_name: str, since_str: str
    ) -> None:
        log_path = Path(self.services.paths.logs / f"{log_name}.log")

        try:
            since = self._parse_time_range(since_str)
            status, file_path = self._filter_log(log_path, since)
        except FileNotFoundError:
            raise UserCommandError(
                "Error: File not found. Expected name format: bot-sessionid."
            )

        if status == 1:
            await ctx.send(
                f"No log entries found in {log_name} within the specified time range."
            )
            return

        try:
            file_size = os.path.getsize(file_path)
            if file_size > 8 * 1024 * 1024:  # 8MB
                raise UserCommandError(
                    "Error: Log file is too large to send. Try a shorter timeframe."
                )
            else:
                await ctx.send(
                    f"Sending {file_size // 1024} KB of {log_name} log...",
                    file=discord.File(file_path),
                )
        except (OSError, discord.HTTPException):
            raise UserCommandError(
                "Error: Failed to send the log file. It may be too large or inaccessible."
            )
        finally:
            if file_path and Path(file_path).exists():
                Path(file_path).unlink()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Administration(bot))
