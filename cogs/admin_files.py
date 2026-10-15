
import discord
from discord.ext import commands
import logging
import os
import pandas as pd
from datetime import datetime, timezone
from embed_utils import aicc_embed

USERS_CSV = "users.csv"
ROUNDS_CSV = "rounds.csv"
REGISTRATIONS_CSV = "registrations.csv"
ENTRIES_CSV = "entries.csv"

ADMIN_ROLE = "organizer"
ADMIN_ROLES = {"organizer", "Bot admin"}
ADMIN_ROLES_TEXT = "`organizer` or `Bot admin`"

class FileManagement(commands.Cog, name="[ADMIN] File Management"):
    def __init__(self, bot):
        self.bot = bot
        
    @commands.command(
        brief="View a CSV",
        help="Send a CSV file.\n"
            "Organizer only\n"
            "Syntax: `!view_csv [filename]`"
    )
    async def view_csv(self, ctx, filename=None):
        if not any(role.name in ADMIN_ROLES for role in ctx.author.roles):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🔴 Organizer command",
                f"You need one of the {ADMIN_ROLES_TEXT} roles to use this command.",
            ))
            return

        if not filename:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "📄 View CSV",
                "Provide a filename, for example `!view_csv users.csv`.",
            ))
            return

        filename = os.path.basename(filename.strip())
        if not filename.lower().endswith(".csv"):
            filename += ".csv"

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(project_root, filename)

        if not os.path.isfile(file_path):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "📄 CSV not found",
                f"`{filename}` does not exist in the bot data folder.",
            ))
            return

        await ctx.reply(
            embed=aicc_embed(
                ctx,
                "📄 CSV export",
                f"Here is the requested data file: `{filename}`.",
            ),
            file=discord.File(file_path, filename=filename),
        )
    
    @commands.command(
        brief="Clear entries",
        help="Clear all entries from `entries.csv`.\n"
            "Organizer only\n"
            "Syntax: `!clear_entries`"
    )
    async def clear_entries(self, ctx):
        if not any(role.name in ADMIN_ROLES for role in ctx.author.roles):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🔴 Organizer command",
                f"You need one of the {ADMIN_ROLES_TEXT} roles to use this command.",
            ))
            return
    
        pd.DataFrame(
            columns=["round", "discord", "time"]
        ).to_csv(ENTRIES_CSV, index=False)
    
        await ctx.reply(embed=aicc_embed(
            ctx,
            "🧹 Entries cleared",
            "`entries.csv` has been cleared successfully.",
        ))

async def setup(bot):
    await bot.add_cog(FileManagement(bot))
