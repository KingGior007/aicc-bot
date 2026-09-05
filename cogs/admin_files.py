
import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import pandas as pd
from datetime import datetime, timezone

USERS_CSV = "users.csv"
ROUNDS_CSV = "rounds.csv"
REGISTRATIONS_CSV = "registrations.csv"
ENTRIES_CSV = "entries.csv"

ADMIN_ROLE = "organizer"

class FileManagement(commands.Cog, name="[ADMIN] File Management"):
    def __init__(self, bot):
        self.bot = bot
        
    @commands.command(
        brief="View a CSV",
        help="Send a CSV file.\n"
            "Organizer only\n"
            "Syntax: `!view_csv [filename]`"
    )
    async def view_csv(self, ctx, filename):
        if not any(role.name == ADMIN_ROLE for role in ctx.author.roles):
            await ctx.reply(f"You need the `{ADMIN_ROLE}` role to use this command.")
            return
    
        if not filename.lower().endswith(".csv"):
            await ctx.reply("The file must be a `.csv` file.")
            return
    
        if not os.path.exists(filename):
            await ctx.reply(f"`{filename}` does not exist.")
            return
    
        await ctx.reply(
            f"Here is `{filename}`:",
            file=discord.File(filename)
        )
    
    @commands.command(
        brief="Clear entries",
        help="Clear all entries from `entries.csv`.\n"
            "Organizer only\n"
            "Syntax: `!clear_entries`"
    )
    async def clear_entries(self, ctx):
        if not any(role.name == ADMIN_ROLE for role in ctx.author.roles):
            await ctx.reply(f"You need the `{ADMIN_ROLE}` role to use this command.")
            return
    
        pd.DataFrame(
            columns=["round", "discord", "time"]
        ).to_csv(ENTRIES_CSV, index=False)
    
        await ctx.reply("✅ `entries.csv` has been cleared.")

async def setup(bot):
    await bot.add_cog(FileManagement(bot))
