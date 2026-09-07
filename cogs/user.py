import discord
from discord.ext import commands
import logging
import os
import pandas as pd
from datetime import datetime, timezone

USERS_CSV = "users.csv"
ROUNDS_CSV = "rounds.csv"
REGISTRATIONS_CSV = "registrations.csv"
ENTRIES_CSV = "entries.csv"

ADMIN_ROLE = "organizer"


class User(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        brief="Link an account",
        help="Regular users: `!link [platform] [username]`\n"
            "Organizers: `!link [discord_username] [platform] [username]`\n"
            "Platform must be `kaggle` or `nitro`."
    )
    async def link(self, ctx, arg1, arg2, arg3=None):
        df = pd.read_csv(USERS_CSV)
    
        # Regular user
        if arg3 is None:
            discord_username = str(ctx.author)
            platform = arg1
            username = arg2
    
        # Organizer
        else:
            if not any(role.name == ADMIN_ROLE for role in ctx.author.roles):
                await ctx.reply(f"You need the `{ADMIN_ROLE}` role to use this command.")
                return
    
            discord_username = arg1
            platform = arg2
            username = arg3
    
        if platform not in ["kaggle", "nitro"]:
            await ctx.reply("Platform must be `kaggle` or `nitro`.")
            return
    
        # Check whether this platform account is already linked
        platform_mask = df[platform].astype(str) == username
    
        if platform_mask.any():
            existing = df[platform_mask].iloc[0]
    
            if str(existing["discord"]) != discord_username:
                await ctx.reply(
                    f"{platform.title()} `{username}` is already linked to "
                    f"Discord `{existing['discord']}`.\n"
                    "Contact an organizer if you believe that is a mistake."
                )
                return
    
            await ctx.reply(
                f"{platform.title()} `{username}` is already linked to your account."
            )
            return
    
        # Find Discord account
        discord_mask = df["discord"].astype(str) == discord_username
    
        if discord_mask.any():
            # Just add/update this platform
            df.loc[discord_mask, platform] = username
        else:
            # Create a new account
            new_row = {
                "discord": discord_username,
                "kaggle": "None",
                "nitro": "None",
                "rating": "unrated"
            }
            new_row[platform] = username
    
            df = pd.concat(
                [df, pd.DataFrame([new_row])],
                ignore_index=True
            )
    
        df.to_csv(USERS_CSV, index=False)
    
        await ctx.reply(
            f"Linked Discord `{discord_username}` to "
            f"{platform.title()} `{username}`!"
        )

    @commands.command(
        brief="View account information",
        help="View your account information\n"
            "Syntax: `!account`\n"
            "Admins can view another account\n"
            "Syntax: `!account [discord/kaggle] [username]`"
    )
    async def account(self, ctx, platform=None, username=None):
        users_df = pd.read_csv(USERS_CSV)
    
        # No arguments → show own account
        if platform is None and username is None:
            platform = "discord"
            username = str(ctx.author)
    
        if platform not in ["discord", "kaggle", "nitro"]:
            await ctx.reply("Platform must be `discord`, `nitro` or `kaggle`.")
            return
    
        if username is None:
            await ctx.reply("Usage: `!account <discord/kaggle> <username>`")
            return
    
        # Find account
        user = users_df[
            users_df[platform].astype(str) == str(username)
        ]
    
        if user.empty:
            await ctx.reply(
                f"{platform.title()} user `{username}` is not linked yet."
            )
            return
    
        user = user.iloc[0]
        discord_username = str(user["discord"])
    
        # Get latest registration
        registrations_df = pd.read_csv(REGISTRATIONS_CSV)
    
        registrations = registrations_df[
            registrations_df["discord"].astype(str) == discord_username
        ]
    
        if registrations.empty:
            latest_registration = "None"
            rated = ""
        else:
            latest_registration = str(registrations.iloc[-1]["round"])
            rated = str(registrations.iloc[-1]["rated"])
            rated = f" ({rated})"
    
        await ctx.reply(
            f"**Account info**\n"
            f"Discord: `{user['discord']}`\n"
            f"Kaggle: `{user['kaggle']}`\n"
            f"Nitro judge: `{user['nitro']}`\n"
            f"Rating: `{user['rating']}` (for more do `!rating {discord_username}`)\n"
            f"Latest registration: `{latest_registration + rated}`"
        )

    @commands.command(
        brief="View top ratings",
        help="View the 10 highest rated participants.\n"
            "Syntax: `!rankings`"
    )
    async def rankings(self, ctx):
        users_df = pd.read_csv(USERS_CSV)
    
        users_df["rating"] = pd.to_numeric(users_df["rating"], errors="coerce")
        top10 = users_df.dropna(subset=["rating"]).nlargest(10, "rating")
    
        if top10.empty:
            await ctx.reply("No rated participants yet.")
            return
    
        message = "**Top 10 Ratings**\n"
    
        for i, (_, user) in enumerate(top10.iterrows(), 1):
            message += f"**{i}.** `{user['discord']}` — **{user['rating']:.0f}**\n"
    
        await ctx.reply(message)

    @commands.command(
        brief="View recent rounds",
        help="View the 5 most recent rounds and their dates.\n"
            "Syntax: `!rounds`"
    )
    async def rounds(self, ctx):
        df = pd.read_csv(ROUNDS_CSV)
    
        if df.empty:
            await ctx.reply("No rounds have been created yet.")
            return
    
        # Sort by date, newest first, and take 5
        df["date"] = pd.to_datetime(df["date"])
        recent = df.sort_values("date", ascending=False).head(5)
    
        message = "**Recent rounds:**\n"
    
        for _, row in recent.iterrows():
            date = row["date"].strftime("%d/%m/%Y")
            message += f"`{row['name']}` — {date} ({row['status']})\n"
    
        await ctx.reply(message)

    @commands.command(
        brief="View rating progression",
        help="View a user's rating progression across rounds.\n"
            "Shows the round, whether it was rated, and the rating.\n"
            "Also shows their current rating.\n"
            "Syntax: `!rating [platform] [username]`"
    )
    async def rating(self, ctx, platform=None, username=None):
        if platform is None and username is None:
            platform = "discord"
            username = str(ctx.author)
    
        elif platform not in ["discord", "kaggle", "nitro"] or platform is None:
            await ctx.reply("Platform must be `discord`, `nitro` or `kaggle`.")
            return
        elif username == None:
            await ctx.reply("No username was given.")
            return
    
    
        users_df = pd.read_csv(USERS_CSV)
        registrations_df = pd.read_csv(REGISTRATIONS_CSV)
    
        # Find the user
        user = users_df[
            users_df[platform].astype(str) == username
        ]
    
        if user.empty:
            await ctx.reply(f"{platform.title()} user `{username}` is not linked.")
            return
    
        user = user.iloc[0]
        discord_username = str(user["discord"])
    
        # Get all registrations for this user
        user_registrations = registrations_df[
            registrations_df["discord"].astype(str) == discord_username
        ]
    
        if user_registrations.empty:
            await ctx.reply(f"`{username}` has no registered rounds.")
            return
    
        message = f"**Rating progression for `{username}`**\n\n"
    
        for _, row in user_registrations.iterrows():
            round_name = row["round"]
            rated = str(row["rated"])
    
            if rated == "rated":
                round_rating = str(row["rating"]).removesuffix(".0")
                message += (
                    f"`{round_name}` — **Rated** — `{round_rating}`\n"
                )
            else:
                message += (
                    f"`{round_name}` — **Unrated**\n"
                )
    
        message += f"\n**Current rating:** `{user['rating']}`"
    
        await ctx.reply(message)

    @commands.command(
        brief="Register for a round",
        help="Register yourself for a round.\n"
            "Syntax: `!register [round_name]`"
    )
    async def register(self, ctx, round_name, rated=None):
        rounds_df = pd.read_csv(ROUNDS_CSV)
        registrations_df = pd.read_csv(REGISTRATIONS_CSV)
    
        discord_username = str(ctx.author)
    
        # Check that the round exists
        round_row = rounds_df[
            (rounds_df["name"].astype(str) == round_name)
        ]
    
        if round_row.empty:
            await ctx.reply("That round does not exist or its registration period ended.")
            return
    
        if rated != "rated" and rated != "unrated":
            await ctx.reply("Specify whether your participation is rated/unrated.")
            return
    
    
        # Check that registration is open
        if round_row.iloc[0]["status"] == "closed":
            await ctx.reply("Registration for this round is closed.")
            return
    
        # Check that the user has linked their account
        users_df = pd.read_csv(USERS_CSV)
    
        user = users_df[users_df["discord"].astype(str) == discord_username]

        if user.empty or pd.isna(user.iloc[0]["kaggle"]):
            await ctx.reply(
                "You haven't linked your Discord account yet!\n"
                "Use `!link kaggle [kaggle_username]` first."
            )
            return

    
        # Check if already registered
        already_registered = (
            (registrations_df["round"].astype(str) == round_name) &
            (registrations_df["discord"].astype(str) == discord_username)
        ).any()
    
        if already_registered:
            await ctx.reply("You are already registered for this round.")
            return
    
        # Add registration
        new_registration = pd.DataFrame([{
            "round": round_name,
            "discord": discord_username,
            "rated": rated,
            "rating": None
        }])
    
        registrations_df = pd.concat(
            [registrations_df, new_registration],
            ignore_index=True
        )
    
        registrations_df.to_csv(REGISTRATIONS_CSV, index=False)
    
        await ctx.reply(
            f"You are registered for `{round_name}` ({rated})!"
        )

async def setup(bot):
    await bot.add_cog(User(bot))
