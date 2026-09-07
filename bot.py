
import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import pandas as pd
from datetime import datetime, timezone
from views import TaskSubmissionModal, TaskSubmissionView

USERS_CSV = "users.csv"
ROUNDS_CSV = "rounds.csv"
REGISTRATIONS_CSV = "registrations.csv"
ENTRIES_CSV = "entries.csv"

ADMIN_ROLE = "organizer"

if not os.path.exists(USERS_CSV):
    df = pd.DataFrame(columns=["discord", "kaggle", "nitro", "rating"])
    df.to_csv(USERS_CSV, index=False)
if not os.path.exists(ROUNDS_CSV):
    pd.DataFrame(columns=["name", "date", "status", "links"]).to_csv(
        ROUNDS_CSV, index=False
    )
if not os.path.exists(REGISTRATIONS_CSV):
    pd.DataFrame(columns=["round", "discord", "rated", "rating"]).to_csv(
        REGISTRATIONS_CSV, index=False
    )
if not os.path.exists(ENTRIES_CSV):
    pd.DataFrame(columns=["round", "discord", "time"]).to_csv(
        ENTRIES_CSV, index=False
    )

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

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
        await ctx.reply(
            f"You need the `{ADMIN_ROLE}` role to use this command."
        )
        return

    submit_channel = discord.utils.get(
        ctx.guild.text_channels,
        name="submit-a-task"
    )

    if submit_channel is None:
        await ctx.reply("I couldn't find the `#submit-a-task` channel.")
        return

    # Customize this message later
    message = (
        "**Task Submissions**\n\n"
        "**Submission:** A complete task that you have created and would like to be reviewed.\n"
        "**Suggestion:** An idea for a task that you think would be good to create.\n\n"
        "Click the button below to submit a suggestion or submission."
    )

    await submit_channel.send(
        message,
        view=TaskSubmissionView()
    )

    await ctx.reply("✅ Submission message sent to #submit-a-task.")

async def main():
    await bot.load_extension("cogs.user")
    await bot.load_extension("cogs.admin_rounds")
    await bot.load_extension("cogs.admin_files")
    await bot.start(token)

import asyncio
asyncio.run(main())
