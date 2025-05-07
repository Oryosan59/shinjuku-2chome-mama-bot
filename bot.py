# 必要なライブラリをインポート
import discord
from discord.ext import commands
import os
import logging
import asyncio

# 設定ファイルをインポート
from config import DISCORD_BOT_TOKEN, GEMINI_API_KEY, GUILDS, PROMPT_Q_FILE_PATH, PROMPT_VOICE_FILE_PATH

# ログ出力の設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# プロンプトファイルの存在確認と読み込み（エラーハンドリングはconfig側で行う想定だが、念のためここでも）
if not os.path.exists(PROMPT_Q_FILE_PATH):
    logger.warning(f"qコマンド用プロンプトファイルが見つかりません: {PROMPT_Q_FILE_PATH}")
if not os.path.exists(PROMPT_VOICE_FILE_PATH):
    logger.warning(f"voiceコマンド用プロンプトファイルが見つかりません: {PROMPT_VOICE_FILE_PATH}")


# Discordボットの基本設定
intents = discord.Intents.default()  # デフォルトのインテントを使用
intents.message_content = True # メッセージ内容の取得を有効にする場合 (Cog内で履歴取得などに使うなら)
bot = commands.Bot(command_prefix="!", intents=intents) # client から bot に変数名変更

# Cogのファイル名 (拡張子なし)
INITIAL_EXTENSIONS = [
    'cogs.ask_cog',
    'cogs.voice_cog',
    'cogs.music_cog' # MusicCogを追加
]

# Botが起動したときに実行される処理
@bot.event
async def on_ready():
    logger.info(f'{bot.user} としてログインしました')

    # Cogをロード
    for extension in INITIAL_EXTENSIONS:
        try:
            await bot.load_extension(extension)
            logger.info(f"{extension} をロードしました。")
        except Exception as e:
            logger.error(f"{extension} のロードに失敗しました: {e}", exc_info=True)
    try:

        # 既存のグローバルコマンドを削除
        # ただし、app_commands.guilds() を使っている場合、基本的にはギルドコマンドとして登録されるので、
        # グローバルコマンドの削除は不要なケースが多い。
        # もし過去にグローバルコマンドを登録してしまっていた場合のみ、一度実行して削除する。
        # global_commands = await bot.tree.fetch_commands()
        # deleted_count = 0
        # for command in global_commands:
        #     if command.guild_id is None: # グローバルコマンドのみ対象
        #         await bot.tree.remove_command(command.name)
        #         deleted_count += 1
        # if deleted_count > 0:
        #    logger.info(f"{deleted_count} 個のグローバルコマンドを削除しました")

        # 各ギルドにコマンドを同期 (Cogがロードされた後に行う)
        for guild_obj in GUILDS:
            try:
                synced = await bot.tree.sync(guild=guild_obj)
                logger.info(f"{len(synced)} 個のコマンドをギルド {guild_obj.id} に同期しました")
            except discord.errors.Forbidden:
                 logger.error(f"ギルド {guild_obj.id} へのコマンド同期権限がありません。ボットが 'applications.commands' スコープで招待されているか確認してください。")
            except Exception as e:
                logger.error(f"ギルド {guild_obj.id} へのコマンド同期中にエラー: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"on_ready処理中にエラー: {e}", exc_info=True)

# ボットを起動（トークンが存在すれば）
async def main():
    if not DISCORD_BOT_TOKEN:
        logger.error("Discord Botトークンが設定されていません。")
        return
    if not GEMINI_API_KEY: # Geminiキーのチェックもここで行う
        logger.error("Gemini APIキーが設定されていません。")
        return

    async with bot:
        await bot.start(DISCORD_BOT_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())