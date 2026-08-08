import os
import logging
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# ローカル開発用に .env を読み込む（Railway 等では環境変数で渡す想定）
load_dotenv()

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify-bot")

TOKEN = os.getenv("TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # 任意: 開発用にギルド単位でコマンドを同期したい場合に指定

if not TOKEN:
    logger.error("環境変数 TOKEN が設定されていません。Bot を起動できません。")
    raise SystemExit("TOKEN is required in environment variables")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # ロール付与に必要

bot = commands.Bot(command_prefix="!", intents=intents)

ROLE_NAME = "認証済み"
ROLE_NAME_GIJUTSU = "技術班"


class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ 認証する", style=discord.ButtonStyle.green, custom_id="verify_button")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        # interaction.user が Member である前提（サーバー内での操作）
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("このボタンはサーバー内でのみ使用できます。", ephemeral=True)
            return

        role = discord.utils.get(guild.roles, name=ROLE_NAME)
        if role is None:
            await interaction.response.send_message(f"「{ROLE_NAME}」ロールが見つかりません。", ephemeral=True)
            return

        member = guild.get_member(interaction.user.id) or interaction.user
        if role in getattr(member, "roles", []):
            await interaction.response.send_message("すでに認証済みです！", ephemeral=True)
            return

        try:
            await member.add_roles(role)
            await interaction.response.send_message("✅ 認証が完了しました！", ephemeral=True)
            logger.info(f"Assigned role '{ROLE_NAME}' to {member} ({member.id}) in guild {guild.name}")
        except discord.Forbidden:
            await interaction.response.send_message("権限が不足しています。管理者に連絡してください。", ephemeral=True)
            logger.exception("権限エラー: ロールを付与できませんでした。")
        except Exception:
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
            logger.exception("ロール付与中にエラーが発生しました。")


class GijutsuButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔧 技術班に参加する", style=discord.ButtonStyle.blurple, custom_id="gijutsu_button")
    async def gijutsu(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("このボタンはサーバー内でのみ使用できます。", ephemeral=True)
            return

        role = discord.utils.get(guild.roles, name=ROLE_NAME_GIJUTSU)
        if role is None:
            await interaction.response.send_message(f"「{ROLE_NAME_GIJUTSU}」ロールが見つかりません。", ephemeral=True)
            return

        member = guild.get_member(interaction.user.id) or interaction.user
        if role in getattr(member, "roles", []):
            await interaction.response.send_message("すでに技術班です！", ephemeral=True)
            return

        try:
            await member.add_roles(role)
            await interaction.response.send_message("🔧 技術班ロールを付与しました！", ephemeral=True)
            logger.info(f"Assigned role '{ROLE_NAME_GIJUTSU}' to {member} ({member.id}) in guild {guild.name}")
        except discord.Forbidden:
            await interaction.response.send_message("権限が不足しています。管理者に連絡してください。", ephemeral=True)
            logger.exception("権限エラー: ロールを付与できませんでした。")
        except Exception:
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
            logger.exception("ロール付与中にエラーが発生しました。")


@bot.event
async def on_ready():
    # persistent view を登録してボタンが再作成されなくても動くようにする
    bot.add_view(VerifyButton())
    bot.add_view(GijutsuButton())

    # コマンド同期（開発時は GUILD_ID を使うと即時反映される）
    try:
        if GUILD_ID:
            guild_obj = discord.Object(id=int(GUILD_ID))
            await bot.tree.sync(guild=guild_obj)
            logger.info(f"Synced commands to guild {GUILD_ID}")
        else:
            await bot.tree.sync()
            logger.info("Synced global commands")
    except Exception:
        logger.exception("コマンド同期に失敗しました。")

    logger.info(f"{bot.user} が起動しました！")


@bot.tree.command(name="setup", description="認証メッセージを送信します")
async def setup(interaction: discord.Interaction):
    embed = discord.Embed(
        title="サーバー認証",
        description="下のボタンを押して認証してください。",
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=embed, view=VerifyButton())


@bot.tree.command(name="setup_gijutsu", description="技術班ロール付与メッセージを送信します")
async def setup_gijutsu(interaction: discord.Interaction):
    embed = discord.Embed(
        title="技術班",
        description="技術班に参加する場合は下のボタンを押してください。",
        color=0x5865F2
    )
    await interaction.response.send_message(embed=embed, view=GijutsuButton())


def main():
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by keyboard interrupt")
    except Exception:
        logger.exception("Bot failed to run")


if __name__ == "__main__":
    main()