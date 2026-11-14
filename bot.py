from __future__ import annotations

import asyncio
import logging
import os
import platform
import signal
import sys
import traceback
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from textwrap import dedent
from typing import NoReturn

import discord
from discord.ext import commands
from dotenv import load_dotenv

from resources.core.file_utils import JsonStore
from resources.core.log_pruner import prune_directory
from resources.core.logging_utils import get_logger

# Requires: Python 3.12+
# Deployment target: Ubuntu Server Linux.
# NOTE: SystemD Unit File **MUST** contain:
# RestartForceExitStatus=10
# User=dicebot
# Group=dicebotgroup
# WorkingDirectory=projectroot
# ExecStart=projectroot/python/bin/python projectroot/bot.py
# Restart=on-failure
# RestartSec=5
# RestartForceExitStatus=10


@dataclass(frozen=True, slots=True)
class Paths:
    root: Path

    resources: Path

    stores: Path
    logs: Path

    plugin_cogs: Path
    plugin_engines: Path
    plugin_module: str

    config: Path
    guilds: Path
    users: Path

    venv_path: Path

    @classmethod
    def from_root(cls, root: str | Path) -> Paths:
        root = Path(root).resolve()

        resources = root / "resources"

        stores = root / "stores"
        logs = root / "logs"

        return cls(
            root=root,
            resources=resources,
            stores=stores,
            logs=logs,
            plugin_cogs=resources / "plugins" / "cogs",
            plugin_engines=resources / "plugins" / "engines",
            plugin_module="resources.plugins.cogs",
            config=stores / "config.json",
            guilds=stores / "guilds.json",
            users=stores / "users.json",
            venv_path=root / "python",
        )

    def ensure_directories(self) -> None:
        paths = [
            self.resources,
            self.stores,
            self.logs,
            self.plugin_cogs,
            self.plugin_engines,
            self.venv_path,
        ]
        for path in paths:
            path.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class Stores:
    config: JsonStore
    guilds: JsonStore
    users: JsonStore

    async def close(self) -> None:
        errors = []

        for store in (self.config, self.guilds, self.users):
            try:
                await store.close()
            except Exception as e:
                errors.append(e)

        if errors:
            raise ExceptionGroup("Failed to close stores", errors)


@dataclass(slots=True)
class Consts:
    bot_session_id: str
    gm_ids: list[int]
    git_url: str
    guilds_to_sync: list[int]
    system_notifs_channel: int


@dataclass(slots=True)
class Services:
    consts: Consts
    logger: logging.Logger
    stores: Stores
    paths: Paths

    async def close(self) -> None:
        errors = []

        try:
            await self.stores.close()
        except Exception as e:
            errors.append(e)

        for handler in self.logger.handlers[:]:
            try:
                handler.close()
            except Exception as e:
                errors.append(e)
            finally:
                self.logger.removeHandler(handler)

        if errors:
            raise ExceptionGroup("Error during Services closure:", errors)


@dataclass(slots=True)
class CogLoadResult:
    package: str
    loaded: list[str]
    failed: list[CogLoadFailure]
    optional_failed: list[CogLoadFailure]

    @property
    def successful(self) -> bool:
        return not self.failed


@dataclass(slots=True)
class CogLoadFailure:
    extension: str
    traceback: str


class StartupError(RuntimeError):
    def __init__(self, result: CogLoadResult):
        self.result = result

        message = [
            f"{len(result.failed)} extension(s) failed to load from {result.package}:"
        ]

        for failure in result.failed:
            message.append("")
            message.append(f"[{failure.extension}]")
            message.append(failure.traceback)

        super().__init__("\n".join(message))


def load_token() -> str:
    load_dotenv()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not defined.")

    return token


