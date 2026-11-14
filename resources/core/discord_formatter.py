import typing
import discord

from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import Enum, StrEnum

from resources.core.dicebot_canned_responses import CannedResponses


class DurationFormat(StrEnum):
    SHORT = "short"  # e.g. 1d 2h 45m 35s
    LONG = "long"  # e.g 1 day, 2 hours, 45 minutes, 35 seconds
    # e.g. 1d 2h 45m (uses only the three most significant duration segments)
    COMPACT = "compact"


class TimestampFormat(StrEnum):
    SHORTTIME = "short_time"  # e.g. 3:42 PM
    LONGTIME = "long_time"  # e.g. 3:42:15 PM
    SHORTDATE = "short_date"  # e.g. 01/01/1970
    LONGDATE = "long_date"  # e.g. January 1, 1970
    SHORTDATETIME = "short_datetime"  # e.g. January 1, 1970 3:42 PM
    LONGDATETIME = "long_datetime"  # e.g. Thursday, January 1, 1970 3:42 PM
    RELATIVE = "relative"  # e.g. 2 hours ago


class Colour(Enum):
    SUCCESS = discord.Colour.green()
    FAILURE = discord.Colour.red()
    ERROR = discord.Colour.dark_red()
    WARNING = discord.Colour.orange()
    INFO = discord.Colour.blue()
    GENERIC = discord.Colour.blurple()
    LOADING = discord.Colour.light_gray()

    DICE_GENERIC = discord.Colour(0xF2F3F5)
    DICE_CRIT_SUCCESS = discord.Colour(0xF1C40F)
    DICE_CRIT_LOSS = discord.Colour(0x71368A)
    DICE_WIN = discord.Colour(0x1F8B4C)
    DICE_LOSS = discord.Colour(0x992D22)


class Icon(StrEnum):
    SUCCESS = "✅"
    FAILURE = "❌"
    ERROR = "🚨"
    INFO = "ℹ️"
    WARNING = "⚠️"
    LOADING = "🔄"
    TICK = "✅"
    CROSS = "❌"
    QUESTION = "❓"

    BOT = "🤖"
    GUILD = "🏰"
    MEMBER = "👤"
    CPU = "⚙️"
    MEMORY = "💾"


ButtonCallback = Callable[[discord.Interaction], Awaitable[None]]

DropdownCallback = Callable[[discord.Interaction, list[str]], Awaitable[None]]

UserDropdownCallback = Callable[
    [discord.Interaction, list[discord.Member | discord.User]], Awaitable[None]
]

ChannelDropdownCallback = Callable[
    [
        discord.Interaction,
        list[
            discord.app_commands.AppCommandChannel
            | discord.app_commands.AppCommandThread
        ],
    ],
    Awaitable[None],
]


