
import discord
from discord.ext import commands
import logging
import math
import os
import pandas as pd
from datetime import datetime, timezone
from views import DynamicTaskButton
from embed_utils import aicc_embed

USERS_CSV = "users.csv"
ROUNDS_CSV = "rounds.csv"
REGISTRATIONS_CSV = "registrations.csv"
ENTRIES_CSV = "entries.csv"

ADMIN_ROLE = "organizer"
ADMIN_ROLES = {"organizer", "Bot admin"}
ADMIN_ROLES_TEXT = "`organizer` or `Bot admin`"
INITIAL_ELO = 1000
ELO_K_FACTOR = 32
MAX_POINTS = 300

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
        if not any(role.name in ADMIN_ROLES for role in ctx.author.roles):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🔴 Organizer command",
                f"You need one of the {ADMIN_ROLES_TEXT} roles to use this command.",
            ))
            return
    
        if field not in ["date", "links", "status"]:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Invalid field",
                "Field must be `date`, `links`, or `status`.",
            ))
            return
    
        if not value:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Missing value",
                "You must provide a new value for the selected field.",
            ))
            return
    
        df = pd.read_csv(ROUNDS_CSV)
    
        mask = df["name"].astype(str) == round_name
    
        if not mask.any():
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Round not found",
                f"Round `{round_name}` doesn't exist.",
            ))
            return

        df[field] = df[field].astype("object")
        
        # Change date
        if field == "date":
            try:
                new_date = datetime.strptime(
                    value[0], "%d/%m/%Y"
                ).strftime("%Y-%m-%d")
            except ValueError:
                await ctx.reply(embed=aicc_embed(
                    ctx,
                    "⚠️ Invalid date",
                    "Use the format `DD/MM/YYYY`.",
                ))
                return
    
            df.loc[mask, "date"] = new_date
    
        # Change links
        elif field == "links":
            df.loc[mask, "links"] = "|".join(value)
    
        # Change status
        elif field == "status":
            if value[0] not in ["upcoming", "started", "finished"]:
                await ctx.reply(embed=aicc_embed(
                    ctx,
                    "⚠️ Invalid status",
                    "Status must be `upcoming`, `started`, or `finished`.",
                ))
                return
    
            df.loc[mask, "status"] = value[0]
    
        df.to_csv(ROUNDS_CSV, index=False)
    
        await ctx.reply(embed=aicc_embed(
            ctx,
            "✅ Round updated",
            f"Updated `{field}` for round `{round_name}`.",
        ))

    @commands.command(
        brief="Start a round",
        help="Start a round and announce it in #announcements.\n"
            "Registered participants can press the button to receive the tasks.\n"
            "Syntax: `!start_round [round_name]`\n"
            "Organizer only"
    )
    async def start_round(self, ctx, round_name):
        if not any(role.name in ADMIN_ROLES for role in ctx.author.roles):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🔴 Organizer command",
                f"You need one of the {ADMIN_ROLES_TEXT} roles to use this command.",
            ))
            return
    
        df = pd.read_csv(ROUNDS_CSV)
    
        round_row = df[
            (df["name"].astype(str) == round_name) &
            (df["status"] == "upcoming")
        ]
    
        if round_row.empty:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Round unavailable",
                "That round doesn't exist or isn't upcoming.",
            ))
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
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Channel not found",
                "I couldn't find the `#announcements` channel.",
            ))
            return
    
        view = discord.ui.View(timeout=None)
        view.add_item(DynamicTaskButton(round_name, links))

        # Send announcement with button
        announcement_embed = aicc_embed(
            ctx,
            f"🏆 {round_name} has started",
            (
                f"Participants registered for `{round_name}` can press the button below "
                "to receive their tasks.\n\n"
                "⏱️ The time limit starts as soon as you click the button."
            ),
            footer="AICC • Round announcement",
        )
        await announcements.send(embed=announcement_embed, view=view)
    
        await ctx.reply(embed=aicc_embed(
            ctx,
            "✅ Round started",
            f"`{round_name}` has been started and announced in #announcements.",
        ))

    @commands.command(
        brief="Create a round",
        help="Create a new round\n"
            "Syntax: `!create_round [round_name] [date] {...links]`\n"
            "Date format: `DD/MM/YYYY`\n"
            "Organizer only"
    )
    async def create_round(self, ctx, round_name, date, *links):
        if not any(role.name in ADMIN_ROLES for role in ctx.author.roles):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🔴 Organizer command",
                f"You need one of the {ADMIN_ROLES_TEXT} roles to use this command.",
            ))
            return
    
        # Convert DD/MM/YYYY → YYYY-MM-DD
        try:
            date = datetime.strptime(date, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Invalid date",
                "Use the format `DD/MM/YYYY`.",
            ))
            return
    
        df = pd.read_csv(ROUNDS_CSV)
    
        # Don't allow duplicate rounds
        if round_name in df["name"].astype(str).values:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Round already exists",
                f"The round `{round_name}` already exists.",
            ))
            return
    
        new_round = pd.DataFrame([{
            "name": round_name,
            "date": date,
            "status": "upcoming",
            "links": " | ".join(links),
        }])
    
        df = pd.concat([df, new_round], ignore_index=True)
        df.to_csv(ROUNDS_CSV, index=False)
    
        await ctx.reply(embed=aicc_embed(
            ctx,
            "✅ Round created",
            (
                f"Created round `{round_name}` on `{date}`.\n"
                f"🔗 Links: {', '.join(links) if links else 'None'}"
            ),
        ))
    
    @commands.command(
        brief="Calculate round ELO",
        help=(
            "Calculate Codeforces-style ELO for rated participants in a finished round.\n"
            "Fill each rated registration points value from 0 to 300 first.\n"
            "The rating column is filled with placement, such as 2/10.\n"
            "Syntax: !elo [round_name]\n"
            "Organizer only"
        ),
    )
    async def elo(self, ctx, *, round_name):
        if not any(role.name in ADMIN_ROLES for role in ctx.author.roles):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🔴 Organizer command",
                f"You need one of the {ADMIN_ROLES_TEXT} roles to use this command.",
            ))
            return

        registrations_df = pd.read_csv(REGISTRATIONS_CSV)
        users_df = pd.read_csv(USERS_CSV)

        if "points" not in registrations_df.columns:
            registrations_df["points"] = None
        if "rating" not in registrations_df.columns:
            registrations_df["rating"] = None
        registrations_df["rating"] = registrations_df["rating"].astype(object)
        if "elo" not in users_df.columns:
            users_df["elo"] = INITIAL_ELO

        round_name = round_name.strip()
        round_mask = registrations_df["round"].astype(str).str.strip() == round_name
        rated_mask = round_mask & (
            registrations_df["rated"].astype(str).str.strip().str.lower() == "rated"
        )
        rated_registrations = registrations_df.loc[rated_mask].copy()

        if rated_registrations.empty:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ No rated participants",
                f"No participants marked rated were found for {round_name}.",
            ))
            return

        rated_registrations["_points"] = pd.to_numeric(
            rated_registrations["points"],
            errors="coerce",
        )
        invalid_points = rated_registrations[
            rated_registrations["_points"].isna()
            | (rated_registrations["_points"] < 0)
            | (rated_registrations["_points"] > MAX_POINTS)
        ]

        if not invalid_points.empty:
            invalid_names = [
                str(row["discord"])
                for _, row in invalid_points.head(20).iterrows()
            ]
            more = len(invalid_points) - len(invalid_names)
            if more > 0:
                invalid_names.append(f"...and {more} more")

            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Points are required",
                (
                    "Enter a valid points value from 0 to 300 for every rated "
                    f"participant in registrations.csv before running !elo.\n\n"
                    "Missing or invalid: " + ", ".join(invalid_names)
                ),
            ))
            return

        users_df["elo"] = pd.to_numeric(users_df["elo"], errors="coerce").fillna(
            INITIAL_ELO
        )
        users_df["elo"] = users_df["elo"].clip(lower=0)

        participants = []
        for registration_index, row in rated_registrations.iterrows():
            discord_username = str(row["discord"]).strip()
            matching_user = users_df[
                users_df["discord"].astype(str).str.strip() == discord_username
            ]
            current_elo = (
                float(matching_user.iloc[0]["elo"])
                if not matching_user.empty
                else INITIAL_ELO
            )
            participants.append({
                "registration_index": registration_index,
                "discord": discord_username,
                "points": float(row["_points"]),
                "elo": current_elo,
            })

        participant_count = len(participants)
        participants.sort(key=lambda participant: participant["points"], reverse=True)

        for participant in participants:
            participant["rank"] = 1 + sum(
                other["points"] > participant["points"]
                for other in participants
            )

        for participant in participants:
            if participant_count == 1:
                expected_score = 0.5
                actual_score = 0.5
            else:
                expected_score = sum(
                    1 / (
                        1
                        + 10 ** ((other["elo"] - participant["elo"]) / 400)
                    )
                    for other in participants
                    if other is not participant
                ) / (participant_count - 1)
                actual_score = sum(
                    1
                    if participant["points"] > other["points"]
                    else 0.5
                    if participant["points"] == other["points"]
                    else 0
                    for other in participants
                    if other is not participant
                ) / (participant_count - 1)

            participant["new_elo"] = max(
                0,
                round(
                    participant["elo"]
                    + ELO_K_FACTOR * (actual_score - expected_score)
                ),
            )

        for participant in participants:
            registration_index = participant["registration_index"]
            points = participant["points"]
            registrations_df.loc[registration_index, "points"] = (
                int(points) if points.is_integer() else round(points, 2)
            )
            registrations_df.loc[registration_index, "rating"] = (
                f"{participant['rank']}/{participant_count}"
            )

            user_mask = (
                users_df["discord"].astype(str).str.strip()
                == participant["discord"]
            )
            if user_mask.any():
                users_df.loc[user_mask, "elo"] = participant["new_elo"]
            else:
                users_df = pd.concat(
                    [
                        users_df,
                        pd.DataFrame([{
                            "discord": participant["discord"],
                            "kaggle": "None",
                            "nitro": "None",
                            "rating": "unrated",
                            "elo": participant["new_elo"],
                        }]),
                    ],
                    ignore_index=True,
                )

        registrations_df.to_csv(REGISTRATIONS_CSV, index=False)
        users_df.to_csv(USERS_CSV, index=False)

        result_lines = [
            (
                f"{participant['rank']}/{participant_count} "
                f"{participant['discord']} · "
                f"{int(participant['points'])}/{MAX_POINTS} pts · "
                f"{round(participant['elo'])} → {participant['new_elo']} ELO"
            )
            for participant in participants
        ]
        results_text = "\n".join(result_lines)
        if len(results_text) > 3900:
            results_text = results_text[:3890] + "\n..."

        result_embed = aicc_embed(
            ctx,
            f"🏆 ELO calculated · {round_name}",
            (
                f"Processed **{participant_count}** rated participant(s).\n"
                "Placements and points were saved to registrations.csv; current ELOs "
                "were saved to users.csv."
            ),
            footer="AICC • Codeforces-style ELO · K-factor 32",
        )
        result_embed.add_field(name="Results", value=results_text, inline=False)
        await ctx.reply(embed=result_embed)

    @commands.command(
        brief="Import points from lb.csv",
        help=(
            "Upload lb.csv with discord and points columns to fill round points.\n"
            "Points must be between 0 and 300.\n"
            "Syntax: !bulk_pts [round_name] with lb.csv attached.\n"
            "Organizer only"
        ),
    )
    async def bulk_pts(self, ctx, *, round_name=None):
        if not any(role.name in ADMIN_ROLES for role in ctx.author.roles):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🔴 Organizer command",
                f"You need one of the {ADMIN_ROLES_TEXT} roles to use this command.",
            ))
            return

        if not ctx.message.attachments:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "📊 Bulk points",
                "Attach lb.csv with the columns discord and points.",
            ))
            return

        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith(".csv"):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Invalid attachment",
                "The attached file must be a CSV file, preferably named lb.csv.",
            ))
            return

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        points_file = os.path.join(project_root, "bulk_points.csv")

        try:
            await attachment.save(points_file)
            points_df = pd.read_csv(points_file)
        except Exception as error:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🔴 CSV read error",
                f"Could not read lb.csv: {error}",
            ))
            return
        finally:
            if os.path.isfile(points_file):
                os.remove(points_file)

        required_columns = {"discord", "points"}
        if not required_columns.issubset(points_df.columns):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Invalid lb.csv",
                "The file must contain these columns: discord, points.",
            ))
            return

        registrations_df = pd.read_csv(REGISTRATIONS_CSV)
        if "points" not in registrations_df.columns:
            registrations_df["points"] = None
        registrations_df["points"] = registrations_df["points"].astype(object)

        points_df["_points"] = pd.to_numeric(
            points_df["points"],
            errors="coerce",
        )
        points_df["_discord"] = points_df["discord"].astype(str).str.strip()
        points_df = points_df[points_df["_discord"].str.lower() != "nan"]

        invalid_points = points_df[
            points_df["_points"].isna()
            | (points_df["_points"] < 0)
            | (points_df["_points"] > MAX_POINTS)
        ]
        if not invalid_points.empty:
            invalid_names = ", ".join(
                str(name)
                for name in invalid_points["_discord"].head(20)
            )
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Invalid points",
                (
                    f"Every points value must be between 0 and {MAX_POINTS}. "
                    f"Invalid entries: {invalid_names}"
                ),
            ))
            return

        registrations_df["_round_key"] = (
            registrations_df["round"].astype(str).str.strip().str.casefold()
        )
        registrations_df["_discord_key"] = (
            registrations_df["discord"].astype(str).str.strip().str.casefold()
        )

        uploaded_users = set(points_df["_discord"].str.casefold())
        candidate_rounds = sorted(
            registrations_df.loc[
                registrations_df["_discord_key"].isin(uploaded_users),
                "round",
            ].astype(str).str.strip().unique()
        )

        if round_name:
            requested_round = round_name.strip()
            matching_rounds = [
                value
                for value in candidate_rounds
                if value.casefold() == requested_round.casefold()
            ]
            if not matching_rounds:
                await ctx.reply(embed=aicc_embed(
                    ctx,
                    "⚠️ Round not found",
                    (
                        f"No uploaded user is registered for {requested_round}. "
                        "Check the round name and try again."
                    ),
                ))
                return
            target_round = matching_rounds[0]
        elif len(candidate_rounds) == 1:
            target_round = candidate_rounds[0]
        elif not candidate_rounds:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ No matching registrations",
                "None of the Discord users in lb.csv are registered for a round.",
            ))
            return
        else:
            round_list = ", ".join(candidate_rounds[:20])
            await ctx.reply(embed=aicc_embed(
                ctx,
                "ℹ️ Round name required",
                (
                    "These uploaded users appear in multiple rounds: "
                    f"{round_list}\n\n"
                    "Run !bulk_pts [round_name] with the same lb.csv attached."
                ),
            ))
            return

        updated = 0
        not_registered = []
        for _, row in points_df.iterrows():
            discord_username = row["_discord"]
            registration_mask = (
                (registrations_df["_round_key"] == target_round.casefold())
                & (registrations_df["_discord_key"] == discord_username.casefold())
            )
            if not registration_mask.any():
                not_registered.append(discord_username)
                continue

            points = float(row["_points"])
            registrations_df.loc[registration_mask, "points"] = (
                int(points) if points.is_integer() else round(points, 2)
            )
            updated += int(registration_mask.sum())

        registrations_df.drop(
            columns=["_round_key", "_discord_key"],
            inplace=True,
        )
        registrations_df.to_csv(REGISTRATIONS_CSV, index=False)

        description = (
            f"Updated **{updated}** registration(s) in **{target_round}**.\n"
            "Points were saved to registrations.csv."
        )
        if not_registered:
            description += (
                "\n\nNot registered in this round: "
                + ", ".join(not_registered[:20])
            )

        await ctx.reply(embed=aicc_embed(
            ctx,
            f"✅ Points imported · {target_round}",
            description,
            footer="AICC • Bulk points import",
        ))

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
        if not any(role.name in ADMIN_ROLES for role in ctx.author.roles):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🔴 Organizer command",
                f"You need one of the {ADMIN_ROLES_TEXT} roles to use this command.",
            ))
            return
    
        if not ctx.message.attachments:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "📊 Bulk rating",
                "Attach a CSV containing `round`, one of `discord/kaggle/nitro`, and `rating`.",
            ))
            return
    
        attachment = ctx.message.attachments[0]
    
        if not attachment.filename.lower().endswith(".csv"):
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Invalid attachment",
                "The attached file must be a `.csv` file.",
            ))
            return
    
        try:
            await attachment.save("bulk_ratings.csv")
    
            ratings_df = pd.read_csv("bulk_ratings.csv")
            registrations_df = pd.read_csv(REGISTRATIONS_CSV)
            users_df = pd.read_csv(USERS_CSV)
            rounds_df = pd.read_csv(ROUNDS_CSV)
    
        except Exception as e:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "🔴 CSV read error",
                f"Could not read the CSV file: `{e}`",
            ))
            return
    
        # Determine which platform column is being used
        platforms = ["discord", "kaggle", "nitro"]
        present_platforms = [p for p in platforms if p in ratings_df.columns]
    
        if "round" not in ratings_df.columns or "rating" not in ratings_df.columns:
            os.remove("bulk_ratings.csv")
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Invalid CSV columns",
                "The CSV must contain `round`, one of `discord/kaggle/nitro`, and `rating`.",
            ))
            return
    
        if len(present_platforms) != 1:
            os.remove("bulk_ratings.csv")
            await ctx.reply(embed=aicc_embed(
                ctx,
                "⚠️ Invalid platform column",
                "The CSV must contain exactly one of: `discord`, `kaggle`, or `nitro`.",
            ))
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
                embed=aicc_embed(
                    ctx,
                    "📊 Bulk rating complete",
                    message + "\n\n📄 Detailed results are attached below.",
                ),
                file=discord.File("bulk_rate_results.csv")
            )
    
            os.remove("bulk_rate_results.csv")
    
        else:
            await ctx.reply(embed=aicc_embed(
                ctx,
                "📊 Bulk rating complete",
                message,
            ))

async def setup(bot):
    await bot.add_cog(Rounds(bot))
