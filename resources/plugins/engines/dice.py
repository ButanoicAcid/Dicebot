from __future__ import annotations

import re
import time
from collections import Counter, deque
from dataclasses import dataclass

import numpy

from resources.core.base_cog import UserCommandError


@dataclass(slots=True)
class ParsedSuffix:
    explode: bool
    advantage: str | None
    modifier: int
    keep: str | None
    keep_count: int | None
    reroll: str | None
    reroll_operator: str | None
    reroll_value: int | None
    reroll_upper_value: int | None

    @classmethod
    def from_dict(cls, data: dict) -> ParsedSuffix:
        return cls(
            explode=data["explode"] is not None,
            advantage=data["advantage"],
            modifier=int(data["modifier"] or 0),
            keep=data["keep_type"],
            keep_count=int(data["keep_count"]) if data["keep_count"] else None,
            reroll=data["reroll_type"],
            reroll_operator=data["reroll_operator"],
            reroll_value=int(data["reroll_value"])
            if data["reroll_value"]
            else None,
            reroll_upper_value=int(data["reroll_upper_value"])
            if data["reroll_upper_value"]
            else None,
        )

    def apply_keep(self, rolls: list[int]) -> list[int]:
        if self.keep == "kh":
            return sorted(rolls, reverse=True)[: self.keep_count]
        elif self.keep == "kl":
            return sorted(rolls)[: self.keep_count]
        else:
            return rolls

    def apply_advantage(self, rolls: list[int]) -> int:
        if self.advantage == "adv":
            return max(rolls[0], rolls[1])
        if self.advantage == "dis":
            return min(rolls[0], rolls[1])
        else:
            return sum(rolls)

    def find_totals(self, rolls: list[int]) -> tuple[int, int]:
        nat_total = self.apply_advantage(rolls=rolls)
        mod_total = nat_total + self.modifier

        return nat_total, mod_total

    def should_reroll(self, roll: int) -> bool:
        if self.reroll is None:
            return False

        if self.reroll_upper_value is not None:
            return self.reroll_value <= roll <= self.reroll_upper_value
        elif self.reroll_operator == "<":
            return roll < self.reroll_value
        elif self.reroll_operator == "<=":
            return roll <= self.reroll_value
        elif self.reroll_operator == ">":
            return roll > self.reroll_value
        elif self.reroll_operator == ">=":
            return roll >= self.reroll_value
        else:
            return roll == self.reroll_value

    def always_rerolls(self, bounds: tuple[int, int]) -> bool:
        high, low = bounds
        value = self.reroll_value

        if self.reroll_upper_value is not None:
            return low >= value and high <= self.reroll_upper_value
        elif self.reroll_operator == "<":
            return high < value
        elif self.reroll_operator == "<=":
            return high <= value
        elif self.reroll_operator == ">":
            return low > value
        elif self.reroll_operator == ">=":
            return low >= value
        else:
            return low == high == value


@dataclass(slots=True)
class ParsedRoll:
    count: int
    sides: int
    suffix: ParsedSuffix | None
    flag: str
    arg: str

    def flag_bounds_check(self) -> tuple[int, int]:
        match self.flag:
            case "ra":
                bounds = (int(self.sides * 0.25), 1)
            case "rb":
                bounds = (int(self.sides * 0.5), int(self.sides * 0.25))
            case "rc":
                bounds = (int(self.sides * 0.75), int(self.sides * 0.5))
            case "rd":
                bounds = (self.sides, int(self.sides * 0.75))
            case _:
                bounds = (self.sides, 1)

        if bounds[1] < 1 or bounds[0] < bounds[1]:
            raise UserCommandError("That's not a valid dice range.")

        return bounds

    def inf_reroll_check(self, bounds: tuple[int, int]) -> None:
        if self.suffix and self.suffix.reroll == "r":
            if self.suffix.always_rerolls(bounds):
                raise UserCommandError(
                    "This reroll condition would cause an infinite loop."
                )

    def inf_explode_check(self, bounds: tuple[int, int]) -> None:
        if bounds[0] == bounds[1]:
            raise UserCommandError(
                "This explosion condition would cause infinite explosions."
            )


