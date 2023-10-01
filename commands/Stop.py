from core import Interaction
import discord


async def go(interaction: Interaction):
    user = interaction.user
    bot = interaction.client
    await bot.db.set("UPDATE users SET active=False WHERE user_id=%s", user.id)
    emb = discord.Embed(
        title="⏹ Successfully Disconnected",
        description="I will not send you new messages.",
        colour=discord.Colour.green()
    )
    await interaction.response.send_message(embed=emb)