def create_services() -> Services:

    paths = Paths.from_root(Path.cwd())
    paths.ensure_directories()

    consts = Consts(
        bot_session_id=uuid.uuid4().hex[:8].upper(),
        gm_ids=[1255574033043554488, 736542444916703234, 1136671239138721893],
        git_url="fih",
        guilds_to_sync=[1460787698477301761, 1408767661214666896],
        system_notifs_channel=1568196139402928198,
    )

    logger = get_logger(
        name="CDBOT",
        sessionid=consts.bot_session_id,
        filename=f"bot-{consts.bot_session_id}",
        directory=paths.logs,
        level="INFO",
    )

    stores = Stores(
        config=JsonStore(paths.config, logger=logger),
        guilds=JsonStore(paths.guilds, logger=logger),
        users=JsonStore(paths.users, logger=logger),
    )

    return Services(consts=consts, logger=logger, stores=stores, paths=paths)


OPTIONAL_PLUGINS = ["dice", "calendar"]

PLUGINS_LIST = [
    "resources.plugins.cogs.admin",
    "resources.plugins.cogs.dice",
    "resources.plugins.cogs.calendar",
    "resources.plugins.cogs.moderation",
    "resources.plugins.cogs.miscellaneous"
]


async def load_cogs(
    bot: commands.Bot, path: Path, package: str
) -> CogLoadResult:

    logger = bot.services.logger

    result = CogLoadResult(
        package=package, loaded=[], failed=[], optional_failed=[]
    )

    if not os.path.isdir(path):
        raise FileNotFoundError(
            f"Module {package} directory ({path}) is not present."
        )

    for file in sorted(path.iterdir()):
        if (
            not file.is_file()
            or file.suffix != ".py"
            or file.stem.startswith("_")
        ):
            continue

        extension = f"{package}.{file.stem}"

        try:
            logger.info(f"Loading {extension}")
            await bot.load_extension(extension)
        except Exception:
            failure = CogLoadFailure(
                extension=f"{extension}", traceback=traceback.format_exc()
            )
            if file.stem in OPTIONAL_PLUGINS:
                logger.warning(
                    f"Failed to load optional extension {extension}"
                )
                result.optional_failed.append(failure)
            else:
                logger.error(f"Failed to load {extension}")
                result.failed.append(failure)
        else:
            logger.info(f"Loaded {extension}")
            result.loaded.append(extension)

    logger.info(
        f"{package}: {len(result.loaded)} loaded, {
            len(result.failed)
        } failed, {len(result.optional_failed)} optional packages failed."
    )

    if result.optional_failed:
        logger.warning("Plugins loaded with some optional plugin failures:")

        for failure in result.optional_failed:
            logger.warning("  - %s", failure.extension)

    if result.failed:
        logger.error("Failed extensions:")

        for failure in result.failed:
            logger.error("  - %s", failure.extension)

    return result


def terminate_exception_handler(
    services: Services | None, error_details: str, exception: Exception | None
) -> None:
    if services is not None:
        services.logger.error(
            f"{error_details}: {exception}.", exc_info=exception
        )
    if exception is not None:
        traceback.print_exception(
            type(exception),
            exception,
            exception.__traceback__,
            file=sys.stderr,
        )


async def terminate(
    *,
    bot: CoreBot | None,
    services: Services | None,
    exception: Exception | None,
    code: int,
) -> NoReturn | None:

    errors = []

    if bot is not None:
        if bot.is_terminating:
            services.logger.warning(
                "Bot already closing, ignoring duplicate request to close."
            )
            return None

        bot.is_terminating = True

    if exception:
        terminate_exception_handler(
            services=services,
            error_details="Bot has experienced an unhandled exception",
            exception=exception,
        )

    try:
        if bot is not None:
            if not bot.is_closed():
                await bot.close()

    except Exception as e:
        errors.append(e)
        terminate_exception_handler(
            services=services,
            error_details="Bot experienced an error while trying to close.",
            exception=e,
        )

    try:
        if services is not None:
            await services.close()
    except Exception as e:
        errors.append(e)
        terminate_exception_handler(
            services=services,
            error_details="Services experienced an error while trying to close.",
            exception=e,
        )

    if errors:
        code = 1

    raise SystemExit(code)


