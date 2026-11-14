import random
import discord

class CannedResponses:
    @staticmethod
    def no_perms_response(user: discord.User) -> str:
        return random.choice([
            "You know, you don't have permission to do that.."
        ]).replace("{USER}", user.name)

    @staticmethod
    def bot_no_perms_response(user: discord.User) -> str:
        return random.choice([
            "I'm not allowed to do that."
        ]).replace("{USER}", user.name)

    @staticmethod
    def generic_error_response(user: discord.User, id: str) -> str:
        return random.choice([
            "Something went wrong, go check for '{ID}' in the logs."
        ]).replace("{USER}", user.name).replace("{ID}", id)

    @staticmethod
    def generic_error_response_noid(user: discord.User) -> str:
        return random.choice([
            "Something went wrong."
        ]).replace("{USER}", user.name)

    @staticmethod
    def restart_response(user: discord.User) -> str:
        return random.choice([
            "Fine, but it's not like I *want* to restart or anything...",
            "Really? Do I **have** to..."
        ]).replace("{USER}", user.name)

    @staticmethod
    def shutdown_response(user: discord.User) -> str:
        return random.choice([
            "Do you *really* want me to go? Fine then.."
        ]).replace("{USER}", user.name)

    @staticmethod
    def user_command_error_response(error: str, user: discord.User) -> str:
        prefix = [
            "You're an idiot."
        ]
        suffix = [
            "Idiot."
        ]

        choice = random.choice([1, 2])
        if choice == 1:
            response = random.choice(prefix).replace("{USER}", user.name)
            message = f"{response} {error}"
        else:
            response = random.choice(suffix).replace("{USER}", user.name)
            message = f"{error} {response}"

        return message

    @staticmethod
    def coinflip_responses(heads: int, tails: int, user: discord.User) -> str:
        return random.choice([
            "You got... {HEADS} heads, and {TAILS} tails."
        ]).replace("{HEADS}", str(heads)).replace("{TAILS}", str(tails)).replace("{USER}", user.name)

    @staticmethod
    def topicwheel_discuss_response(choice: str, user: discord.User) -> str:
        return random.choice([
            "The topic is now {CHOICE}."
        ]).replace("{CHOICE}", choice).replace("{USER}", user.name)
    
    @staticmethod
    def topicwheel_selfdiscuss_response(user: discord.User) -> str:
        return random.choice([
            "The topic is now... me!?"
        ]).replace("{USER}", user.name)
    
    @staticmethod
    def topicwheel_empty_response(user: discord.User) -> str:
        return random.choice([
            "Nothing to talk about? How boring..."
        ]).replace("{USER}", user.name)

    @staticmethod
    def topicwheel_add_response(choice: str, user: discord.User) -> str:
        return random.choice([
            "Are you **sure** you want to talk about {CHOICE}?",
            "Really? {CHOICE}? I mean, if you want to..."
        ]).replace("{CHOICE}", choice).replace("{USER}", user.name)

    @staticmethod
    def topicwheel_remove_response(choice: str, user: discord.User) -> str:
        return random.choice([
            "But I liked {CHOICE}...",
            "Removed {CHOICE} from the topic list. What, not a fan?"
        ]).replace("{CHOICE}", choice).replace("{USER}", user.name)