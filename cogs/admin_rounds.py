
import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import pandas as pd
from datetime import datetime, timezone
from views import DynamicTaskButton

USERS_CSV = "users.csv"
ROUNDS_CSV = "rounds.csv"
REGISTRATIONS_CSV = "registrations.csv"
ENTRIES_CSV = "entries.csv"

ADMIN_ROLE = "organizer"

class Rounds(commands.Cog, name="[ADMIN] Rounds"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        brief="Edit a round",
        help="Change information about a round.\n"
            "Syntax: `!edit_round [round_name] [field] [value]`\n"
            "Fields: `date`, `links`, `status`\n"
            "Date format: `DD/MM/YYYY`\n"
            "For multiple links, separate them with spaces.\n"
            "Status: `upcoming`, `started`, or `finished`\n"
            "Organizer only"
    )
    async def edit_round(self, ctx, round_name, field, *value):
        if not any(role.name == ADMIN_ROLE for role in ctx.author.roles):
            await ctx.reply(f"You need the `{ADMIN_ROLE}` role to use this command.")
            return
    
        if field not in ["date", "links", "status"]:
            await ctx.reply("Field must be `date`, `links`, or `status`.")
            return
    
        if not value:
            await ctx.reply("You must provide a new value.")
            return
    
        df = pd.read_csv(ROUNDS_CSV)
    
        mask = df["name"].astype(str) == round_name
    
        if not mask.any():
            await ctx.reply(f"Round `{round_name}` doesn't exist.")
            return
    
        # Change date
        if field == "date":
            try:
                new_date = datetime.strptime(
                    value[0], "%d/%m/%Y"
                ).strftime("%Y-%m-%d")
            except ValueError:
                await ctx.reply("Invalid date. Use `DD/MM/YYYY`.")
                return
    
            df.loc[mask, "date"] = new_date
    
        # Change links
        elif field == "links":
            df.loc[mask, "links"] = "|".join(value)
    
        # Change status
        elif field == "status":
            if value[0] not in ["upcoming", "started", "finished"]:
                await ctx.reply(
                    "Status must be `upcoming`, `started`, or `finished`."
                )
                return
    
            df.loc[mask, "status"] = value[0]
    
        df.to_csv(ROUNDS_CSV, index=False)
    
        await ctx.reply(
            f"✅ Updated `{field}` for round `{round_name}`."
        )

    @commands.command(
        brief="Start a round",
        help="Start a round and announce it in #announcements.\n"
            "Registered participants can press the button to receive the tasks.\n"
            "Syntax: `!start_round [round_name]`\n"
            "Organizer only"
    )
    async def start_round(self, ctx, round_name):
        if not any(role.name == ADMIN_ROLE for role in ctx.author.roles):
            await ctx.reply(f"You need the `{ADMIN_ROLE}` role to use this command.")
            return
    
        df = pd.read_csv(ROUNDS_CSV)
    
        round_row = df[
            (df["name"].astype(str) == round_name) &
            (df["status"] == "upcoming")
        ]
    
        if round_row.empty:
            await ctx.reply("That round doesn't exist or isn't upcoming.")
            return
    
        links = str(round_row.iloc[0]["links"]).split("|")
    
        # Change status to started
        df.loc[
            df["name"].astype(str) == round_name,
            "status"
        ] = "started"
    
        df.to_csv(ROUNDS_CSV, index=False)
    
        # Find #announcements
        announcements = discord.utils.get(
            ctx.guild.text_channels,
            name="announcements"
        )
    
        if announcements is None:
            await ctx.reply("I couldn't find the `#announcements` channel.")
            return
    
        view = discord.ui.View(timeout=None)
        view.add_item(DynamicTaskButton(round_name, links))

        # Send announcement with button
        await announcements.send(
            f"Participants registered for {round_name} can press the button below to receive the tasks.\n"
            "The time limit starts as soon as you click the button.",
            view=view
        )
    
        await ctx.reply(f"`{round_name}` has started!")

    @commands.command(
        brief="Create a round",
        help="Create a new round\n"
            "Syntax: `!create_round [round_name] [date] {...links]`\n"
            "Date format: `DD/MM/YYYY`\n"
            "Organizer only"
    )
    async def create_round(self, ctx, round_name, date, *links):
        if not any(role.name == ADMIN_ROLE for role in ctx.author.roles):
            await ctx.reply(f"You need the `{ADMIN_ROLE}` role to use this command.")
            return
    
        # Convert DD/MM/YYYY → YYYY-MM-DD
        try:
            date = datetime.strptime(date, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            await ctx.reply("Invalid date. Use `DD/MM/YYYY`.")
            return
    
        df = pd.read_csv(ROUNDS_CSV)
    
        # Don't allow duplicate rounds
        if round_name in df["name"].astype(str).values:
            await ctx.reply("That round already exists.")
            return
    
        new_round = pd.DataFrame([{
            "name": round_name,
            "date": date,
            "status": "upcoming",
            "links": " | ".join(links),
        }])
    
        df = pd.concat([df, new_round], ignore_index=True)
        df.to_csv(ROUNDS_CSV, index=False)
    
        await ctx.reply(
            f"Created round `{round_name}` on `{date}`!\n"
            f"Links: {links}"
        )
    
    @commands.command(
        brief="Bulk change ratings",
        help="Set ratings for participants using an attached CSV file.\n"
            "CSV must contain `round`, one of `discord`, `kaggle`, or `nitro`, and `rating` columns.\n"
            "Kaggle/Nitro usernames will be converted to Discord usernames using `users.csv`.\n"
            "Only participants registered as `rated` will be updated.\n"
            "Syntax: `!bulk_rate` with the CSV attached\n"
            "Use `!bulk_rate detailed` for a detailed results CSV.\n"
            "Organizer only"
    )
    async def bulk_rate(self, ctx, detailed=None):
        if not any(role.name == ADMIN_ROLE for role in ctx.author.roles):
            await ctx.reply(f"You need the `{ADMIN_ROLE}` role to use this command.")
            return
    
        if not ctx.message.attachments:
            await ctx.reply(
                "Attach a CSV file containing `round`, one of `discord/kaggle/nitro`, and `rating`."
            )
            return
    
        attachment = ctx.message.attachments[0]
    
        if not attachment.filename.lower().endswith(".csv"):
            await ctx.reply("The attached file must be a `.csv` file.")
            return
    
        try:
            await attachment.save("bulk_ratings.csv")
    
            ratings_df = pd.read_csv("bulk_ratings.csv")
            registrations_df = pd.read_csv(REGISTRATIONS_CSV)
            users_df = pd.read_csv(USERS_CSV)
            rounds_df = pd.read_csv(ROUNDS_CSV)
    
        except Exception as e:
            await ctx.reply(f"Could not read the CSV file: `{e}`")
            return
    
        # Determine which platform column is being used
        platforms = ["discord", "kaggle", "nitro"]
        present_platforms = [p for p in platforms if p in ratings_df.columns]
    
        if "round" not in ratings_df.columns or "rating" not in ratings_df.columns:
            os.remove("bulk_ratings.csv")
            await ctx.reply(
                "The CSV must contain `round`, one of `discord/kaggle/nitro`, "
                "and `rating`."
            )
            return
    
        if len(present_platforms) != 1:
            os.remove("bulk_ratings.csv")
            await ctx.reply(
                "The CSV must contain exactly one of: `discord`, `kaggle`, or `nitro`."
            )
            return
    
        platform = present_platforms[0]
    
        updated = 0
        not_registered = []
        unrated = []
        not_found = []
    
        for _, row in ratings_df.iterrows():
            round_name = str(row["round"])
            identifier = str(row[platform])
            rating = row["rating"]
    
            # Check that round exists
            if round_name not in rounds_df["name"].astype(str).values:
                not_found.append(
                    f"{identifier} ({round_name}) - round not found"
                )
                continue
    
            # Convert Kaggle/Nitro username to Discord username
            user = users_df[
                users_df[platform].astype(str) == identifier
            ]
    
            if user.empty:
                not_found.append(
                    f"{identifier} ({round_name})"
                )
                continue
    
            discord_username = str(user.iloc[0]["discord"])
    
            # Find participant in this round
            mask = (
                (registrations_df["round"].astype(str) == round_name) &
                (registrations_df["discord"].astype(str) == discord_username)
            )
    
            if not mask.any():
                not_registered.append(
                    f"{discord_username} ({round_name})"
                )
                continue
    
            # Only update rated participants
            rated_mask = mask & (
                registrations_df["rated"].astype(str) == "rated"
            )
    
            if not rated_mask.any():
                unrated.append(
                    f"{discord_username} ({round_name})"
                )
                continue
    
            # Update rating for this round
            registrations_df.loc[rated_mask, "rating"] = rating
    
            # Update current rating
            user_mask = (
                users_df["discord"].astype(str) == discord_username
            )
    
            users_df.loc[user_mask, "rating"] = rating
    
            updated += 1
    
        registrations_df.to_csv(REGISTRATIONS_CSV, index=False)
        users_df.to_csv(USERS_CSV, index=False)
    
        os.remove("bulk_ratings.csv")
    
        message = f"✅ Updated **{updated}** rated participant(s)."
    
        if unrated:
            message += (
                f"\n⚠️ **{len(unrated)}** participant(s) were registered as `unrated`."
            )
    
        if not_registered:
            message += (
                f"\n⚠️ **{len(not_registered)}** participant(s) were not registered."
            )
    
        if not_found:
            message += (
                f"\n⚠️ **{len(not_found)}** participant(s) were not found in `users.csv`."
            )
    
            message = f"✅ Updated **{updated}** rated participant(s)."
    
        if unrated:
            message += (
                f"\n⚠️ **{len(unrated)}** participant(s) were registered as `unrated`."
            )
    
        if not_registered:
            message += (
                f"\n⚠️ **{len(not_registered)}** participant(s) were not registered."
            )
    
        if not_found:
            message += (
                f"\n⚠️ **{len(not_found)}** participant(s) were not found in `users.csv`."
            )
    
        # Detailed results
        if detailed == "detailed":
            results = []
    
            for x in not_registered:
                results.append({
                    "status": "not_registered",
                    "entry": x
                })
    
            for x in unrated:
                results.append({
                    "status": "unrated",
                    "entry": x
                })
    
            for x in not_found:
                results.append({
                    "status": "not_found",
                    "entry": x
                })
    
            detailed_df = pd.DataFrame(
                results,
                columns=["status", "entry"]
            )
    
            detailed_df.to_csv("bulk_rate_results.csv", index=False)
    
            await ctx.reply(
                message + "\n📄 Detailed results:",
                file=discord.File("bulk_rate_results.csv")
            )
    
            os.remove("bulk_rate_results.csv")
    
        else:
            await ctx.reply(message)

async def setup(bot):
    await bot.add_cog(Rounds(bot))
