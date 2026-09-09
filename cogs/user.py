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
INITIAL_ELO = 1000


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
        if "elo" not in df.columns:
            df["elo"] = INITIAL_ELO
        df["elo"] = pd.to_numeric(df["elo"], errors="coerce").fillna(INITIAL_ELO)
    
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
                "rating": "unrated",
                "elo": INITIAL_ELO,
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
            "View another account\n"
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
    
        def server_emoji(name, fallback):
            custom_emoji = discord.utils.get(
                getattr(ctx.guild, "emojis", []),
                name=name,
            )
            return str(custom_emoji) if custom_emoji else fallback

        def display_value(value, missing="Not linked"):
            if pd.isna(value) or str(value).strip().lower() in {"", "nan", "none"}:
                return missing
            return str(value)

        discord_emoji = server_emoji("discord", "💬")
        kaggle_emoji = server_emoji("kaggle", "📊")
        nitro_emoji = server_emoji("nitro", "⚖️")
        rating_emoji = server_emoji("aicc_white", "⭐")
        registration_emoji = server_emoji("registration", "📝")

        if registrations.empty:
            latest_registration = "No registrations yet"
            registration_status = ""
        else:
            latest_registration = display_value(
                registrations.iloc[-1]["round"],
                "Unknown round",
            )
            registration_status = f" • {str(registrations.iloc[-1]['rated']).title()}"

        embed = discord.Embed(
            title="Account Profile",
            description=(
                "Your linked identities and current AICC competition status."
            ),
            color=discord.Color.red(),
        )

        if ctx.bot.user:
            embed.set_author(
                name="AICC • Participant Profile",
                icon_url=ctx.bot.user.display_avatar.url,
            )

        requester_names = {str(ctx.author), ctx.author.name}
        if discord_username in requester_names:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)

        embed.add_field(
            name=f"{discord_emoji} Discord",
            value=f"`{display_value(user['discord'])}`",
            inline=True,
        )
        embed.add_field(
            name=f"{kaggle_emoji} Kaggle",
            value=f"`{display_value(user['kaggle'])}`",
            inline=True,
        )
        embed.add_field(
            name=f"{nitro_emoji} Nitro judge",
            value=f"`{display_value(user['nitro'])}`",
            inline=True,
        )
        current_elo = display_value(user.get("elo"), str(INITIAL_ELO))
        embed.add_field(
            name=f"{rating_emoji} ELO",
            value=(
                f"`{current_elo}`\n"
                f"Use `!rating {discord_username}` for progression."
            ),
            inline=False,
        )
        embed.add_field(
            name=f"{registration_emoji} Latest registration",
            value=f"`{latest_registration}`{registration_status}",
            inline=False,
        )
        embed.set_footer(text="AICC • Keep your competition profile up to date")

        await ctx.reply(embed=embed)

    @commands.command(
        brief="View ELO rankings",
        aliases=["ranking"],
        help="View the 10 highest ELO participants.\n"
            "Syntax: `!rankings` or `!ranking`"
    )
    async def rankings(self, ctx):
        users_df = pd.read_csv(USERS_CSV)

        if "elo" not in users_df.columns:
            users_df["elo"] = INITIAL_ELO
        users_df["elo"] = pd.to_numeric(users_df["elo"], errors="coerce")
        top10 = users_df.dropna(subset=["elo"]).nlargest(10, "elo")

        if top10.empty:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🏆 AICC ELO Rankings",
                "No rated participants yet.",
                footer="AICC • ELO leaderboard",
            ))
            return

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (_, user) in enumerate(top10.iterrows(), 1):
            medal = medals[i - 1] if i <= len(medals) else "🔹"
            lines.append(
                f"{medal} **{i}.** {user['discord']} — **{user['elo']:.0f} ELO**"
            )

        embed = aicc_embed(
            ctx,
            "🏆 AICC ELO Rankings",
            "The strongest current ELO scores in the AICC competition.",
            footer="AICC • ELO leaderboard",
        )
        embed.add_field(
            name="Leaderboard",
            value="\n".join(lines),
            inline=False,
        )
        embed.add_field(
            name="📌 Ranking notes",
            value="ELO starts at 1000 and changes after rated rounds.",
            inline=False,
        )
        await ctx.reply(embed=embed)

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

    async def _send_round_points_leaderboard(self, ctx, round_name):
        registrations_df = pd.read_csv(REGISTRATIONS_CSV)

        if "points" not in registrations_df.columns:
            registrations_df["points"] = None

        round_mask = (
            registrations_df["round"].astype(str).str.strip().str.casefold()
            == round_name.casefold()
        )
        round_registrations = registrations_df.loc[round_mask].copy()
        round_registrations["_points"] = pd.to_numeric(
            round_registrations["points"],
            errors="coerce",
        )
        scored = round_registrations[
            round_registrations["_points"].notna()
            & (round_registrations["_points"] >= 0)
            & (round_registrations["_points"] <= 300)
        ].sort_values("_points", ascending=False)

        if scored.empty:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "📊 Round leaderboard",
                f"No points have been recorded for {round_name} yet.",
                footer="AICC • Round points",
            ))
            return

        total_scored = len(scored)
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for position, (_, row) in enumerate(scored.head(10).iterrows(), 1):
            medal = medals[position - 1] if position <= len(medals) else "🔹"
            placement = str(row.get("rating", "")).strip()
            placement_text = f" · {placement}" if placement and placement != "nan" else ""
            points = float(row["_points"])
            points_text = f"{int(points) if points.is_integer() else points:g}/300"
            lines.append(
                f"{medal} **{position}.** {row['discord']} — **{points_text} pts**"
                f"{placement_text}"
            )

        embed = aicc_embed(
            ctx,
            f"📊 {round_name} · Top points",
            (
                f"Top 10 scores from this round. "
                f"Recorded points: **{total_scored}** participant(s)."
            ),
            footer="AICC • Round points leaderboard",
        )
        embed.add_field(
            name="Leaderboard",
            value="\n".join(lines),
            inline=False,
        )
        embed.add_field(
            name="📌 Scoring",
            value="Points are shown out of 300. Placement is stored in registrations.csv.",
            inline=False,
        )
        await ctx.reply(embed=embed)

    @commands.command(
        brief="Use !rating [round_name] or !rating [platform] [username]",
        help="View a user's rating progression across rounds.\n"
            "Syntax: `!rating` or `!rating [platform] [username]`\n"
            "View the top 10 points for a round with `!rating [round_name]`"
    )
    async def rating(self, ctx, *args):
        if not args:
            platform = "discord"
            username = str(ctx.author)
        else:
            requested_name = " ".join(args).strip()
            rounds_df = pd.read_csv(ROUNDS_CSV)
            known_rounds = rounds_df["name"].astype(str).str.strip().str.casefold()

            if requested_name.casefold() in set(known_rounds):
                await self._send_round_points_leaderboard(ctx, requested_name)
                return

            if len(args) != 2:
                await ctx.reply(embed=aicc_embed(
                    ctx,
                    "ℹ️ Rating usage",
                    (
                        "Use !rating for your own progression, "
                        "!rating [platform] [username] for another account, "
                        "or !rating [round_name] for a round leaderboard."
                    ),
                    footer="AICC • Rating tools",
                ))
                return

            platform, username = args
            if platform.lower() not in ["discord", "kaggle", "nitro"]:
                await ctx.reply(embed=aicc_embed(
                    ctx,
                    "⚠️ Invalid platform",
                    "Platform must be discord, nitro, or kaggle.",
                    footer="AICC • Rating tools",
                ))
                return
            platform = platform.lower()
    
    
        users_df = pd.read_csv(USERS_CSV)
        registrations_df = pd.read_csv(REGISTRATIONS_CSV)
    
        # Find the user
        user = users_df[
            users_df[platform].astype(str) == username
        ]
    
        if user.empty:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Account not linked",
                f"{platform.title()} user {username} is not linked.",
                footer="AICC • Rating tools",
            ))
            return
    
        user = user.iloc[0]
        discord_username = str(user["discord"])
    
        # Get all registrations for this user
        user_registrations = registrations_df[
            registrations_df["discord"].astype(str) == discord_username
        ]
    
        if user_registrations.empty:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "📈 No rating history",
                f"{username} has no registered rounds.",
                footer="AICC • Rating progression",
            ))
            return
    
        message = f"**Rating progression for {username}**\n\n"
    
        for _, row in user_registrations.iterrows():
            round_name = row["round"]
            rated = str(row["rated"])
    
            if rated == "rated":
                round_rating = str(row["rating"]).removesuffix(".0")
                points = row.get("points")
                numeric_points = pd.to_numeric(points, errors="coerce")
                points_value = (
                    f" · {int(numeric_points)}/300 pts"
                    if pd.notna(numeric_points)
                    else ""
                )
                message += (
                    f"🏁 {round_name} — **Rated** — {round_rating}{points_value}\n"
                )
            else:
                message += (
                    f"▫️ {round_name} — **Unrated**\n"
                )
    
        current_elo = user.get("elo", INITIAL_ELO)
        if pd.isna(current_elo):
            current_elo = INITIAL_ELO
        message += f"\n**Current ELO:** {float(current_elo):.0f}"

        embed = aicc_embed(
            ctx,
            f"📈 Rating progression · {username}",
            "Your round placements, points, and current ELO.",
            footer="AICC • Rating progression",
        )
        embed.add_field(
            name="Current ELO",
            value=f"**{float(current_elo):.0f}**",
            inline=True,
        )
        embed.add_field(
            name="Rounds",
            value=message.split("\n\n", 1)[1],
            inline=False,
        )
        await ctx.reply(embed=embed)

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
        if "elo" not in users_df.columns:
            users_df["elo"] = INITIAL_ELO
        users_df["elo"] = pd.to_numeric(
            users_df["elo"], errors="coerce"
        ).fillna(INITIAL_ELO)
    
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
            "rating": None,
            "points": None,
        }])
    
        registrations_df = pd.concat(
            [registrations_df, new_registration],
            ignore_index=True
        )
    
        registrations_df.to_csv(REGISTRATIONS_CSV, index=False)
        users_df.to_csv(USERS_CSV, index=False)
    
        await ctx.reply(
            f"You are registered for `{round_name}` ({rated})!"
        )

async def setup(bot):
    await bot.add_cog(User(bot))