@dataclass(slots=True)
class RollResult:
    roll_str: str
    rolls: list[int]
    modified_rolls: list[int]
    count: int
    sides: int
    suffix: ParsedSuffix | None
    flag: str
    natural_total: int
    modified_total: int

    @property
    def is_crit(self) -> bool:
        return self.count == 1 and self.natural_total == self.sides

    @property
    def is_fumble(self) -> bool:
        return self.count == 1 and self.natural_total == 1

    @property
    def dropped(self) -> list[int]:
        if not self.suffix or not self.suffix.keep:
            return []

        original = Counter(self.rolls)
        kept = Counter(self.modified_rolls)

        return list((original - kept).elements())

    @property
    def roll_string_text(self) -> str:
        if self.suffix and self.suffix.advantage:
            return f"d{self.sides}{self.suffix.advantage}"

        elif self.flag in ["ra", "rb", "rc", "rd"]:
            return f"{self.count}d{self.sides}"

        return self.roll_str

    @property
    def modifier_text(self) -> str:
        if not self.suffix:
            return "No modifiers..."

        suffix = self.suffix

        if suffix.explode:
            return "Exploding dice!"

        if suffix.modifier or suffix.advantage:
            if suffix.modifier and not suffix.advantage:
                return f"{suffix.modifier:+}"
            elif not suffix.modifier and suffix.advantage:
                return (
                    "Advantage!"
                    if suffix.advantage == "adv"
                    else "Disadvantage!"
                )
            else:
                advtext = (
                    "Advantage"
                    if suffix.advantage == "adv"
                    else "Disadvantage"
                )
                return f"{advtext} and a {suffix.modifier:+}."

        if suffix.keep:
            direction = "highest" if suffix.keep == "kh" else "lowest"
            return f"Keep {direction} {suffix.keep_count}."

        if suffix.reroll:

            action = "Reroll once" if suffix.reroll == "ro" else "Reroll"

            if suffix.reroll_upper_value is not None:
                condition = "if between"
                lower = self._die_face(suffix.reroll_value)
                upper = self._die_face(suffix.reroll_upper_value)
                number = f"{lower} and {upper}"
            else:
                if suffix.reroll_operator == "<":
                    condition = "if less than"
                elif suffix.reroll_operator == "<=":
                    condition = "if less than or equal to"
                elif suffix.reroll_operator == ">":
                    condition = "if greater than"
                elif suffix.reroll_operator == ">=":
                    condition = "if greater than or equal to"
                else:
                    condition = "on"

                number = self._die_face(suffix.reroll_value)

            return f"{action} {condition} {number}."

        return "No modifiers..."

    @property
    def rolls_text(self) -> str:
        if len(self.rolls) <= 100:
            rolls = ", ".join(map(str, self.modified_rolls))
        else:
            rolls = ", ".join(map(str, self.modified_rolls[:100]))
            rolls += f", ... (+{len(self.modified_rolls) - 100} more)"
        return rolls

    @property
    def dropped_rolls_text(self) -> str:
        if len(self.dropped) <= 100:
            rolls = ", ".join(map(str, self.dropped))
        else:
            rolls = ", ".join(map(str, self.dropped[:100]))
            rolls += f", ... (+{len(self.dropped) - 100} more)"
        return rolls

    @staticmethod
    def _die_face(number: int):

        words = {
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "five",
            6: "six",
            7: "seven",
            8: "eight",
            9: "nine",
            10: "ten",
            11: "eleven",
            12: "twelve",
            13: "thirteen",
            14: "fourteen",
            15: "fifteen",
            16: "sixteen",
            17: "seventeen",
            18: "eighteen",
            19: "nineteen",
            20: "twenty",
        }

        face = words.get(number, str(number))

        if face.endswith("y"):
            return face[:-1] + "ies"
        if face.endswith("x"):
            return face + "es"

        return face + "s"