class CoreBot(commands.Bot):
    def __init__(self, services: Services) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(command_prefix="~", intents=intents)

        self.services = services

        self.is_terminating = False
        self._logged_ready = False
        self.loaded_cogs: list = []
        self.optional_failed_plugins: list[CogLoadFailure] = []

    async def on_ready(self) -> None:
        global start_time

        do_sync = await self.stores.config.get("#/state/syncnextstart", 0)

        if do_sync == 1:
            for guild in self.consts.guilds_to_sync:
                try:
                    await self.tree.sync(guild=discord.Object(id=guild))
                    self.logger.info(f"Synced commands in guild id: {guild}")
                except discord.Forbidden:
                    pass
            await self.tree.sync()
            await self.stores.config.write("#/state/syncnextstart", 0)
            do_sync = 0

        if not self._logged_ready:
            failed_plugins = []

            for plugin in self.optional_failed_plugins:
                failed_plugins.append(plugin.extension)

            missing_plugins = []

            for plugin in PLUGINS_LIST:
                if (
                    plugin not in self.loaded_cogs
                    and plugin not in failed_plugins
                ):
                    missing_plugins.append(plugin)

            message = dedent(f"""
            ============================================================
            Bot Ready

            Bot
                User               : {self.user} ({self.user.id})
                Application ID     : {self.application_id}
                Session ID         : {self.consts.bot_session_id}
                Started            : {start_time}
                Ready              : {datetime.now(UTC).isoformat()}

            Discord
                Guilds             : {len(self.guilds)}
                Members            : {sum(g.member_count or 0 for g in self.guilds)}
                Latency            : {self.latency * 1000:.1f} ms
                Slash Commands     : {len(await self.tree.fetch_commands())}
                Prefix Commands    : {len(self.commands)}

            Plugins
                Loaded             : {(", ".join(self.loaded_cogs)) or "None"} (count: {len(self.loaded_cogs)})
                Failed to Load     : {(", ".join(failed_plugins)) or "None"} (count: {len(failed_plugins)})
                Missing            : {(",".join(missing_plugins)) or "None"} (count: {len(missing_plugins)})

            Intents
                Guilds             : {self.intents.guilds}
                Members            : {self.intents.members}
                Message Content    : {self.intents.message_content}
                Presences          : {self.intents.presences}

            Platform
                Python             : {platform.python_implementation()} {platform.python_version()}
                Discord.py         : {discord.__version__}
            ============================================================
            """)

            self._logged_ready = await self.startup_notify()
            self.logger.info(message)

    async def retrieve_channel(
        self, id
    ) -> (
        discord.abc.GuildChannel
        | discord.abc.PrivateChannel
        | discord.Thread
        | None
    ):
        try:
            channel = self.get_channel(id)
            if channel is None:
                channel = await self.fetch_channel(id)
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

    async def startup_notify(self) -> bool:
        try:
            channel = await self.retrieve_channel(
                self.consts.system_notifs_channel
            )
            if not isinstance(channel, discord.TextChannel):
                raise ValueError(
                    "Provided Channel ID does not point to a valid discord text channel."
                )
            await channel.send(
                f"Discord ready at time {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S (%Z)')}. Process PID: {os.getpid()}. Session ID: {self.consts.bot_session_id}."
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to notify start: {e}")
            return False

    async def on_disconnect(self) -> None:
        self.logger.warning("Discord disconnect.")

    async def on_resumed(self) -> None:
        self.logger.info(
            f"Discord reconnect. Bot user: {self.user} (ID: {self.user.id})."
        )
        try:
            channel = await self.retrieve_channel(
                id=self.consts.system_notifs_channel
            )
            if not isinstance(channel, discord.TextChannel):
                raise ValueError(
                    "Provided Channel ID does not point to a valid discord text channel."
                )
            await channel.send(
                f"Discord reconnect at time {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S (%Z)')}. Process PID: {os.getpid()}. Session ID: {self.consts.bot_session_id}."
            )
        except Exception as e:
            self.logger.error(f"Failed to notify resume: {e}")

    async def on_error(self, event, *args, **kwargs):
        exception_type, exception, tb = sys.exc_info()
        self.logger.error(
            f"Unhandled exception in event {event}: {exception_type}.",
            exc_info=(exception_type, exception, tb),
        )

    # TODO: Other API Events to implement here: on_cog_add, on_cog_remove,
    # on_extension_load, on_extension_unload

    async def shutdown(
        self, reason: str, requested_by: discord.User, module: str
    ) -> NoReturn | None:
        self.logger.info(
            f"Shutdown requested by {requested_by.name}. Reason: {
                reason
            }. Module used: {module}"
        )
        await terminate(
            bot=self, services=self.services, exception=None, code=0
        )

    async def restart(
        self, reason: str, requested_by: discord.User, module: str
    ) -> NoReturn | None:
        self.logger.info(
            f"Restart requested by {requested_by.name}. Reason: {
                reason
            }. Module used: {module}"
        )
        await terminate(
            bot=self, services=self.services, exception=None, code=10
        )

    async def update_restart(
        self, reason: str, requested_by: discord.User, module: str
    ) -> NoReturn | None:
        self.logger.info(
            f"Restart requested by {requested_by.name}. Reason: {
                reason
            }. Module used: {module}"
        )
        await self.stores.config.write("#/state/syncnextstart", 1)
        await self.stores.config.wait_for_flush()
        await terminate(
            bot=self, services=self.services, exception=None, code=10
        )

    async def crash(self, exc: Exception) -> NoReturn | None:
        self.logger.critical(
            f"Something went wrong, and the bot has to exit. Exception: {exc}"
        )
        await terminate(
            bot=self, services=self.services, exception=exc, code=1
        )

    @property
    def logger(self) -> logging.Logger:
        return self.services.logger

    @property
    def stores(self) -> Stores:
        return self.services.stores

    @property
    def paths(self) -> Paths:
        return self.services.paths

    @property
    def consts(self) -> Consts:
        return self.services.consts