class DiscordFormatter:
    DurationFormat = DurationFormat
    TimestampFormat = TimestampFormat
    Colour = Colour
    Icon = Icon

    @staticmethod
    def formatter_embed(
        *,
        title: str | None = None,
        description: str | None = None,
        colour: Colour = Colour.GENERIC,
        url: str | None = None,
        timestamp: datetime | None = None,
        fields: list[tuple[str, str, bool]] | None = None,
        author_name: str | None = None,
        author_url: str | None = None,
        author_icon_url: str | None = None,
        footer_text: str | None = None,
        footer_icon_url: str | None = None,
        thumbnail_url: str | None = None,
        image_url: str | None = None,
    ) -> discord.Embed:
        if timestamp is not None:
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("Timestamp must be timezone-aware.")

        if fields is None:
            fields = []

        embed = discord.Embed(
            colour=colour.value,
            title=title,
            url=url,
            description=description,
            timestamp=timestamp,
        )

        for field in fields:
            name = field[0]
            value = field[1]
            inline = field[2]
            embed.add_field(name=name, value=value, inline=inline)

        if author_name:
            embed.set_author(
                name=author_name, url=author_url, icon_url=author_icon_url
            )

        if footer_text or footer_icon_url:
            embed.set_footer(text=footer_text, icon_url=footer_icon_url)

        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        if image_url:
            embed.set_image(url=image_url)

        return embed

    class FormatterView(discord.ui.View):
        def __init__(
            self,
            user: discord.User | discord.Member,
            *components: discord.ui.Item,
            timeout: float | None = 180,
        ):
            super().__init__(timeout=timeout)

            self.user_id = user.id

            self.message: discord.Message | None = None
            # This **must** be assigned after sending the view to discord.
            # Examples:

            # await interaction.response.send_message(embed=embed, view=view)
            # view.message = await interaction.original_response()

            # or

            # view.message = await ctx.send(embed=embed, view=view)

            for component in components:
                self.add_item(component)

        async def interaction_check(
            self, interaction: discord.Interaction
        ) -> bool:
            if interaction.user.id != self.user_id:
                message = CannedResponses.no_perms_response(user=interaction.user)
                await interaction.response.send_message(message, ephemeral=True)
                return False
            return True

        def _disable_all(self) -> None:
            for item in self.children:
                if hasattr(item, "disabled"):
                    item.disabled = True

        async def _edit(
            self,
            *,
            interaction: discord.Interaction | None = None,
            **kwargs: typing.Any,
        ) -> None:
            if interaction is not None:
                if not interaction.response.is_done():
                    await interaction.response.edit_message(**kwargs)
                elif interaction.message is not None:
                    await interaction.message.edit(**kwargs)
            elif self.message is not None:
                await self.message.edit(**kwargs)
            else:
                raise RuntimeError(
                    "View has no interaction or message to edit."
                )

        async def on_error(
            self,
            interaction: discord.Interaction,
            error: Exception,
            item: discord.ui.Item,
        ) -> None:
            self._disable_all()
            self.stop()

            await super().on_error(interaction, error, item)

            try:
                await self._edit(interaction=interaction, view=self)
            except discord.HTTPException:
                pass

            error_response = CannedResponses.generic_error_response_noid(interaction.user)

            if interaction.response.is_done():
                await interaction.followup.send(error_response, ephemeral=True)
            else:
                await interaction.response.send_message(
                    error_response, ephemeral=True
                )

    # View Component Helpers

    class Button(discord.ui.Button):
        def __init__(
            self,
            *,
            callback: ButtonCallback,
            style: discord.ButtonStyle = discord.ButtonStyle.secondary,
            label: str | None = None,
            emoji: str | None = None,
        ) -> None:

            super().__init__(style=style, label=label, emoji=emoji)

            self._callback = callback

        async def callback(self, interaction: discord.Interaction) -> None:
            if self._callback is not None:
                await self._callback(interaction)

    class Dropdown(discord.ui.Select):
        def __init__(
            self,
            *,
            callback: DropdownCallback,
            placeholder: str | None = None,
            min_values: int = 1,
            max_values: int = 1,
            options: list[
                tuple[
                    str,
                    str,
                    str | None,
                    str | discord.Emoji | discord.PartialEmoji | None,
                ]
            ],
        ) -> None:

            self._callback = callback

            droplist = []

            for label, description, value, emoji in options:
                droplist.append(
                    discord.SelectOption(
                        label=label,
                        value=value,
                        description=description,
                        emoji=emoji,
                    )
                )

            super().__init__(
                placeholder=placeholder,
                min_values=min_values,
                max_values=max_values,
                options=droplist,
            )

        async def callback(self, interaction: discord.Interaction) -> None:
            if self._callback is not None:
                await self._callback(interaction, self.values)

    class ChannelDropdown(discord.ui.ChannelSelect):
        def __init__(
            self,
            *,
            callback: ChannelDropdownCallback,
            placeholder: str | None = None,
            min_values: int = 1,
            max_values: int = 1,
            channel_types: list[discord.ChannelType] | None = None,
        ) -> None:
            if channel_types is None:
                channel_types = [discord.ChannelType.text]

            super().__init__(
                channel_types=list(channel_types),
                placeholder=placeholder,
                min_values=min_values,
                max_values=max_values,
            )

            self._callback = callback

        async def callback(self, interaction: discord.Interaction) -> None:
            if self._callback is not None:
                await self._callback(interaction, self.values)

    class UserDropdown(discord.ui.UserSelect):
        def __init__(
            self,
            *,
            callback: UserDropdownCallback,
            placeholder: str | None = None,
            min_values: int = 1,
            max_values: int = 1,
        ) -> None:
            super().__init__(
                placeholder=placeholder,
                min_values=min_values,
                max_values=max_values,
            )

            self._callback = callback

        async def callback(self, interaction: discord.Interaction) -> None:
            if self._callback is not None:
                await self._callback(interaction, self.values)

    @staticmethod
    def clamp(
        value: int | float, minimum: int | float, maximum: int | float
    ) -> int | float:

        if minimum > maximum:
            raise ValueError(
                "Minimum cannot be larger than maximum when clamping."
            )

        return max(minimum, min(value, maximum))

    @staticmethod
    def ratio(val1: int | float, val2: int | float) -> str:

        if val2 == 0:
            raise ZeroDivisionError(
                "Cannot calculate a ratio with a denominator of zero."
            )

        return f"{val1 / val2} : 1"

    @staticmethod
    def ordinal(num: int) -> str:
        num = abs(num)

        if 10 <= num % 100 <= 20:
            suffix = "th"
        else:
            match num % 10:
                case 1:
                    suffix = "st"
                case 2:
                    suffix = "nd"
                case 3:
                    suffix = "rd"
                case _:
                    suffix = "th"

        return f"{num}{suffix}"

    @staticmethod
    def duration(seconds: float, style: DurationFormat) -> str:

        seconds = abs(seconds)

        years = int(seconds // (365 * 24 * 60 * 60))
        seconds %= 365 * 24 * 60 * 60

        months = int(seconds // (30 * 24 * 60 * 60))
        seconds %= 30 * 24 * 60 * 60

        weeks = int(seconds // (7 * 24 * 60 * 60))
        seconds %= 7 * 24 * 60 * 60

        days = int(seconds // (24 * 60 * 60))
        seconds %= 24 * 60 * 60

        hours = int(seconds // (60 * 60))
        seconds %= 60 * 60

        minutes = int(seconds // 60)
        seconds %= 60

        durations = {
            "y": {
                "value": years,
                "longname": "years" if years != 1 else "year",
            },
            "mo": {
                "value": months,
                "longname": "months" if months != 1 else "month",
            },
            "w": {
                "value": weeks,
                "longname": "weeks" if weeks != 1 else "week",
            },
            "d": {"value": days, "longname": "days" if days != 1 else "day"},
            "h": {
                "value": hours,
                "longname": "hours" if hours != 1 else "hour",
            },
            "m": {
                "value": minutes,
                "longname": "minutes" if minutes != 1 else "minute",
            },
            "s": {
                "value": seconds,
                "longname": "seconds" if seconds != 1 else "second",
            },
        }

        usedurations = {}

        for k, v in durations.items():
            if len(usedurations) >= 3 and style == DurationFormat.COMPACT:
                continue
            if v["value"] != 0:
                usedurations[k] = v
            elif k == "s":
                usedurations[k] = v

        parts = []

        for k, v in usedurations.items():
            if style == DurationFormat.LONG:
                parts.append(f"{v['value']} {v['longname']}")
            else:
                parts.append(f"{v['value']}{k}")

        return f"{', ' if style == DurationFormat.LONG else ' '}".join(parts)

    @staticmethod
    def timestamp(value: datetime, style: TimestampFormat) -> str:

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware.")

        styles = {
            TimestampFormat.SHORTTIME: "t",
            TimestampFormat.LONGTIME: "T",
            TimestampFormat.SHORTDATE: "d",
            TimestampFormat.LONGDATE: "D",
            TimestampFormat.SHORTDATETIME: "f",
            TimestampFormat.LONGDATETIME: "F",
            TimestampFormat.RELATIVE: "R",
        }

        return f"<t:{int(value.timestamp())}:{styles[style]}>"

    @staticmethod
    def quantity(
        value: int | float,
        *,
        thousandseparator: str = "",
        decimalseparator: str = ".",
        suffix: bool = False,
        precision: int = 1,
    ) -> str:

        string = ""

        if value == 0:
            return "0"

        if suffix:
            for unit in ["", "K", "M", "B", "T"]:
                if abs(value) < 1000.0:
                    string = f"{value:,.{precision}f}{unit}"
                    break
                if unit != "T":
                    value /= 1000.0
            else:
                string = f"{value:,.{precision}f}T"
        else:
            string = f"{value:,.{precision}f}"

        if "." in string:
            integer, decimal = string.rsplit(".", 1)
            integer = integer.replace(",", thousandseparator)
            decimal = decimal.rstrip("0") or "0"
            string = integer + decimalseparator + decimal
        else:
            string = string.replace(",", thousandseparator)

        return string

    @staticmethod
    def filesize(
        value: int | float,
        *,
        thousandseparator: str = "",
        decimalseparator: str = ".",
        precision: int = 1,
    ) -> str:

        string = ""

        if value == 0:
            return "0 B"

        for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
            if abs(value) < 1024:
                string = f"{value:,.{precision}f} {unit}"
                break
            if unit != "TiB":
                value /= 1024
        else:
            string = f"{value:,.{precision}f} TiB"

        if "." in string:
            integer, decimal = string.rsplit(".", 1)
            integer = integer.replace(",", thousandseparator)
            decimal = decimal.rstrip("0") or "0"
            string = integer + decimalseparator + decimal
        else:
            string = string.replace(",", thousandseparator)

        return string

    @staticmethod
    def percentage(
        val1: int | float, val2: int | float, *, precision: int = 1
    ) -> str:

        if val2 == 0:
            raise ZeroDivisionError(
                "Cannot calculate a percentage with a denominator of zero."
            )

        return f"{((val1 / val2) * 100):.{precision}f}%"
