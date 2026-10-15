
import discord
from discord.ext import commands
import asyncio
import json
import logging
import math
import os
import pandas as pd
import random
from pathlib import Path
from datetime import datetime, timezone
from views import TaskSubmissionModal, TaskSubmissionView
from views import DynamicTaskButton
from embed_utils import aicc_embed

USERS_CSV = "users.csv"
ROUNDS_CSV = "rounds.csv"
REGISTRATIONS_CSV = "registrations.csv"
ENTRIES_CSV = "entries.csv"

ADMIN_ROLE = "organizer"

SHEET_JSON = Path(__file__).resolve().parent / "cogs" / "sheet.json"
CATEGORY_ICONS_DIR = Path(__file__).resolve().parent / "category-icons"
WEEKLY_STATE_FILE = Path(__file__).resolve().parent / "weekly_used.json"
WEEKLY_CHANNEL_ID = 1546212377106583574
WEEKLY_STATE_LOCK = asyncio.Lock()


def _numeric_score(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(score):
        return None

    return score


def _weekly_task_key(task):
    link = str(task.get("Link") or "").strip()
    if link:
        return f"link:{link}"

    contest = str(task.get("Contest") or "").strip()
    problem = str(task.get("Problem") or "").strip()
    return f"task:{contest}|{problem}"


def _load_weekly_used():
    if not WEEKLY_STATE_FILE.exists():
        return set()

    try:
        data = json.loads(WEEKLY_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    if isinstance(data, dict):
        data = data.get("used", [])

    if not isinstance(data, list):
        return set()

    return {str(item) for item in data}


def _save_weekly_used(used):
    WEEKLY_STATE_FILE.write_text(
        json.dumps(sorted(used), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _progress_bar(value, maximum, slots=10):
    if value is None:
        return "`Not rated`"

    filled = max(0, min(slots, round(value / maximum * slots)))
    return (
        f"`{'█' * filled}{'░' * (slots - filled)}`\n"
        f"`{value:g}/{maximum:g}`"
    )


def _category_icon_path(category):
    category_key = " ".join(
        str(category or "").lower().replace("-", " ").split()
    )

    icon_names = {
        "audio": "audio.png",
        "classical ml": "classical-ml.png",
        "code": "code.png",
        "computer vision": "computer-vision.png",
        "deep learning": "deep-learning.png",
        "multimodal": "multi-modal.png",
        "multi modal": "multi-modal.png",
        "natural language processing": "natural-language-processing.png",
        "reinforcement learning": "reinforcement-learning.png",
        "theory": "theory.png",
        "time series": "time-series.png",
    }

    filename = icon_names.get(category_key)
    if not filename:
        return None

    path = CATEGORY_ICONS_DIR / filename
    return path if path.exists() else None


class AICCHelpCommand(commands.HelpCommand):
    """Render the help command as a clean, red AICC embed."""

    RED = discord.Color.red()
    ORGANIZER_COGS = {
        "[ADMIN] Rounds",
        "[ADMIN] File Management",
    }
    ORGANIZER_COMMANDS = {
        "task_submission",
        "weekly",
        "create_round",
        "start_round",
        "edit_round",
        "bulk_rate",
        "bulk_pts",
        "elo",
        "view_csv",
        "clear_entries",
    }

    def __init__(self):
        super().__init__(
            verify_checks=False,
            no_category="Other commands",
        )

    @staticmethod
    def _category_name(cog):
        if cog is None:
            return "Quick access"

        names = {
            "User": "Participant commands",
            "[ADMIN] Rounds": "Organizer • Rounds",
            "[ADMIN] File Management": "Organizer • Files",
        }
        return names.get(cog.qualified_name, cog.qualified_name)

    @staticmethod
    def _category_emoji(cog):
        if cog is None:
            return "🚀"

        emojis = {
            "User": "🎯",
            "[ADMIN] Rounds": "🏆",
            "[ADMIN] File Management": "📁",
        }
        return emojis.get(cog.qualified_name, "🧰")

    @staticmethod
    def _command_text(ctx, command):
        description = command.short_doc or "No description available."
        return f"`{ctx.clean_prefix}{command.qualified_name}` — {description}"

    def _is_organizer(self):
        return any(
            role.name == ADMIN_ROLE
            for role in getattr(self.context.author, "roles", [])
        )

    def _is_organizer_command(self, command):
        return (
            command.qualified_name in self.ORGANIZER_COMMANDS
            or getattr(command, "cog_name", None) in self.ORGANIZER_COGS
        )

    def _visible_to_requester(self, command):
        return self._is_organizer() or not self._is_organizer_command(command)

    def _base_embed(self, title, description):
        embed = discord.Embed(
            title=title,
            description=description,
            color=self.RED,
        )

        if self.context.bot.user:
            embed.set_author(
                name="AICC • Command Center",
                icon_url=self.context.bot.user.display_avatar.url,
            )
            embed.set_thumbnail(url=self.context.bot.user.display_avatar.url)

        embed.set_footer(
            text="AICC • Competition management made simple"
        )
        return embed

    async def send_bot_help(self, mapping):
        ctx = self.context
        embed = self._base_embed(
            "🔴 AICC Bot Help",
            (
                "Welcome to the AICC competition hub.\n"
                "Your command center for accounts, rounds, ratings, and tasks."
            ),
        )

        embed.add_field(
            name="🚀 Quick start",
            value=(
                "`!rounds`  Latest rounds\n"
                "`!link kaggle <username>`  Link Kaggle\n"
                "`!register <round> <rated/unrated>`  Join a round"
            ),
            inline=False,
        )

        for cog, commands_list in mapping.items():
            visible_commands = await self.filter_commands(
                commands_list,
                sort=True,
            )
            visible_commands = [
                command
                for command in visible_commands
                if self._visible_to_requester(command)
            ]

            if not visible_commands:
                continue

            command_text = "\n".join(
                self._command_text(ctx, command)
                for command in visible_commands
            )

            embed.add_field(
                name=f"{self._category_emoji(cog)}  {self._category_name(cog)}",
                value=command_text,
                inline=True,
            )

        embed.add_field(
            name="💡 Command details",
            value="Use `!help <command>` to see the full description and exact usage.",
            inline=False,
        )
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        ctx = self.context

        if not self._visible_to_requester(command):
            denied_embed = self._base_embed(
                "🔴 Organizer Command",
                "This command is available only to users with the `organizer` role.",
            )
            await self.get_destination().send(embed=denied_embed)
            return

        embed = self._base_embed(
            f"🔴 `{ctx.clean_prefix}{command.qualified_name}`",
            "Here are the details for this command:",
        )

        embed.add_field(
            name="Description",
            value=command.help or command.short_doc or "No description available.",
            inline=False,
        )
        embed.add_field(
            name="⌨️ Usage",
            value=f"`{self.get_command_signature(command)}`",
            inline=False,
        )

        if command.aliases:
            embed.add_field(
                name="Aliases",
                value=", ".join(f"`{alias}`" for alias in command.aliases),
                inline=False,
            )

        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group):
        await self.send_command_help(group)

    async def send_cog_help(self, cog):
        ctx = self.context
        embed = self._base_embed(
            self._category_name(cog),
            "Commands available in this category:",
        )

        visible_commands = await self.filter_commands(
            cog.get_commands(),
            sort=True,
        )
        visible_commands = [
            command
            for command in visible_commands
            if self._visible_to_requester(command)
        ]

        if not visible_commands:
            return

        command_text = "\n".join(
            self._command_text(ctx, command)
            for command in visible_commands
        )
        embed.add_field(name="Commands", value=command_text, inline=False)
        await self.get_destination().send(embed=embed)

if not os.path.exists(USERS_CSV):
    df = pd.DataFrame(columns=["discord", "kaggle", "nitro", "rating", "elo"])
    df.to_csv(USERS_CSV, index=False)
if not os.path.exists(ROUNDS_CSV):
    pd.DataFrame(columns=["name", "date", "status", "links"]).to_csv(
        ROUNDS_CSV, index=False
    )
if not os.path.exists(REGISTRATIONS_CSV):
    pd.DataFrame(columns=["round", "discord", "rated", "rating", "points"]).to_csv(
        REGISTRATIONS_CSV, index=False
    )
if not os.path.exists(ENTRIES_CSV):
    pd.DataFrame(columns=["round", "discord", "time"]).to_csv(
        ENTRIES_CSV, index=False
    )


def ensure_csv_columns(filename, defaults):
    """Migrate existing CSV files without discarding their current data."""
    dataframe = pd.read_csv(filename)
    changed = False

    for column, default in defaults.items():
        if column not in dataframe.columns:
            dataframe[column] = default
            changed = True

    if changed:
        dataframe.to_csv(filename, index=False)


ensure_csv_columns(USERS_CSV, {"elo": 1000})
ensure_csv_columns(REGISTRATIONS_CSV, {"points": None})

token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    help_command=AICCHelpCommand(),
)


def _is_organizer_only_command(command):
    if command is None:
        return False

    return (
        command.qualified_name in AICCHelpCommand.ORGANIZER_COMMANDS
        or getattr(command, "cog_name", None) in AICCHelpCommand.ORGANIZER_COGS
    )


@bot.event
async def on_command_error(ctx, error):
    """Give organizer commands a clear embed when parsing fails."""
    if hasattr(error, "original"):
        error = error.original

    if not _is_organizer_only_command(ctx.command):
        return

    if isinstance(error, commands.MissingRequiredArgument):
        description = (
            f"Missing required argument `{error.param.name}`.\n\n"
            f"Usage: `!{ctx.command.qualified_name} {ctx.command.signature}`"
        )
        title = "⚠️ Missing command argument"
    elif isinstance(error, commands.BadArgument):
        description = (
            f"I couldn't understand the command arguments.\n\n"
            f"Usage: `!{ctx.command.qualified_name} {ctx.command.signature}`"
        )
        title = "⚠️ Invalid command arguments"
    else:
        logging.error(
            "Organizer command '%s' failed",
            getattr(ctx.command, "qualified_name", "unknown"),
            exc_info=(type(error), error, error.__traceback__),
        )
        description = "Something went wrong while running this organizer command."
        title = "🔴 Organizer command error"

    await ctx.reply(embed=aicc_embed(ctx, title, description))

ALLOWED_GUILD_IDS = [
    1406913559446683680,  # AICC Discord
    1546212376657789121,  # AICC Test
]

async def leave_unauthorized_guild(guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(
                "This bot is restricted to the AICC servers and cannot be used here. "
                "The bot will now leave this server."
            )
            break

    await guild.leave()


@bot.check
async def only_allowed_servers(ctx):
    if ctx.guild is None:
        return False

    if ctx.guild.id not in ALLOWED_GUILD_IDS:
        await leave_unauthorized_guild(ctx.guild)
        return False

    return True


@bot.event
async def on_guild_join(guild):
    if guild.id not in ALLOWED_GUILD_IDS:
        await leave_unauthorized_guild(guild)

@bot.command(
    brief="Send task submission message",
    help="Send a message with a button for submitting tasks.\n"
         "The button opens a form and creates a private thread.\n"
         "Organizer only\n"
         "Syntax: `!task_submission`"
)
async def task_submission(ctx):

    if not any(role.name == ADMIN_ROLE for role in ctx.author.roles):
        await ctx.reply(embed=aicc_embed(
            ctx,
            "🔴 Organizer command",
            f"You need the `{ADMIN_ROLE}` role to use this command.",
        ))
        return

    submit_channel = discord.utils.get(
        ctx.guild.text_channels,
        name="submit-a-task"
    )

    if submit_channel is None:
        await ctx.reply(embed=aicc_embed(
            ctx,
            "⚠️ Channel not found",
            "I couldn't find the `#submit-a-task` channel.",
        ))
        return

    embed = discord.Embed(
        title="🔴 Task Submission Portal",
        description=(
            "Have a great competition idea or a complete task ready for review?\n"
            "Use the button below to send it directly to the Problem Review Team."
        ),
        color=discord.Color.red(),
    )

    if ctx.bot.user:
        embed.set_author(
            name="AICC • Problem Review",
            icon_url=ctx.bot.user.display_avatar.url,
        )
        embed.set_thumbnail(url=ctx.bot.user.display_avatar.url)

    embed.add_field(
        name="📝 Submission",
        value="A complete task that you have created and would like to be reviewed.",
        inline=False,
    )
    embed.add_field(
        name="💡 Suggestion",
        value="An idea for a task that you think would be good to create.",
        inline=False,
    )
    embed.add_field(
        name="🚀 How it works",
        value=(
            "1. Click **Submit** below.\n"
            "2. Choose `suggestion` or `submission`.\n"
            "3. Complete the form and a private review thread will be created."
        ),
        inline=False,
    )
    embed.set_footer(text="AICC • Your ideas help shape the next competition")

    await submit_channel.send(
        embed=embed,
        view=TaskSubmissionView()
    )

    await ctx.reply(embed=aicc_embed(
        ctx,
        "✅ Submission panel posted",
        "The task submission panel was sent to #submit-a-task.",
    ))


@bot.command(
    brief="Post a weighted, non-repeating weekly task",
    help=(
        "Choose a random task with an Insightfulness score of at least 1.\n"
        "Higher Insightfulness scores are more likely to be selected.\n"
        "Organizer only.\n"
        "Syntax: `!weekly` or `!weekly reset`"
    ),
)
async def weekly(ctx, action=None):
    if not any(role.name == ADMIN_ROLE for role in ctx.author.roles):
        await ctx.reply(embed=aicc_embed(
            ctx,
            "🔴 Organizer command",
            f"You need the `{ADMIN_ROLE}` role to use this command.",
        ))
        return

    if action is not None and action.lower() != "reset":
        await ctx.reply(embed=aicc_embed(
            ctx,
            "ℹ️ Weekly task usage",
            "Use `!weekly` to post a task or `!weekly reset` to reset the rotation.",
        ))
        return

    if action and action.lower() == "reset":
        async with WEEKLY_STATE_LOCK:
            _save_weekly_used(set())

        reset_embed = discord.Embed(
            title="🔴 Weekly Task Pool Reset",
            description=(
                "All previously selected tasks are available again.\n"
                "Insightfulness 0 and unrated tasks remain excluded."
            ),
            color=discord.Color.red(),
        )
        reset_embed.set_footer(text="AICC • Weekly challenge rotation")
        await ctx.reply(embed=reset_embed)
        return

    async with WEEKLY_STATE_LOCK:
        try:
            tasks = json.loads(SHEET_JSON.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🔴 Weekly task error",
                f"Could not read `sheet.json`: `{error}`",
            ))
            return

        if not isinstance(tasks, list):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🔴 Weekly task error",
                "`sheet.json` must contain a list of tasks.",
            ))
            return

        used = _load_weekly_used()
        eligible_tasks = []
        seen_keys = set()

        for task in tasks:
            if not isinstance(task, dict):
                continue

            insightfulness = _numeric_score(
                task.get("Insightfulness", task.get("Insightful"))
            )
            if insightfulness is None or insightfulness < 1:
                continue

            link = str(task.get("Link") or "").strip()
            if not link.startswith(("http://", "https://")):
                continue

            task_key = _weekly_task_key(task)
            if task_key in used or task_key in seen_keys:
                continue

            task_copy = dict(task)
            task_copy["_insightfulness"] = insightfulness
            task_copy["_key"] = task_key
            eligible_tasks.append(task_copy)
            seen_keys.add(task_key)

        if not eligible_tasks:
            exhausted_embed = discord.Embed(
                title="🔴 Weekly Task Pool Empty",
                description=(
                    "Every eligible task has already been selected.\n"
                    "Use `!weekly reset` to make them available again."
                ),
                color=discord.Color.red(),
            )
            await ctx.reply(embed=exhausted_embed)
            return

        selected_task = random.choices(
            eligible_tasks,
            weights=[task["_insightfulness"] ** 2 for task in eligible_tasks],
            k=1,
        )[0]
        used.add(selected_task["_key"])
        _save_weekly_used(used)

    contest = str(selected_task.get("Contest") or "Unknown contest").strip()
    problem = str(selected_task.get("Problem") or "Untitled task").strip()
    category = str(selected_task.get("Category") or "Uncategorized").strip()
    topic = str(selected_task.get("Topic") or "No topic specified").strip()
    link = str(selected_task["Link"]).strip()
    difficulty = _numeric_score(selected_task.get("Difficulty"))
    insightfulness = selected_task["_insightfulness"]

    embed = discord.Embed(
        title=problem,
        description=(
            f"*{contest}*\n\n"
            f"**Topic**\n{topic}"
        ),
        color=discord.Color.red(),
    )
    embed.set_author(name="AICC • Weekly Challenge")
    embed.add_field(
        name="🗂️ Category",
        value=f"`{category}`",
        inline=True,
    )
    embed.add_field(
        name="⚙️ Difficulty",
        value=_progress_bar(difficulty, 10),
        inline=True,
    )
    embed.add_field(
        name="💡 Insightfulness",
        value=_progress_bar(insightfulness, 3),
        inline=True,
    )
    embed.add_field(
        name="✨ Weekly pick",
        value=(
            "A fresh challenge selected from the AICC task library.\n"
            "This task will not be selected again until the pool is reset."
        ),
        inline=False,
    )
    embed.set_footer(text="AICC • Higher insightfulness tasks are weighted more heavily")

    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="Open task",
            style=discord.ButtonStyle.link,
            url=link,
        )
    )

    icon_path = _category_icon_path(category)
    send_kwargs = {
        "embed": embed,
        "view": view,
    }

    if icon_path:
        embed.set_thumbnail(url=f"attachment://{icon_path.name}")
        send_kwargs["file"] = discord.File(
            str(icon_path),
            filename=icon_path.name,
        )

    try:
        weekly_channel = bot.get_channel(WEEKLY_CHANNEL_ID)
        if weekly_channel is None:
            weekly_channel = await bot.fetch_channel(WEEKLY_CHANNEL_ID)
        await weekly_channel.send(**send_kwargs)
    except (discord.Forbidden, discord.HTTPException) as error:
        await ctx.reply(embed=aicc_embed(
            ctx,
            "🔴 Weekly task error",
            f"Could not post the weekly task: `{error}`",
        ))
        return

    await ctx.reply(embed=aicc_embed(
        ctx,
        "✅ Weekly task posted",
        f"The weekly task was posted in <#{WEEKLY_CHANNEL_ID}>.",
    ))

async def main():
    bot.add_view(TaskSubmissionView())
    bot.add_dynamic_items(DynamicTaskButton)
    await bot.load_extension("cogs.user")
    await bot.load_extension("cogs.admin_rounds")
    await bot.load_extension("cogs.admin_files")
    await bot.start(token)

asyncio.run(main())