class DiceEngine:
    REROLLS_LIMIT = 100

    def __init__(self, gm_ids: list[int], rng=None) -> None:
        self.gm_ids = gm_ids
        self.rng = rng or numpy.random.default_rng()

    def _is_gm(self, user_id: int) -> bool:
        return user_id in self.gm_ids

    def _parse_roll(self, roll_str: str) -> ParsedRoll:

        specials = (
            r"(?P<explode>!)"
            r"|(?=(?:adv|dis|[+-][0-9]+))(?P<advantage>adv|dis)?(?P<modifier>[+-][0-9]+)?"
            r"|(?P<keep>(?P<keep_type>kh|kl)(?P<keep_count>0*[1-9][0-9]*))"
            r"|(?P<reroll>(?P<reroll_type>ro?)(?P<reroll_operator><=|>=|<|>)?(?P<reroll_value>[1-9][0-9]*))(?::(?P<reroll_upper_value>[1-9][0-9]*))?)"
        )

        specialpattern = re.compile(specials, re.IGNORECASE)
        pattern = re.compile(
            r"^(?P<count>0*[1-9][0-9]*)?(?P<flag>d|r[abcd]|g)(?P<sides>0*[1-9][0-9]*)"
            rf"(?P<suffix>{specials})?"
            r"(?:\s+--\s*(?P<argument>[A-Za-z]+))?$"
        )
        match = pattern.fullmatch(roll_str.lower())

        if not match:
            raise UserCommandError(
                "That's not a valid dice string, check the guide."
            )

        data = match.groupdict()

        count = int(data["count"] or 1)
        flag = data["flag"]
        sides = int(data["sides"])
        arg = data["argument"]

        if count < 1:
            raise UserCommandError("You can't roll less than once dice.")

        if count > 10000:
            raise UserCommandError("You can't roll more than ten thousand dice.")

        if sides < 2:
            raise UserCommandError("The number of sides on a dice cannot be less than two.")

        if sides > 10000:
            raise UserCommandError("The number of sides on a dice cannot be more than ten thousand.")

        suffix = data["suffix"]
        special = None

        if suffix:
            suffixmatch = specialpattern.fullmatch(suffix)

            if suffixmatch:
                special = ParsedSuffix.from_dict(suffixmatch.groupdict())

                if special.advantage is not None and not (count == 1 or count == 2):
                    raise UserCommandError(
                        "You can't roll more than one dice when using dis/advantage."
                    )

                if special.keep_count is not None and special.keep_count > count:
                    raise UserCommandError(
                        "You cannot keep more dice than you roll."
                    )

                if special.reroll_operator is not None and special.reroll_upper_value is not None:
                    raise UserCommandError(
                        "You cannot perform range calculations and size comparisons in the same reroll."
                    )

                if special.reroll_upper_value is not None and special.reroll_upper_value < special.reroll_value:
                    raise UserCommandError(
                        "The lower bound of the reroll range cannot exceed the upper bound."
                    )

        return ParsedRoll(
            count=count, sides=sides, suffix=special, flag=flag, arg=arg
        )

    def _supergamble_number(
        self, low: int, high: int, strength: int = 6
    ) -> int:
        x = numpy.arange(low, high + 1)
        c = (low + high) / 2
        t = (x - c) / ((high - low) / 2)

        weights = (5.6 * t**strength) + 0.3 * numpy.sqrt(
            numpy.sqrt(9.5 * numpy.abs(t))
        )
        p = weights / weights.sum()
        return self.rng.choice(numpy.arange(low, high + 1), p=p)

    def _generate_number(
        self, bounds: tuple[int, int], supergamble: bool
    ) -> int:
        high, low = bounds

        if supergamble:
            value = self._supergamble_number(low=low, high=high, strength=4)
        else:
            value = self.rng.integers(low=low, high=high + 1)

        return max(low, min(value, high))

    def _roll_dice(
        self,
        count: int,
        bounds: tuple[int, int],
        suffix: ParsedSuffix | None,
        supergamble: bool,
    ) -> list[int]:
        results = []
        pending = deque()

        deadline = time.monotonic() + 20

        for _ in range(count):
            if time.monotonic() >= deadline:
                raise UserCommandError("The command took too long.")
            value = self._generate_number(
                bounds=bounds, supergamble=supergamble
            )
            pending.append(value)

        while pending:
            if time.monotonic() >= deadline:
                raise UserCommandError("The command took too long.")
            value = pending.popleft()

            if suffix:
                if suffix.explode and value == bounds[0]:
                    explosion = self._generate_number(
                        bounds=bounds, supergamble=supergamble
                    )
                    pending.append(explosion)

                elif suffix.should_reroll(value):
                    rerolls = 0

                    while True:
                        if rerolls >= self.REROLLS_LIMIT:
                            raise UserCommandError(
                                "The number of rerolls exceeded the limit."
                            )
                        value = self._generate_number(
                            bounds=bounds, supergamble=supergamble
                        )
                        rerolls += 1

                        if not suffix.should_reroll(value):
                            break

                        if suffix.reroll == "ro":
                            break

            results.append(value)

        return results

    def roll(self, roll_str: str, user_id: int | None) -> RollResult:
        parsed = self._parse_roll(roll_str)
        suffix = parsed.suffix

        if parsed.flag in ["ra", "rb", "rc", "rd"] and (
            not user_id or not self._is_gm(user_id)
        ):
            raise UserCommandError(
                "That's not a valid dice string, check the guide."
            )  # haha, lies!

        bounds = parsed.flag_bounds_check()
        count = 2 if suffix and suffix.advantage else parsed.count

        if suffix and suffix.reroll:
            parsed.inf_reroll_check(bounds=bounds)

        if suffix and suffix.explode:
            parsed.inf_explode_check(bounds=bounds)

        rolls = self._roll_dice(
            count=count,
            bounds=bounds,
            suffix=suffix,
            supergamble=(parsed.flag == "g"),
        )
        modified_rolls = suffix.apply_keep(rolls=rolls) if suffix else rolls

        nat_total, mod_total = (
            suffix.find_totals(rolls=modified_rolls)
            if suffix
            else (sum(modified_rolls), sum(modified_rolls))
        )

        sorted_modified = (
            sorted(modified_rolls) if parsed.arg == "order" else modified_rolls
        )

        return RollResult(
            roll_str=roll_str,
            rolls=rolls,
            modified_rolls=sorted_modified,
            count=parsed.count,
            sides=parsed.sides,
            suffix=suffix,
            flag=parsed.flag,
            natural_total=nat_total,
            modified_total=mod_total,
        )

    def eightball(self) -> str:
        return self.rng.choice([
            "It is certain.",
            "Without a doubt.",
            "You may rely on it.",
            "Yes - definitely.",
            "Most likely.",
            "Ask again later.",
            "Reply hazy, try again.",
            "Better not tell you now.",
            "Don't count on it.",
            "Very doubtful.",
        ])

    def coinflip(self, count: int) -> list[str]:
        if not 1 <= count <= 10000:
            raise UserCommandError(
                "You can't flip less than one coin, and you can't flip more than ten thousand."
            )
        return self.rng.choice(["Heads", "Tails"], size=count).tolist()
