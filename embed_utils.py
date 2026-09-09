import discord


def aicc_embed(ctx, title, description, footer="AICC • Organizer tools"):
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.red(),
    )

    if ctx.bot.user:
        embed.set_author(
            name="AICC • Command Center",
            icon_url=ctx.bot.user.display_avatar.url,
        )

    embed.set_footer(text=footer)
    return embed
