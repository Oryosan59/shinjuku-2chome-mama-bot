# c:\Users\super\デスクトップ\新宿二丁目のオネエ\cogs\ask_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
from config import BASE_Q_PROMPT, GUILDS # configから読み込み
from handlers.gemini_handler import GeminiHandler # GeminiHandlerをインポート

logger = logging.getLogger(__name__)

class AskCog(commands.Cog):
    def __init__(self, bot: commands.Bot, gemini_handler: GeminiHandler):
        self.bot = bot
        self.gemini_handler = gemini_handler
        if not BASE_Q_PROMPT:
            logger.warning("qコマンド用のベースプロンプトが読み込まれていません。")

    @app_commands.command(name="q", description="ママにお悩み質問するのよ！")
    @app_commands.guilds(*GUILDS) # GUILDSリストを展開して渡す
    async def ask_gemini_command(self, interaction: discord.Interaction, *, question: str):
        logger.info(f"/q 質問: {question} from {interaction.user} in {interaction.guild.name if interaction.guild else 'DM'}")
        await interaction.response.defer(thinking=True)

        if not BASE_Q_PROMPT:
            await interaction.followup.send("ごめんなさい、なんだか調子が悪いの… (プロンプト設定エラー)")
            return

        try:
            # 過去の会話履歴を取得してプロンプトに組み込む (元のロジックを流用)
            history = []
            # DMではchannel.historyが使えない場合があるので、ギルド内のみ履歴取得
            if interaction.guild:
                async for msg in interaction.channel.history(limit=5, oldest_first=False):
                    if msg.author.bot:
                        continue
                    if msg.content.strip():
                        # ユーザー名がNoneの場合を考慮
                        author_name = msg.author.display_name if msg.author else "不明なユーザー"
                        history.append(f"{author_name}: {msg.content.strip()}")
                    if len(history) >= 5:
                        break
                history.reverse()
            history_text = "\n".join(history)
            user_display_name = interaction.user.display_name if interaction.user else "アンタ"

            full_prompt = f"{BASE_Q_PROMPT}\n--- 会話履歴 ---\n{history_text}\n\n--- {user_display_name}からの質問 ---\n{question}"

            answer_text = await self.gemini_handler.generate_response(full_prompt)

            if answer_text:
                await interaction.followup.send(f"> {question}\n\n{answer_text}")
            else:
                await interaction.followup.send("うまく答えが出なかったわ… もう一度試してみてちょうだい。")
        except Exception as e:
            logger.error(f"/q コマンド処理中にエラー: {e}", exc_info=True)
            await interaction.followup.send("質問処理中にトラブル発生よ💦 ちょっと待っててちょうだい。")

async def setup(bot: commands.Bot):
    gemini_h = GeminiHandler() # Bot起動時にGeminiHandlerを初期化
    await bot.add_cog(AskCog(bot, gemini_h), guilds=GUILDS)
    logger.info("AskCogが正常にロードされました。")

