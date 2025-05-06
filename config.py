# c:\Users\super\デスクトップ\新宿二丁目のオネエ\config.py
import os
from dotenv import load_dotenv
import discord
import logging

logger = logging.getLogger(__name__)
load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# プロンプトファイルのパス (bot.pyからの相対パスを想定)
PROMPT_Q_FILE_PATH = os.path.join("prompt", "q.txt")
PROMPT_VOICE_FILE_PATH = os.path.join("prompt", "voice.txt")

BASE_Q_PROMPT = ""
try:
    with open(PROMPT_Q_FILE_PATH, "r", encoding="utf-8") as f:
        BASE_Q_PROMPT = f.read().strip() + "\n\n"
    logger.info(f"qコマンド用プロンプトファイルを読み込みました: {PROMPT_Q_FILE_PATH}")
except FileNotFoundError:
    logger.warning(f"警告: qコマンド用プロンプトファイルが見つかりません: {PROMPT_Q_FILE_PATH}")
    BASE_Q_PROMPT = "あら、ちょっと設定ファイルが見当たらないわね…？ (qプロンプト)\n\n" # フォールバック
except Exception as e:
    logger.error(f"qコマンド用プロンプトファイルの読み込み中にエラー: {e}")
    BASE_Q_PROMPT = "プロンプトの読み込みでエラーよ！ (qプロンプト)\n\n" # フォールバック

BASE_VOICE_PROMPT = ""
try:
    with open(PROMPT_VOICE_FILE_PATH, "r", encoding="utf-8") as f:
        BASE_VOICE_PROMPT = f.read().strip() + "\n\n"
    logger.info(f"voiceコマンド用プロンプトファイルを読み込みました: {PROMPT_VOICE_FILE_PATH}")
except FileNotFoundError:
    logger.warning(f"警告: voiceコマンド用プロンプトファイルが見つかりません: {PROMPT_VOICE_FILE_PATH}")
    BASE_VOICE_PROMPT = "あら、ちょっと設定ファイルが見当たらないわね…？ (voiceプロンプト)\n\n" # フォールバック
except Exception as e:
    logger.error(f"voiceコマンド用プロンプトファイルの読み込み中にエラー: {e}")
    BASE_VOICE_PROMPT = "プロンプトの読み込みでエラーよ！ (voiceプロンプト)\n\n" # フォールバック

# Discordギルド（サーバー）のIDを.envから読み込む
GUILD_IDS_STR = os.getenv("DISCORD_GUILD_IDS")
GUILD_IDS = []
if GUILD_IDS_STR:
    try:
        GUILD_IDS = [int(gid.strip()) for gid in GUILD_IDS_STR.split(',')]
        logger.info(f"DiscordギルドIDを .env から読み込みました: {GUILD_IDS}")
    except ValueError:
        logger.error(f"DISCORD_GUILD_IDS の形式が正しくありません。カンマ区切りの数値で指定してください。例: 123,456")
else:
    logger.warning("DISCORD_GUILD_IDS が .env ファイルに設定されていません。")

GUILDS = [discord.Object(id=gid) for gid in GUILD_IDS]

# VOICEVOX APIのベースURL
VOICEVOX_BASE_URL = "http://127.0.0.1:50021"

# Geminiモデル名
GEMINI_MODEL_NAME = "gemini-2.0-flash"

# スピーカーID
VOICEVOX_SPEAKER_ID = 66
