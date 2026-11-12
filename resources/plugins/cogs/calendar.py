from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands, tasks

from resources.core.base_cog import BaseCog, UserCommandError
from resources.core.discord_formatter import DiscordFormatter

MONTHSDICT = {
    1: {"name": "Aquarius (January)", "length": 30},
    2: {"name": "Pisces (February)", "length": 30},
    3: {"name": "Aries (March)", "length": 30},
    4: {"name": "Taurus (April)", "length": 30},
    5: {"name": "Gemini (May)", "length": 30},
    6: {"name": "Cancer (June)", "length": 30},
    7: {"name": "Leo (July)", "length": 30},
    8: {"name": "Virgo (August)", "length": 30},
    9: {"name": "Libra (September)", "length": 30},
    10: {"name": "Scorpio (October)", "length": 30},
    11: {"name": "Sagittarius (November)", "length": 30},
    12: {"name": "Capricorn (December)", "length": 30},
}


@dataclass(slots=True)
class CalendarObj:
    start_day: int
    elapsed_days: int
    months_dict: dict
    timespeed: int

    paused: bool

    tick_msg: str
    event_msg: str

    events: list[EventObj]

    announce_channel_id: int
    time_tick_last: float

    @classmethod
    def from_dict(cls, data: dict) -> CalendarObj:
        return cls(
            start_day=int(data["start_day"]),
            elapsed_days=int(data["elapsed_days"]),
            months_dict=cls.normalize_months_dict(data["months_dict"]),
            timespeed=int(data["timespeed"]),
            paused=bool(data["paused"]),
            tick_msg=data["tick_msg"],
            event_msg=data["event_msg"],
            events=[EventObj.from_dict(event) for event in data["events"]],
            announce_channel_id=int(data["announce_channel_id"]),
            time_tick_last=float(data["time_tick_last"]),
        )

    def to_dict(self) -> dict:
        return {
            "start_day": self.start_day,
            "elapsed_days": self.elapsed_days,
            "months_dict": self.months_dict,
            "timespeed": self.timespeed,
            "paused": self.paused,
            "tick_msg": self.tick_msg,
            "event_msg": self.event_msg,
            "events": [event.to_dict() for event in self.events],
            "announce_channel_id": self.announce_channel_id,
            "time_tick_last": self.time_tick_last,
        }

    @classmethod
    def normalize_months_dict(cls, months_dict):
        return {int(k): v for k, v in months_dict.items()}

    @property
    def abs_day(self):
        return self.start_day + self.elapsed_days

    def formatted_calendar_message(self) -> str:
        day, month, year = Calendar.abs_day_to_date(
            abs_day=self.abs_day, months_dict=self.months_dict
        )
        start_day, start_month, start_year = Calendar.abs_day_to_date(
            abs_day=self.start_day, months_dict=self.months_dict
        )
        template = self.tick_msg

        replacements = {
            "{DATE}": f"{day}/{month}/{year}",
            "{DAY}": str(day),
            "{ORDINAL}": DiscordFormatter.ordinal(day),
            "{MONTH}": str(month),
            "{MONTHTEXT}": self.months_dict[month]["name"]
            if month in self.months_dict
            else "Unknown",
            "{YEAR}": str(year),
            "{DELTA}": str(self.elapsed_days),
            "{STARTDATE}": f"{start_day}/{start_month}/{start_year}",
            "{STARTDAY}": str(start_day),
            "{STARTORDINAL}": DiscordFormatter.ordinal(start_day),
            "{STARTMONTH}": str(start_month),
            "{STARTMONTHTEXT}": self.months_dict[start_month]["name"]
            if start_month in self.months_dict
            else "Unknown",
            "{STARTYEAR}": str(start_year),
        }

        for key, value in replacements.items():
            template = template.replace(key, value)
        return template

    def _formatted_event_message(self, event: EventObj) -> str:

        day, month, year = Calendar.abs_day_to_date(
            abs_day=event.trigger_abs_day, months_dict=self.months_dict
        )

        replacements = {
            "{DATE}": f"{day}/{month}/{year}",
            "{DAY}": str(day),
            "{ORDINAL}": DiscordFormatter.ordinal(day),
            "{MONTH}": str(month),
            "{MONTHTEXT}": self.months_dict[month]["name"]
            if month in self.months_dict
            else "Unknown",
            "{YEAR}": str(year),
            "{USERPING}": f"<@{event.creatorid}>",
            "{TITLE}": event.title,
        }

        template = self.event_msg
        for key, value in replacements.items():
            template = template.replace(key, value)
        return template

    def get_period_event_messages(self) -> list[str] | None:
        event_msg_list = []

        for event in self.events:
            if not event.should_announce(
                abs_day=self.abs_day, timespeed=self.timespeed
            ):
                continue
            event_msg_list.append(self._formatted_event_message(event=event))

        return event_msg_list or None

    def remove_period_events(self) -> None:
        events_to_keep = []
        for event in self.events:
            if not event.should_announce(
                abs_day=self.abs_day, timespeed=self.timespeed
            ):
                events_to_keep.append(event)
        self.events = events_to_keep

    def do_day_tick(self) -> bool:
        now = time.time()
        last = self.time_tick_last
        elapsed = now - last

        if elapsed < 86400 or self.paused:
            return False

        days_since_tick = int(elapsed // 86400)
        self.elapsed_days += days_since_tick * self.timespeed
        self.time_tick_last += days_since_tick * 86400
        return True

    def skip(self, days: int = 0, months: int = 0, years: int = 0) -> None:

        if days < 0 or months < 0 or years < 0:
            raise UserCommandError("Skip values cannot be negative.")

        if days == 0 and months == 0 and years == 0:
            raise UserCommandError(
                "At least one skip value must be greater than zero."
            )

        if months > 50:
            raise UserCommandError(
                "Skipped months cannot exceed 50 in a single operation."
            )

        month_lengths = Calendar.get_month_lengths(
            months_dict=self.months_dict
        )
        days_per_year = sum(month_lengths)

        if days:
            self.elapsed_days += days

        if months:
            _, current_month, _ = Calendar.abs_day_to_date(
                abs_day=self.abs_day, months_dict=self.months_dict
            )
            for _ in range(months):
                self.elapsed_days += month_lengths[current_month - 1]
                current_month = (current_month % len(month_lengths)) + 1

        if years:
            self.elapsed_days += years * days_per_year

    def rewind(self, days: int = 0, months: int = 0, years: int = 0) -> None:
        if days < 0 or months < 0 or years < 0:
            raise UserCommandError("Rewind values cannot be negative.")

        if days == 0 and months == 0 and years == 0:
            raise UserCommandError(
                "At least one rewind value must be greater than zero."
            )

        if months > 50:
            raise UserCommandError(
                "Rewound months cannot exceed 50 in a single operation."
            )

        month_lengths = Calendar.get_month_lengths(
            months_dict=self.months_dict
        )
        days_per_year = sum(month_lengths)
        original_elapsed = self.elapsed_days

        if days:
            self.elapsed_days -= days

        if months:
            _, current_month, _ = Calendar.abs_day_to_date(
                abs_day=self.abs_day, months_dict=self.months_dict
            )

            for _ in range(months):
                previous_month = ((current_month - 2) % len(month_lengths)) + 1
                self.elapsed_days -= month_lengths[previous_month - 1]
                current_month = previous_month

        if years:
            self.elapsed_days -= years * days_per_year

        _, _, current_year = Calendar.abs_day_to_date(
            abs_day=self.abs_day, months_dict=self.months_dict
        )

        if current_year < 1:
            self.elapsed_days = original_elapsed
            raise UserCommandError(
                "Rewind cannot take the calendar before year 1. Changes have been reverted."
            )

    def toggle_pause(self) -> None:
        if self.paused:
            self.paused = False
            self.time_tick_last = time.time()
        else:
            self.paused = True

    def create_event(self, date: str, title: str, creatorid: int) -> None:
        uuid = BaseCog.new_uuid()
        trigger_abs_day = Calendar.date_to_abs_day(
            date=date, months_dict=self.months_dict
        )
        if trigger_abs_day < (self.abs_day + self.timespeed):
            raise UserCommandError(
                "Event trigger day cannot occur in this or a past calendar period."
            )
        event = EventObj(
            uuid=uuid,
            trigger_abs_day=trigger_abs_day,
            title=title,
            creatorid=creatorid,
        )
        self.events.append(event)

    def delete_event(self, uuid: str) -> bool:
        for event in self.events[::]:
            if event.uuid == uuid:
                self.events.remove(event)
                return True
        return False


@dataclass(slots=True)
class EventObj:
    uuid: str
    trigger_abs_day: int
    title: str
    creatorid: int

    @classmethod
    def from_dict(cls, data: dict) -> EventObj:
        return cls(
            uuid=data["uuid"],
            trigger_abs_day=int(data["trigger_abs_day"]),
            title=data["title"],
            creatorid=int(data["creatorid"]),
        )

    def to_dict(self) -> dict:
        return {
            "uuid": self.uuid,
            "trigger_abs_day": self.trigger_abs_day,
            "title": self.title,
            "creatorid": self.creatorid,
        }

    def should_announce(self, abs_day: int, timespeed: int) -> bool:
        return self.trigger_abs_day <= abs_day + timespeed


class Calendar(BaseCog):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        self._guild_locks: dict[int, asyncio.Lock] = {}

    async def cog_load(self) -> None:
        self.calendar_loop.start()

    async def cog_unload(self):
        self.calendar_loop.cancel()

    def _get_guild_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._guild_locks:
            self._guild_locks[guild_id] = asyncio.Lock()

        return self._guild_locks[guild_id]

    @staticmethod
    def validate_date(date: str, months_dict: dict) -> tuple[int, int, int]:
        try:
            day, month, year = map(int, date.split("/"))
        except ValueError:
            raise UserCommandError(f"Invalid date format: {date}")

        if year < 1:
            raise UserCommandError("Invalid year: cannot be less than one.")

        if month not in months_dict:
            raise UserCommandError(f"Invalid month: {month}")

        month_length = Calendar.get_month_lengths(months_dict=months_dict)[
            month - 1
        ]

        if day < 1 or day > month_length:
            raise UserCommandError(
                "Invalid day: Day cannot be less than one or greater than the length of the current month."
            )

        return day, month, year

    @staticmethod
    def get_month_lengths(months_dict: dict) -> list[int]:
        return [
            months_dict[i]["length"]
            for i in range(1, len(months_dict.items()) + 1)
        ]

    @staticmethod
    def date_to_abs_day(date: str, months_dict: dict) -> int:
        day, month, year = Calendar.validate_date(
            date=date, months_dict=months_dict
        )
        month_lengths = Calendar.get_month_lengths(months_dict=months_dict)
        year_length = sum(month_lengths)

        years_to_date = year * year_length
        months_to_date = sum(month_lengths[: month - 1])
        days_to_date = day - 1

        return years_to_date + months_to_date + days_to_date

    @staticmethod
    def abs_day_to_date(
        abs_day: int, months_dict: dict
    ) -> tuple[int, int, int]:
        month_lengths = Calendar.get_month_lengths(months_dict=months_dict)
        days_per_year = sum(month_lengths)

        year = abs_day // days_per_year
        day_of_year = abs_day % days_per_year

        month = 1
        for length in month_lengths:
            if day_of_year < length:
                break
            day_of_year -= length
            month += 1
        day = day_of_year + 1

        return day, month, year

    @tasks.loop(seconds=300)
    async def calendar_loop(self):
        calendars = await self.stores.guilds.get("#/calendar", None)

        if not calendars:
            return

        for guildid in calendars:
            try:
                async with self._get_guild_lock(int(guildid)):
                    calendar_data = await self.stores.guilds.read(
                        f"#/calendar/{guildid}"
                    )
                    calendar = CalendarObj.from_dict(calendar_data)
                    ticked = calendar.do_day_tick()
                    if not ticked:
                        continue
                    tick_msg = calendar.formatted_calendar_message()
                    event_msg_list = calendar.get_period_event_messages()
                    if event_msg_list:
                        event_msg = "\n".join(["Events:", *event_msg_list])

                    tick_msg_conf = await self.send_message(
                        channelid=calendar.announce_channel_id,
                        content=tick_msg,
                    )

                    if isinstance(tick_msg_conf, discord.Message):
                        await self.stores.guilds.write(
                            f"#/calendar/{guildid}", calendar.to_dict()
                        )

                    if event_msg_list:
                        event_msg_conf = await self.send_message(
                            channelid=calendar.announce_channel_id,
                            content=event_msg,
                        )

                        if isinstance(event_msg_conf, discord.Message):
                            calendar.remove_period_events()
                            await self.stores.guilds.write(
                                f"#/calendar/{guildid}", calendar.to_dict()
                            )

            except Exception:
                self.logger.exception(
                    f"Failed to process calendar for guild {guildid}."
                )

    @calendar_loop.before_loop
    async def before_calendar_loop(self) -> None:
        await self.bot.wait_until_ready()

    calendar = app_commands.Group(
        name="calendar", description="Calendar commands"
    )

    async def _get_calendar(
        self, guild_id: int, expect_missing: bool = False
    ) -> CalendarObj | None:
        data = await self.stores.guilds.get(
            f"#/calendar/{guild_id}",
            None,
        )

        if data is None:
            if not expect_missing:
                raise UserCommandError(
                    "This guild does not have a running calendar."
                )
            return None

        elif data:
            if expect_missing:
                raise UserCommandError(
                    "This guild already has a running calendar."
                )
            return CalendarObj.from_dict(data)

    async def _save_calendar(
        self,
        guild_id: int,
        calendar: CalendarObj,
    ) -> None:
        await self.stores.guilds.write(
            f"#/calendar/{guild_id}",
            calendar.to_dict(),
        )

    @calendar.command(name="start", description="Starts the calendar")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def start(
        self,
        interaction: discord.Interaction,
        date: str,
        timespeed: int,
        message: str,
        eventmsg: str,
    ):
        await interaction.response.defer()

        if timespeed <= 0:
            raise UserCommandError("Timespeed must be greater than zero.")

        async with self._get_guild_lock(interaction.guild.id):
            await self._get_calendar(
                guild_id=interaction.guild.id, expect_missing=True
            )
            calendar = CalendarObj(
                start_day=Calendar.date_to_abs_day(
                    date=date, months_dict=MONTHSDICT
                ),
                elapsed_days=0,
                months_dict=MONTHSDICT,
                timespeed=timespeed,
                paused=False,
                tick_msg=message,
                event_msg=eventmsg,
                events=[],
                announce_channel_id=interaction.channel.id,
                time_tick_last=time.time(),
            )
            await self._save_calendar(
                guild_id=interaction.guild.id, calendar=calendar
            )

            first_message = calendar.formatted_calendar_message()
            await interaction.followup.send(content=first_message)

    @calendar.command(name="stop", description="Stops the calendar")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def stop(self, interaction: discord.Interaction):
        await interaction.response.defer()

        async with self._get_guild_lock(interaction.guild.id):
            await self._get_calendar(guild_id=interaction.guild.id)
            await self.stores.guilds.delete(
                f"#/calendar/{interaction.guild.id}"
            )

            await interaction.followup.send("Calendar stopped.")

    @calendar.command(
        name="timespeed", description="Change the calendar timespeed."
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def timespeed(self, interaction: discord.Interaction, speed: int):
        await interaction.response.defer()
        if speed <= 0:
            raise UserCommandError("Timespeed must be greater than 0.")

        async with self._get_guild_lock(interaction.guild.id):
            calendar = await self._get_calendar(guild_id=interaction.guild.id)
            calendar.timespeed = speed
            await self._save_calendar(
                guild_id=interaction.guild.id, calendar=calendar
            )

            await interaction.followup.send(f"Timespeed set to {speed}.")

    @calendar.command(
        name="toggle", description="Pauses or unpauses the calendar."
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle(self, interaction: discord.Interaction):
        await interaction.response.defer()

        async with self._get_guild_lock(interaction.guild.id):
            calendar = await self._get_calendar(guild_id=interaction.guild.id)
            calendar.toggle_pause()
            await self._save_calendar(
                guild_id=interaction.guild.id, calendar=calendar
            )

            await interaction.followup.send(
                f"Calendar {'paused' if calendar.paused else 'unpaused'}."
            )

    @calendar.command(name="skip", description="Skips the calendar forwards.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def skip(
        self,
        interaction: discord.Interaction,
        days: int = 0,
        months: int = 0,
        years: int = 0,
    ):
        await interaction.response.defer()

        async with self._get_guild_lock(interaction.guild.id):
            calendar = await self._get_calendar(guild_id=interaction.guild.id)
            calendar.skip(days=days, months=months, years=years)
            skip_message = calendar.formatted_calendar_message()
            event_msg_list = calendar.get_period_event_messages()
            if event_msg_list:
                event_message = "\n".join(
                    ["Bypassed Events:", *event_msg_list]
                )

            skip_conf = await interaction.followup.send(
                content=skip_message, wait=True
            )

            if isinstance(skip_conf, discord.WebhookMessage):
                await self._save_calendar(
                    guild_id=interaction.guild.id, calendar=calendar
                )

            if event_msg_list:
                event_conf = await interaction.followup.send(
                    content=event_message, wait=True
                )
                if isinstance(event_conf, discord.WebhookMessage):
                    calendar.remove_period_events()
                    await self._save_calendar(
                        guild_id=interaction.guild.id, calendar=calendar
                    )

    @calendar.command(
        name="rewind", description="Winds the calendar backwards."
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def rewind(
        self,
        interaction: discord.Interaction,
        days: int = 0,
        months: int = 0,
        years: int = 0,
    ):
        await interaction.response.defer()

        async with self._get_guild_lock(interaction.guild.id):
            calendar = await self._get_calendar(guild_id=interaction.guild.id)
            calendar.rewind(days=days, months=months, years=years)
            rewind_message = calendar.formatted_calendar_message()

            rewind_conf = await interaction.followup.send(
                content=rewind_message, wait=True
            )

            if isinstance(rewind_conf, discord.WebhookMessage):
                await self._save_calendar(
                    guild_id=interaction.guild.id, calendar=calendar
                )

    @calendar.command(
        name="addevent", description="Adds an event to the calendar."
    )
    @app_commands.guild_only()
    async def addevent(
        self, interaction: discord.Interaction, date: str, title: str
    ):
        await interaction.response.defer()

        if "@" in title:
            raise UserCommandError(
                "You can't have @ in an event title, to prevent unintended mentions."
            )

        async with self._get_guild_lock(interaction.guild.id):
            calendar = await self._get_calendar(guild_id=interaction.guild.id)
            calendar.create_event(
                date=date, title=title, creatorid=interaction.user.id
            )
            await self._save_calendar(
                guild_id=interaction.guild.id, calendar=calendar
            )

            await interaction.followup.send(
                f"Added event '{title}' for date {date}."
            )

    # TODO: add calendar exacttime


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Calendar(bot))