bot = None
services = None
start_time = None


async def main() -> NoReturn | None:

    global bot
    global services
    global start_time

    start_time = datetime.now(UTC).isoformat()

    loop = asyncio.get_running_loop()

    loop.add_signal_handler(
        signal.SIGINT, lambda: asyncio.create_task(signal_exit(signal.SIGINT))
    )

    loop.add_signal_handler(
        signal.SIGTERM,
        lambda: asyncio.create_task(signal_exit(signal.SIGTERM)),
    )

    try:
        token = load_token()

        services = create_services()

        bot = CoreBot(services)

        plugins = await load_cogs(
            bot, services.paths.plugin_cogs, services.paths.plugin_module
        )

        if not plugins.successful:
            raise StartupError(plugins)

        bot.loaded_cogs.extend(plugins.loaded)
        bot.optional_failed_plugins.extend(plugins.optional_failed)

        try:
            logs = prune_directory(services.paths.logs, bot.logger)
            bot.logger.info(f"Removed {logs} log files older than 7 days.")
        except Exception as exc:
            bot.logger.warning(
                f"Error while attempting to remove old log files: {exc}."
            )

        try:
            await bot.start(token)
        except discord.PrivilegedIntentsRequired as exc:
            services.logger.error(
                "Discord rejected one or more privileged intents. Check application Intents settings in Discord Developer portal."
            )
            await terminate(bot=bot, services=services, exception=exc, code=1)

    except Exception as exc:
        if bot is not None:
            await bot.crash(exc)
        elif services is not None:
            await terminate(bot=None, services=services, exception=exc, code=1)
        else:
            await terminate(bot=None, services=None, exception=exc, code=1)


async def signal_exit(signum) -> NoReturn | None:

    global bot
    global services

    if bot and bot.logger:
        bot.logger.info(f"Shutdown requested by SystemD. Signum: {signum}.")

    await terminate(
        bot=bot, services=services, exception=None, code=(128 + signum)
    )


if __name__ == "__main__":
    asyncio.run(main())
