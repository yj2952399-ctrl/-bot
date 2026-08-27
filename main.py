import os
import logging
import datetime
import random
import discord
from discord.ext import commands
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify-bot")
TOKEN = os.getenv("TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
LOG_CHANNEL_ID = 1540259565503774790
if not TOKEN:
    logger.error("環境変数 TOKEN が設定されていません。Bot を起動できません。")
    raise SystemExit("TOKEN is required in environment variables")
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ========== ロール名 ==========
ROLE_NAME_VERIFIED = "認証済み"
ROLE_NAME_GIJUTSU = "技術班"   #このコマンド使わないでね　ショップで買う制度にしてるから
ROLE_NAME_BRAWL = "ブロスタ勢"

# ========== セキュリティ設定 ==========
MIN_ACCOUNT_AGE_DAYS = 1
MIN_MEMBER_MINUTES = 1
COOLDOWN_SECONDS = 10
MAX_ATTEMPTS = 3
TIMEOUT_DURATION_SEC = 24 * 60 * 60

# ========== 状態管理 ==========
cooldown = {}
attempts = {}
last_verified_time = None

# ========== 色分け判定 ==========
def get_time_diff_info(prev_time: float | None, curr_time: float) -> dict:
    global last_verified_time
    if prev_time is None:
        diff_sec = 999999
    else:
        diff_sec = max(0, curr_time - prev_time)
    if diff_sec > 120:
        color = discord.Color.from_rgb(25, 180, 100)
        level = "🟢 安全"
        note = "完全に正常な範囲"
    elif diff_sec > 90:
        color = discord.Color.from_rgb(80, 190, 90)
        level = "🟢 安全"
        note = "問題なし"
    elif diff_sec > 60:
        color = discord.Color.from_rgb(150, 200, 70)
        level = "🟡 正常範囲"
        note = "許容範囲内"
    elif diff_sec > 45:
        color = discord.Color.from_rgb(210, 210, 50)
        level = "🟡 やや速い"
        note = "特に問題なし"
    elif diff_sec > 30:
        color = discord.Color.from_rgb(240, 180, 50)
        level = "🟠 速め"
        note = "稀に発生、監視のみ"
    elif diff_sec > 20:
        color = discord.Color.from_rgb(245, 140, 60)
        level = "🟠 速い"
        note = "連続認証の可能性あり"
    elif diff_sec > 15:
        color = discord.Color.from_rgb(250, 100, 70)
        level = "🔴 非常に速い"
        note = "手動でも可能、確認推奨"
    else:
        color = discord.Color.from_rgb(200, 30, 80)
        level = "🔴🔴 極めて速い"
        note = "BOT/荒らしの可能性大"
    if diff_sec < 60:
        diff_str = f"{int(diff_sec)}秒"
    elif diff_sec < 3600:
        diff_str = f"{int(diff_sec//60)}分 {int(diff_sec%60)}秒"
    else:
        diff_str = f"{round(diff_sec/3600, 1)}時間"
    return {
        "diff_sec": None if prev_time is None else round(diff_sec),
        "diff_str": "初回認証" if prev_time is None else diff_str,
        "color": color,
        "level": level,
        "note": note,
    }

# ========== 管理者用ボタン ==========
class QuickActionView(discord.ui.View):
    def __init__(self, target_member_id: int):
        super().__init__(timeout=None)
        self.target_member_id = target_member_id
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return (
            interaction.user.guild_permissions.administrator
            or interaction.user.id == interaction.guild.owner_id
        )
    @discord.ui.button(label="⏱ 1日タイムアウト", style=discord.ButtonStyle.secondary)
    async def timeout_1d(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.guild.get_member(self.target_member_id)
        if not member:
            await interaction.response.send_message("❌ メンバーが見つかりません（退出済み）", ephemeral=True)
            return
        try:
            until = discord.utils.utcnow() + datetime.timedelta(seconds=TIMEOUT_DURATION_SEC)
            await member.edit(timed_out_until=until, reason="認証ログからの管理者操作")
            await interaction.response.send_message(f"✅ {member.mention} に1日タイムアウトを付与しました", ephemeral=True)
            logger.info(f"管理者 {interaction.user} → {member} 1day timeout")
        except Exception as e:
            await interaction.response.send_message(f"❌ 失敗: {e}", ephemeral=True)
    @discord.ui.button(label="👢 キック", style=discord.ButtonStyle.primary)
    async def kick_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.guild.get_member(self.target_member_id)
        if not member:
            await interaction.response.send_message("❌ メンバーが見つかりません", ephemeral=True)
            return
        try:
            await member.kick(reason="認証ログからの管理者操作")
            await interaction.response.send_message(f"✅ {member.mention} をキックしました", ephemeral=True)
            logger.info(f"管理者 {interaction.user} → {member} kick")
        except Exception as e:
            await interaction.response.send_message(f"❌ 失敗: {e}", ephemeral=True)
    @discord.ui.button(label="🔨 BAN", style=discord.ButtonStyle.danger)
    async def ban_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.guild.ban(
                discord.Object(id=self.target_member_id),
                reason="認証ログからの管理者操作",
                delete_message_seconds=0,
            )
            await interaction.response.send_message(f"✅ <@{self.target_member_id}> をBANしました", ephemeral=True)
            logger.info(f"管理者 {interaction.user} → ID:{self.target_member_id} BAN")
        except Exception as e:
            await interaction.response.send_message(f"❌ 失敗: {e}", ephemeral=True)

# ========== ✅ 修正版：条件チェック ==========
def is_verified(member: discord.Member) -> bool:
    return any(role.name == ROLE_NAME_VERIFIED for role in member.roles)

async def check_restrictions(interaction: discord.Interaction) -> tuple[bool, str]:
    user = interaction.user
    now = datetime.datetime.now(datetime.timezone.utc)
    account_age_days = (now - user.created_at).days
    if account_age_days < MIN_ACCOUNT_AGE_DAYS:
        return False, (
            f"⚠️ アカウント作成から{MIN_ACCOUNT_AGE_DAYS}日以上経過していません。\n"
            f"作成日: {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    if not isinstance(user, discord.Member) or user.joined_at is None:
        return False, "⚠️ 参加時間の取得に失敗しました。"
    wait_sec = (now - user.joined_at).total_seconds()
    if wait_sec < MIN_MEMBER_MINUTES * 60:
        return False, (
            f"⚠️ サーバー参加から{MIN_MEMBER_MINUTES}分以上経過していないため認証できません。\n"
            f"あと約{max(0, MIN_MEMBER_MINUTES * 60 - int(wait_sec))}秒お待ちください。"
        )
    uid = user.id
    # ✅ クールダウンチェック
    if uid in cooldown:
        elapsed = now.timestamp() - cooldown[uid]
        if elapsed < COOLDOWN_SECONDS:
            return False, f"⚠️ 連続して操作できません。あと{int(COOLDOWN_SECONDS - elapsed)}秒お待ちください。"
    # ✅ 試行回数チェック
    if attempts.get(uid, 0) >= MAX_ATTEMPTS:
        return False, "⛔ 連続して失敗しました。しばらくしてから再試行してください。"
    return True, ""

def record_attempt(uid: int, success: bool):
    cooldown[uid] = datetime.datetime.now(datetime.timezone.utc).timestamp()
    attempts[uid] = 0 if success else attempts.get(uid, 0) + 1

# ========== ログ作成 ==========
def make_log_embed(member: discord.Member) -> tuple[discord.Embed, discord.ui.View]:
    global last_verified_time
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now_ts = now_dt.timestamp()
    diff_info = get_time_diff_info(last_verified_time, now_ts)
    last_verified_time = now_ts
    embed = discord.Embed(
        title="✅ 認証完了【実験環境】",
        color=diff_info["color"],
        timestamp=now_dt,
    )
    embed.add_field(name="👤 ユーザー", value=member.mention, inline=True)
    embed.add_field(name="🆔 ユーザーID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="📅 アカウント作成日時", value=member.created_at.strftime('%Y-%m-%d %H:%M:%S'), inline=True)
    embed.add_field(name="📥 サーバー参加日時", value=(member.joined_at.strftime('%Y-%m-%d %H:%M:%S') if member.joined_at else "不明"), inline=True)
    embed.add_field(name="⏱ 前回認証との時間差", value=f"**{diff_info['diff_str']}**\n{diff_info['level']} — {diff_info['note']}", inline=False)
    embed.add_field(
        name="🔬 実験用：IP/トークン記録欄",
        value=(
            "🌐 IPアドレス: Discord API仕様上取得不可\n"
            "🔑 トークン: 認証APIの設計上取得不可\n"
            "📌 本人確認キー: 上記ユーザーID・作成日時・参加日時を一意識別子として使用"
        ),
        inline=False,
    )
    embed.set_footer(text=f"判定基準: 🔬実験用｜緑=正常→黄=速め→赤=要確認｜前回差:{diff_info['diff_str']}")
    view = QuickActionView(member.id)
    return embed, view

async def send_log(member: discord.Member):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        logger.error(f"ログチャンネルID {LOG_CHANNEL_ID} が見つかりません")
        return
    embed, view = make_log_embed(member)
    try:
        await log_channel.send(embed=embed, view=view)
        logger.info(f"ログ送信完了: {member}")
    except Exception as e:
        logger.exception(f"ログ送信失敗: {e}")

# ========== 認証モーダル ==========
class CaptchaModal(discord.ui.Modal, title="🧮 人間であることの証明"):
    def __init__(self, a: int, b: int):
        super().__init__()
        self.a = a
        self.b = b
        self.correct_answer = a + b
        self.answer_input = discord.ui.TextInput(
            label=f"{a} + {b} = ?",
            placeholder="答えの数値を半角で入力",
            min_length=1, max_length=10, required=True
        )
        self.add_item(self.answer_input)
    async def on_submit(self, interaction: discord.Interaction):
        user_answer = self.answer_input.value.strip()
        ok, reason = await check_restrictions(interaction)
        if not ok:
            # ✅ 条件不十分・クールダウンの場合は失敗カウントしない
            await interaction.response.send_message(reason, ephemeral=True)
            return
        if not user_answer.isdigit() or int(user_answer) != self.correct_answer:
            record_attempt(interaction.user.id, success=False)
            await interaction.response.send_message("❌ 答えが違います。もう一度ボタンを押してやり直してください。", ephemeral=True)
            logger.warning(f"証明失敗: {interaction.user} — 不正解")
            return
        record_attempt(interaction.user.id, success=True)
        guild = interaction.guild
        member = guild.get_member(interaction.user.id) or interaction.user
        role = discord.utils.get(guild.roles, name=ROLE_NAME_VERIFIED)
        if role in getattr(member, "roles", []):
            await interaction.response.send_message("✅ すでに認証済みです！", ephemeral=True)
            return
        try:
            await member.add_roles(role)
            await interaction.response.send_message(
                "✅ 認証が完了しました！\nこれで「技術班」「ブロスタ勢」のロールも取得できます。",
                ephemeral=True
            )
            await send_log(member)
        except Exception as e:
            await interaction.response.send_message("❌ エラーが発生しました。管理者に連絡してください。", ephemeral=True)
            logger.exception(f"ロール付与エラー: {e}")

# ========== 認証ボタン ==========
class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="✅ 認証する", style=discord.ButtonStyle.green, custom_id="verify_button")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("このボタンはサーバー内でのみ使用できます。", ephemeral=True)
            return
        role = discord.utils.get(guild.roles, name=ROLE_NAME_VERIFIED)
        if role is None:
            await interaction.response.send_message(f"「{ROLE_NAME_VERIFIED}」ロールが見つかりません。", ephemeral=True)
            return
        member = guild.get_member(interaction.user.id) or interaction.user
        if role in getattr(member, "roles", []):
            await interaction.response.send_message("✅ すでに認証済みです！", ephemeral=True)
            return
        ok, reason = await check_restrictions(interaction)
        if not ok:
            # ✅ 条件不十分・クールダウンではじかれた → 失敗カウントしない
            await interaction.response.send_message(reason, ephemeral=True)
            logger.warning(f"認証拒否: {member} — {reason}")
            return
        a = random.randint(5, 15)
        b = random.randint(5, 15)
        modal = CaptchaModal(a, b)
        await interaction.response.send_modal(modal)

# ========== 技術班ボタン ==========
class GijutsuButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="🔧 技術班に参加する", style=discord.ButtonStyle.blurple, custom_id="gijutsu_button")
    async def gijutsu(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = guild.get_member(interaction.user.id) or interaction.user
        if not is_verified(member):
            await interaction.response.send_message("⛔ 先に「✅ 認証する」ボタンで認証を完了してください。", ephemeral=True)
            logger.warning(f"未認証: {member}")
            return
        role = discord.utils.get(guild.roles, name=ROLE_NAME_GIJUTSU)
        if role is None:
            await interaction.response.send_message(f"「{ROLE_NAME_GIJUTSU}」ロールが見つかりません。", ephemeral=True)
            return
        if role in getattr(member, "roles", []):
            await interaction.response.send_message("✅ すでに技術班です！", ephemeral=True)
            return
        try:
            await member.add_roles(role)
            await interaction.response.send_message("🔧 技術班ロールを付与しました！", ephemeral=True)
            logger.info(f"技術班: {member}")
        except Exception as e:
            await interaction.response.send_message("❌ エラーが発生しました。", ephemeral=True)
            logger.exception(e)

# ========== ブロスタ勢ボタン ==========
class BrawlButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="🎮 ブロスタ勢になる", style=discord.ButtonStyle.green, custom_id="brawl_button")
    async def brawl(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = guild.get_member(interaction.user.id) or interaction.user
        if not is_verified(member):
            await interaction.response.send_message("⛔ 先に「✅ 認証する」ボタンで認証を完了してください。", ephemeral=True)
            logger.warning(f"未認証: {member}")
            return
        role = discord.utils.get(guild.roles, name=ROLE_NAME_BRAWL)
        if role is None:
            await interaction.response.send_message(f"「{ROLE_NAME_BRAWL}」ロールが見つかりません。", ephemeral=True)
            return
        if role in getattr(member, "roles", []):
            await interaction.response.send_message("✅ すでにブロスタ勢です！", ephemeral=True)
            return
        try:
            await member.add_roles(role)
            await interaction.response.send_message("🎮 ブロスタ勢ロールを付与しました！", ephemeral=True)
            logger.info(f"ブロスタ勢: {member}")
        except Exception as e:
            await interaction.response.send_message("❌ エラーが発生しました。", ephemeral=True)
            logger.exception(e)

# ========== 起動 ==========
@bot.event
async def on_ready():
    bot.add_view(VerifyButton())
    bot.add_view(GijutsuButton())
    bot.add_view(BrawlButton())
    try:
        if GUILD_ID:
            await bot.tree.sync(guild=discord.Object(id=int(GUILD_ID)))
        else:
            await bot.tree.sync()
    except Exception:
        logger.exception("コマンド同期エラー")
    logger.info(f"✅ {bot.user} 起動 — ログ先:{LOG_CHANNEL_ID} 待機{MIN_MEMBER_MINUTES}分 アカウント{MIN_ACCOUNT_AGE_DAYS}日")

# ========== コマンド ==========
@bot.tree.command(name="setup", description="認証メッセージを送信")
async def setup(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔒 サーバー認証【実験環境】",
        description=(
            "下のボタンを押して認証してください。\n"
            f"・アカウント作成から{MIN_ACCOUNT_AGE_DAYS}日以上経過\n"
            f"・サーバー参加から{MIN_MEMBER_MINUTES}分以上経過\n"
            "✅ ボタンを押すと簡単な計算問題が出ます → 人間だと証明してください\n"
            "⚠️ 認証後でないと「技術班」「ブロスタ勢」は取得できません。"
        ),
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=embed, view=VerifyButton())

@bot.tree.command(name="setup_gijutsu")
async def setup_gijutsu(interaction: discord.Interaction):
    embed = discord.Embed(title="🔧 技術班", description="先に認証を済ませてからボタンを押してください。", color=0x5865F2)
    await interaction.response.send_message(embed=embed, view=GijutsuButton())

@bot.tree.command(name="setup_brawl")
async def setup_brawl(interaction: discord.Interaction):
    embed = discord.Embed(title="🎮 ブロスタ勢", description="先に認証を済ませてからボタンを押してください。", color=0x2ECC71)
    await interaction.response.send_message(embed=embed, view=BrawlButton())

def main():
    try:
        bot.run(TOKEN)
    except Exception:
        logger.exception("Bot起動エラー")

if __name__ == "__main__":
    main()