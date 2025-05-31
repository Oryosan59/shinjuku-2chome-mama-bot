# c:\Users\super\デスクトップ\新宿二丁目のオネエ\config.py
import os
from dotenv import load_dotenv
import discord
import logging

logger = logging.getLogger(__name__)
load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

PROMPT_DIR = "prompt" # プロンプトファイルが格納されているディレクトリ

# 音楽ファイルのディレクトリ設定
# 環境変数 MUSIC_FOLDER_PATH で指定されていればそれを使用し、
# なければデフォルトで "music" フォルダを使用する
DEFAULT_MUSIC_DIR = "music"
MUSIC_DIR_FROM_ENV = os.getenv("MUSIC_FOLDER_PATH")

if MUSIC_DIR_FROM_ENV and os.path.isdir(MUSIC_DIR_FROM_ENV):
    MUSIC_DIR = os.path.abspath(MUSIC_DIR_FROM_ENV) # 絶対パスに変換
else:
    MUSIC_DIR = os.path.abspath(DEFAULT_MUSIC_DIR) # デフォルトも絶対パスに
logger.info(f"音楽ディレクトリとして {MUSIC_DIR} を使用します。")

def find_prompt_file(keyword: str, directory: str = PROMPT_DIR) -> str | None:
    """
    指定されたディレクトリ内で、キーワードに部分一致する最初のプロンプトファイルを探す。
    まず '{keyword}.txt' という完全一致のファイルを探し、
    見つからなければ '{keyword}' を含む .txt ファイルを探す（大文字・小文字区別なし）。
    """
    # 1. 完全一致のファイルを探す (例: q.txt)
    exact_match_path = os.path.join(directory, f"{keyword}.txt")
    if os.path.exists(exact_match_path):
        logger.info(f"プロンプトファイル (完全一致) を見つけました: {exact_match_path}")
        return exact_match_path

    # 2. 部分一致のファイルを探す (例: q_custom.txt, my_q_prompt.txt など)
    try:
        if not os.path.isdir(directory):
            logger.warning(f"プロンプトディレクトリが見つかりません: {directory}")
            return None
        for filename in os.listdir(directory):
            if keyword.lower() in filename.lower() and filename.lower().endswith(".txt"):
                partial_match_path = os.path.join(directory, filename)
                logger.info(f"プロンプトファイル (部分一致) を見つけました: {partial_match_path}")
                return partial_match_path
    except Exception as e:
        logger.error(f"プロンプトファイル検索中にエラー ({directory}): {e}")
        return None

    logger.warning(f"キーワード '{keyword}' に一致するプロンプトファイルが {directory} 内に見つかりませんでした。")
    return None

def find_music_file(keyword: str, directory: str = MUSIC_DIR, extensions: list[str] = None) -> str | None:
    """
    指定されたディレクトリ内で、キーワードに部分一致する最初の音楽ファイルを探す。
    まず '{keyword}.ext' という完全一致のファイルを探し (指定された拡張子で)、
    見つからなければ '{keyword}' を含むファイルを探す（大文字・小文字区別なし、指定された拡張子で）。
    """
    if extensions is None:
        extensions = [".mp3", ".wav", ".ogg"] # デフォルトの音楽ファイル拡張子

    # 1. 完全一致のファイルを探す
    for ext in extensions:
        exact_match_path = os.path.join(directory, f"{keyword}{ext}")
        if os.path.exists(exact_match_path):
            logger.info(f"音楽ファイル (完全一致) を見つけました: {exact_match_path}")
            return exact_match_path

    # 2. 部分一致のファイルを探す
    try:
        if not os.path.isdir(directory):
            logger.warning(f"音楽ディレクトリが見つかりません: {directory}")
            return None
        for filename in os.listdir(directory):
            name_lower = filename.lower()
            if keyword.lower() in name_lower and any(name_lower.endswith(ext) for ext in extensions):
                partial_match_path = os.path.join(directory, filename)
                logger.info(f"音楽ファイル (部分一致) を見つけました: {partial_match_path}")
                return partial_match_path
    except Exception as e:
        logger.error(f"音楽ファイル検索中にエラー ({directory}): {e}")
        return None
    logger.warning(f"キーワード '{keyword}' に一致する音楽ファイルが {directory} 内 (拡張子: {extensions}) に見つかりませんでした。")
    return None

# プロンプトファイルのパスを検索して設定
PROMPT_Q_KEYWORD = "q"
PROMPT_VOICE_KEYWORD = "voice"

PROMPT_Q_FILE_PATH = find_prompt_file(PROMPT_Q_KEYWORD)
PROMPT_VOICE_FILE_PATH = find_prompt_file(PROMPT_VOICE_KEYWORD)

BASE_Q_PROMPT = ""
if PROMPT_Q_FILE_PATH:
    try:
        with open(PROMPT_Q_FILE_PATH, "r", encoding="utf-8") as f:
            BASE_Q_PROMPT = f.read().strip() + "\n\n"
        logger.info(f"qコマンド用プロンプトファイルを読み込みました: {PROMPT_Q_FILE_PATH}")
    except Exception as e:
        logger.error(f"qコマンド用プロンプトファイル ({PROMPT_Q_FILE_PATH}) の読み込み中にエラー: {e}")
        BASE_Q_PROMPT = "プロンプトの読み込みでエラーよ！ (qプロンプト)\n\n" # フォールバック
else:
    logger.warning(f"警告: qコマンド用プロンプトファイルが見つかりません (キーワード: {PROMPT_Q_KEYWORD})。")
    BASE_Q_PROMPT = "あら、ちょっと設定ファイルが見当たらないわね…？ (qプロンプト)\n\n" # フォールバック

BASE_VOICE_PROMPT = ""
if PROMPT_VOICE_FILE_PATH:
    try:
        with open(PROMPT_VOICE_FILE_PATH, "r", encoding="utf-8") as f:
            BASE_VOICE_PROMPT = f.read().strip() + "\n\n"
        logger.info(f"voiceコマンド用プロンプトファイルを読み込みました: {PROMPT_VOICE_FILE_PATH}")
    except Exception as e:
        logger.error(f"voiceコマンド用プロンプトファイル ({PROMPT_VOICE_FILE_PATH}) の読み込み中にエラー: {e}")
        BASE_VOICE_PROMPT = "プロンプトの読み込みでエラーよ！ (voiceプロンプト)\n\n" # フォールバック
else:
    logger.warning(f"警告: voiceコマンド用プロンプトファイルが見つかりません (キーワード: {PROMPT_VOICE_KEYWORD})。")
    BASE_VOICE_PROMPT = "あら、ちょっと設定ファイルが見当たらないわね…？ (voiceプロンプト)\n\n" # フォールバック

# 例: BGMファイルのパスを検索して設定 (music_cog.py などで利用することを想定)
BACKGROUND_MUSIC_KEYWORD = "bgm" # 例: "bgm.mp3" や "background_music_long.wav" などを探す
BACKGROUND_MUSIC_FILE_PATH = find_music_file(BACKGROUND_MUSIC_KEYWORD)

if BACKGROUND_MUSIC_FILE_PATH:
    logger.info(f"BGMファイルを見つけました: {BACKGROUND_MUSIC_FILE_PATH}")
else:
    logger.warning(f"BGMファイルが見つかりませんでした (キーワード: {BACKGROUND_MUSIC_KEYWORD})。")


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
