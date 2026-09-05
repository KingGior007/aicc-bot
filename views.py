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

class TaskButton(discord.ui.View):
    def __init__(self, round_name, links):
        super().__init__(timeout=None)
        self.round_name = round_name
        self.links = links

    @discord.ui.button(
        label="Receive Tasks",
        style=discord.ButtonStyle.primary
    )
    async def receive_tasks(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        registrations_df = pd.read_csv(REGISTRATIONS_CSV)
        entries_df = pd.read_csv(ENTRIES_CSV)

        discord_username = str(interaction.user)

        registered = (
            (registrations_df["round"].astype(str) == self.round_name) &
            (registrations_df["discord"].astype(str) == discord_username)
        ).any()

        if not registered:
            await interaction.response.send_message(
                "You are not registered for this round.\n"
                "Time limit not started.",
                ephemeral=True
            )
            return

        # Record when the participant received the tasks
        entry = pd.DataFrame([{
            "round": self.round_name,
            "discord": discord_username,
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }])

        entries_df = pd.concat(
            [entries_df, entry],
            ignore_index=True
        )

        entries_df.to_csv(ENTRIES_CSV, index=False)

        message = "**Tasks:**\n" + "\n".join(
            f"{i+1}. {link}" for i, link in enumerate(self.links)
        )

        await interaction.response.send_message(
            message,
            ephemeral=True
        )

class TaskSubmissionModal(discord.ui.Modal, title="Task Submission"):

    task_name = discord.ui.TextInput(
        label="Task Name",
        placeholder="Enter the task name",
        required=True,
        max_length=100
    )

    category = discord.ui.TextInput(
        label="Category",
        placeholder="suggestion or submission",
        required=True,
        max_length=20
    )

    problem_type = discord.ui.TextInput(
        label="Problem Type",
        placeholder="CV, NLP, audio, ML (multiple allowed)",
        required=True,
        max_length=100
    )

    description = discord.ui.TextInput(
        label="Brief Description",
        placeholder="Briefly describe the task...",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):

        category = self.category.value.lower().strip()

        if category not in ["suggestion", "submission"]:
            await interaction.response.send_message(
                "Category must be `suggestion` or `submission`.",
                ephemeral=True
            )
            return

        problem_types = [
            x.strip().lower()
            for x in self.problem_type.value.split(",")
        ]

        valid_types = {"cv", "nlp", "audio", "ml"}

        if not all(x in valid_types for x in problem_types):
            await interaction.response.send_message(
                "Problem types must be `CV`, `NLP`, `audio`, or `ML`.",
                ephemeral=True
            )
            return

        problem_type_display = ", ".join(
            x.upper() if x in ["cv", "nlp", "ml"] else x
            for x in problem_types
        )

        thread_name = f'{category} - "{self.task_name.value}"'

        # Create the private thread in the channel where the button was sent
        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread
        )

        # Add the person who submitted it
        await thread.add_user(interaction.user)

        # Find Problem Review Team role
        review_role = discord.utils.get(
            interaction.guild.roles,
            name="Problem Review Team"
        )

        role_mention = (
            review_role.mention
            if review_role
            else "@Problem Review Team"
        )

        message = (
            f"Task Name: {self.task_name.value}\n"
            f"Problem Type: {problem_type_display}\n"
            f"Brief Description: {self.description.value}\n\n"
            f"{interaction.user.mention} {role_mention}"
        )

        await thread.send(message)

        await interaction.response.send_message(
            f"Your {category} has been submitted!",
            ephemeral=True
        )


class TaskSubmissionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Submit",
        style=discord.ButtonStyle.primary
    )
    async def submit_task(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            TaskSubmissionModal()
        )
