import discord
from core import Interaction, Bot


CATEGORY_ID = 1157803933968900256


async def go(interaction: Interaction):
    await interaction.response.defer()
    bot = interaction.client
    user = interaction.user
    data = await bot.db.get("SELECT active, channel_id FROM users WHERE user_id=%s", user.id)
    channel = bot.get_channel(data[0][1]) if data else None

    if not channel:
        category: discord.CategoryChannel = interaction.guild.get_channel(CATEGORY_ID)
        permissions = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True)
        }
        channel = await category.create_text_channel(name=str(user), overwrites=permissions)
        await bot.db.set('''
            DELETE FROM users WHERE user_id=%s;
            INSERT INTO users(user_id, username, channel_id)
            VALUES (%s, %s, %s)
        ''', user.id, user.id, str(user), channel.id)
        await channel.send(
            f"> 🔎 {user.mention} I will send you bets on this channel. "
            f"Use the `/bookies` command to filter the bookmakers you are interested in."
        )

    else:
        if not data[0][0]:
            await bot.db.set("UPDATE users SET active=True WHERE user_id=%s", user.id)
        else:
            emb = discord.Embed(
                description="⚠ You have already activated the bot.",
                colour=discord.Colour.red()
            )
            return await interaction.followup.send(embed=emb)

    emb = discord.Embed(
        title="✅ Connected Successfully",
        description="I will send you new messages whenever a new bet comes up!",
        colour=discord.Colour.green()
    )
    await interaction.followup.send(embed=emb)


async def deleted_user_channel(channel_id: int, bot: Bot):
    await bot.db.set("DELETE FROM users WHERE channel_id=%s", channel_id)
