# c:\Users\super\.github\新宿二丁目のママ\cogs\music_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import logging, math
import os
import asyncio, enum # enumを追加
from pathlib import Path # フォルダパスの操作のために追加
from config import GUILDS # configからGUILDSを読み込み

logger = logging.getLogger(__name__)

MUSIC_DIR = "music" # プロジェクトルートからの相対パス
ITEMS_PER_PAGE = 20 # /listmusic で1ページに表示する曲数
ITEMS_IN_SUMMARY = 5 # /playfolder などで表示する曲数の上限

class RepeatMode(enum.Enum):
    NONE = 0    # リピートなし
    ONE = 1     # 現在の曲をリピート
    ALL = 2     # キュー全体をリピート

class MusicListView(discord.ui.View):
    def __init__(self, music_files_details: list[tuple[str, str]], author_id: int):
        super().__init__(timeout=180) # 3分でタイムアウト
        self.music_files_details = music_files_details
        self.author_id = author_id
        self.current_page = 0
        self.total_pages = math.ceil(len(self.music_files_details) / ITEMS_PER_PAGE)
        self._update_buttons()

    def _get_page_content(self) -> str:
        start_index = self.current_page * ITEMS_PER_PAGE
        end_index = start_index + ITEMS_PER_PAGE
        page_items = self.music_files_details[start_index:end_index]
        
        description = ""
        for i, (_, display_name) in enumerate(page_items, start=start_index + 1):
            description += f"{i}. {display_name}\n"
        return description

    def _update_buttons(self):
        self.children[0].disabled = self.current_page == 0 # prev_button
        self.children[1].disabled = self.current_page >= self.total_pages - 1 # next_button

    async def _update_message(self, interaction: discord.Interaction):
        self._update_buttons()
        embed = discord.Embed(
            title=f"🎵 再生可能な曲リスト ({self.current_page + 1}/{self.total_pages}) 🎵",
            description=self._get_page_content(),
            color=discord.Color.purple()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀ 前へ", style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("コマンドを実行した人だけが操作できるのよ。", ephemeral=True)
            return
        self.current_page -= 1
        await self._update_message(interaction)

    @discord.ui.button(label="次へ ▶", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("コマンドを実行した人だけが操作できるのよ。", ephemeral=True)
            return
        self.current_page += 1
        await self._update_message(interaction)

class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.vc_connections = {}  # ギルドID: discord.VoiceClient
        self.music_queues = {}    # ギルドID: list[tuple[str, str]] (song_path, song_name)
        self.currently_playing_info = {} # ギルドID: {'path': str, 'name': str} 現在再生中の曲情報
        self.song_details_to_resume_after_voice = {} # ギルドID: {'path': str, 'name': str} VoiceCogによる中断後再開する曲
        self.last_text_channel_ids = {} # ギルドID: 最後に音楽コマンドが使われたテキストチャンネルID
        self.repeat_modes = {} # ギルドID: RepeatMode (デフォルトは RepeatMode.NONE)
        self._ensure_music_dir()

    def _ensure_music_dir(self):
        if not os.path.exists(MUSIC_DIR):
            try:
                os.makedirs(MUSIC_DIR)
                logger.info(f"音楽ディレクトリ '{MUSIC_DIR}' を作成しました。")
            except Exception as e:
                logger.error(f"音楽ディレクトリ '{MUSIC_DIR}' の作成に失敗しました: {e}")
        else:
            logger.info(f"音楽ディレクトリ '{MUSIC_DIR}' は既に存在します。")

    def get_vc_connection(self, guild_id: int) -> discord.VoiceClient | None:
        return self.vc_connections.get(guild_id)

    def set_vc_connection(self, guild_id: int, vc: discord.VoiceClient | None):
        if vc is None and guild_id in self.vc_connections:
            del self.vc_connections[guild_id]
        elif vc:
            self.vc_connections[guild_id] = vc

    def _get_music_files(self) -> list[tuple[str, str]]: # (absolute_path, display_name)
        music_files_details = []
        if not os.path.exists(MUSIC_DIR) or not os.path.isdir(MUSIC_DIR):
            return []
        
        # サポートする可能性のある拡張子 (FFmpegが対応するもの)
        supported_extensions = ('.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac')
        
        for root, _, files in os.walk(MUSIC_DIR):
            for file in files:
                if file.lower().endswith(supported_extensions):
                    full_path = os.path.abspath(os.path.join(root, file)) # 絶対パスで保存
                    # MUSIC_DIR からの相対パスを表示名とし、OSの標準パス区切り文字に正規化
                    display_name = os.path.normpath(os.path.relpath(full_path, os.path.abspath(MUSIC_DIR)))
                    music_files_details.append((full_path, display_name))
        
        music_files_details.sort(key=lambda x: x[1]) # display_name (相対パス) でソート
        return music_files_details

    def _after_playing(self, error, guild_id: int, song_path_played: str, song_name_played: str):
        logger.info(f'_after_playing: Song "{song_name_played}" (Path: {song_path_played}) finished/stopped for guild {guild_id}. Error: {error}')
        
        # 再生が終わった曲の情報を取得 (リピート処理で使うため pop する前に)
        # currently_playing_info は _play_next_song で設定されるが、_after_playing の時点ではまだ残っているはず
        # しかし、song_path_played と song_name_played を引数で受け取るようにしたので、そちらを使用する

        self.currently_playing_info.pop(guild_id, None) # 現在再生中の情報をクリア

        if error:
            logger.error(f'音楽再生エラー (ギルド {guild_id}, 曲: {song_name_played}): {error}')

        current_repeat_mode = self.repeat_modes.get(guild_id, RepeatMode.NONE)
        queue = self.music_queues.setdefault(guild_id, [])

        if song_path_played and song_name_played: # 有効な曲情報がある場合のみリピート処理
            if current_repeat_mode == RepeatMode.ONE:
                queue.insert(0, (song_path_played, song_name_played))
                logger.info(f"[Guild {guild_id}] リピート(1曲): {song_name_played} をキューの先頭に追加しました。")
            elif current_repeat_mode == RepeatMode.ALL:
                queue.append((song_path_played, song_name_played))
                logger.info(f"[Guild {guild_id}] リピート(全曲): {song_name_played} をキューの末尾に追加しました。")

        # VoiceCogによる中断からの再開が保留されている場合は、自動で次の曲へは進まない
        if guild_id not in self.song_details_to_resume_after_voice:
            if self.bot.loop.is_running(): # ボットがまだ動作しているか確認
                logger.info(f"_after_playing: Not a voice interruption, attempting to play next for guild {guild_id}")
                asyncio.run_coroutine_threadsafe(self._play_next_song(guild_id), self.bot.loop)
            else:
                logger.warning(f"_after_playing: Bot loop not running, cannot play next song for guild {guild_id}")
        else:
            logger.info(f"_after_playing: Voice interruption detected (resume pending for {self.song_details_to_resume_after_voice.get(guild_id, {}).get('name')}) for guild {guild_id}. Not playing next song automatically.")

    async def _play_next_song(self, guild_id: int):
        """キューから次の曲を再生する内部メソッド"""
        current_vc = self.get_vc_connection(guild_id)
        if not current_vc or not current_vc.is_connected():
            logger.warning(f"VCに接続されていません。次の曲を再生できません (ギルド {guild_id})。")
            if guild_id in self.music_queues: # VCがないならキューもクリアした方が安全
                self.music_queues[guild_id].clear()
            return
        
        logger.info(f"_play_next_song: Called for guild {guild_id}. VC Status - Playing: {current_vc.is_playing()}, Paused: {current_vc.is_paused()}")

        if guild_id not in self.music_queues or not self.music_queues[guild_id]:
            logger.info(f"_play_next_song: 音楽キューが空です (ギルド {guild_id})。再生を停止します。")
            # オプション: キューが空になったらVCから自動退出するロジック
            # if current_vc and current_vc.is_connected():
            #     # await current_vc.channel.send("キューが空になったので、少ししたら退出するわね。")
            #     # await asyncio.sleep(60) # 60秒後に退出など
            #     # if not self.music_queues.get(guild_id): # 再度キューが空か確認
            #     #    await current_vc.disconnect()
            #     #    self.set_vc_connection(guild_id, None)
            return

        if current_vc.is_playing() or current_vc.is_paused():
            # 通常、_after_playing から呼ばれるので、この状態は稀だが念のため
            logger.info(f"_play_next_song: VCは既に何かを再生/一時停止中です。処理をスキップします (ギルド {guild_id})。")
            return

        song_path, song_name = self.music_queues[guild_id].pop(0) # キューの先頭から取得して削除

        if not os.path.exists(song_path):
            logger.error(f"次の曲のファイルが見つかりません: {song_path} (ギルド {guild_id})")
            if current_vc.channel:
                try:
                    # interactionがないので、テキストチャンネルに直接送信
                    text_channel = self.bot.get_channel(current_vc.channel.id) # VCと同じIDのテキストチャンネルを探すのは適切ではない
                                                                              # interactionから取得するか、最後に使ったチャンネルを記憶しておく必要がある
                    logger.warning(f"_play_next_song: ファイル欠損通知の送信先チャンネル不明。'{song_name}'")
                    # await current_vc.channel.send(f"あら、キューにあった '{song_name}' が見つからないみたい…？ スキップするわね。")
                except Exception as e:
                    logger.error(f"ファイル欠損通知の送信エラー: {e}")
            await self._play_next_song(guild_id) # 次の曲へ
            return

        try:
            # 現在再生中の情報を更新
            self.currently_playing_info[guild_id] = {'path': song_path, 'name': song_name}
            logger.info(f"_play_next_song: Preparing to play '{song_name}' in guild {guild_id}")

            # FFmpegPCMAudioをPCMVolumeTransformerでラップして音量を調整
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(song_path), volume=0.1) # 音量を調整
            current_vc.play(source, after=lambda e: self._after_playing(e, guild_id, song_path, song_name)) # song_pathも渡す
            
            log_message = f"'{song_name}' の再生を開始するわよ♬ (ギルド {guild_id})"
            logger.info(log_message)

            # Discordにも通知
            notification_channel = None
            voice_channel_for_notification = current_vc.channel

            if voice_channel_for_notification and isinstance(voice_channel_for_notification, discord.VoiceChannel):
                try:
                    notification_channel = voice_channel_for_notification.text_in_voice_channel
                    if notification_channel:
                        logger.info(f"再生開始通知: ボイスチャンネル '{voice_channel_for_notification.name}' のテキストチャット (ID: {notification_channel.id}) を使用します。")
                except AttributeError:
                    logger.warning(f"再生開始通知: 'text_in_voice_channel' 属性が見つかりません。コマンド実行チャンネルへのフォールバックを試みます。 (ギルド {guild_id})")
                    notification_channel = None
                
                if not notification_channel:
                    logger.info(f"再生開始通知: ボイスチャンネル '{voice_channel_for_notification.name}' に紐づくテキストチャットが見つからないか属性がありません。コマンド実行チャンネルへのフォールバックを試みます。 (ギルド {guild_id})")
            
            if not notification_channel:
                last_cmd_channel_id = self.last_text_channel_ids.get(guild_id)
                if last_cmd_channel_id:
                    notification_channel = self.bot.get_channel(last_cmd_channel_id)
                    if notification_channel and isinstance(notification_channel, discord.TextChannel):
                        logger.info(f"再生開始通知: フォールバックとしてコマンド実行チャンネル '{notification_channel.name}' (ID: {notification_channel.id}) を使用します。 (ギルド {guild_id})")
                    elif notification_channel:
                        logger.warning(f"再生開始通知: フォールバック先のチャンネルID {last_cmd_channel_id} はテキストチャンネルではありません。タイプ: {type(notification_channel)} (ギルド {guild_id})")
                        notification_channel = None
                    else:
                        logger.warning(f"再生開始通知: フォールバック先のチャンネルID {last_cmd_channel_id} が見つかりません。 (ギルド {guild_id})")
                        notification_channel = None
                else:
                    logger.warning(f"再生開始通知: ボイスチャンネルチャットもコマンド実行チャンネルも見つかりません (ギルド {guild_id})。")

            if notification_channel:
                try:
                    await notification_channel.send(f"🎶 '{song_name}' の再生を開始するわよ♬")
                    logger.info(f"再生開始通知をチャンネル '{notification_channel.name}' に送信しました: '{song_name}' (ギルド {guild_id})")
                except discord.Forbidden:
                    logger.warning(f"チャンネル {notification_channel.id} ('{notification_channel.name}') へのメッセージ送信権限がありません。 (ギルド {guild_id})")
                except Exception as e:
                    logger.error(f"再生開始通知の送信中にエラー (チャンネル: {notification_channel.name}, ID: {notification_channel.id}, ギルド {guild_id}): {e}", exc_info=True)
            else:
                logger.warning(f"再生開始通知: 送信先のチャンネルが見つかりませんでした (ギルド {guild_id})。")

        except Exception as e:
            logger.error(f"_play_next_song: 再生開始時にエラー (ギルド {guild_id}, 曲: {song_name}): {e}", exc_info=True)
            
            # エラーメッセージを送信するチャンネルを特定 (上記通知ロジックと同様)
            error_notification_channel = None
            # (この部分は上記通知ロジックをコピー＆ペーストして変数名を変えるなどして実装)
            # ... (上記 notification_channel を特定するロジックと同様のものをここに記述) ...
            # 簡単のため、ここでは最後にコマンドが使われたチャンネルのみ試行
            last_cmd_channel_id_for_error = self.last_text_channel_ids.get(guild_id)
            if last_cmd_channel_id_for_error:
                error_notification_channel = self.bot.get_channel(last_cmd_channel_id_for_error)

            if error_notification_channel and isinstance(error_notification_channel, discord.TextChannel):
                try:
                    await error_notification_channel.send(f"あら、'{song_name}' の再生中に問題が発生したみたい…？ スキップするわね。")
                except Exception as send_e:
                    logger.error(f"再生エラー通知の送信エラー: {send_e}")
            else:
                logger.warning(f"再生エラー通知の送信先チャンネルが見つかりませんでした (ギルド {guild_id})。")

            self.currently_playing_info.pop(guild_id, None) # 再生失敗したのでクリア
            await self._play_next_song(guild_id) # エラーが発生した場合でも、次の曲の再生を試みる

    async def _add_to_queue_and_play(self, interaction: discord.Interaction, songs_to_add: list[tuple[str, str]], success_message_prefix: str):
        """複数の曲をキューに追加し、必要であれば再生を開始する共通ヘルパー"""
        guild_id = interaction.guild.id
        self.last_text_channel_ids[guild_id] = interaction.channel.id # コマンドが使われたチャンネルを記憶
        vc_channel = interaction.user.voice.channel # このメソッドを呼ぶ前にVCにいることは確認済みのはず
        if not songs_to_add:
            await interaction.followup.send("追加する曲が見つからなかったわ。") # 基本的にはここには来ないはず
            return

        if guild_id not in self.music_queues:
            self.music_queues[guild_id] = []

        for song_path, song_name in songs_to_add:
            self.music_queues[guild_id].append((song_path, song_name))
        
        added_songs_summary = ""
        if songs_to_add:
            if len(songs_to_add) == 1:
                # success_message_prefix が曲名を含むので、ここでは追加情報は不要
                pass
            else: # 複数曲の場合
                added_songs_summary += "\n**追加された曲の一部:**\n"
                for i, (_, display_name) in enumerate(songs_to_add[:ITEMS_IN_SUMMARY]):
                    added_songs_summary += f"- {display_name}\n"
                if len(songs_to_add) > ITEMS_IN_SUMMARY:
                    added_songs_summary += f"...他{len(songs_to_add) - ITEMS_IN_SUMMARY}曲\n"

        current_vc = self.get_vc_connection(guild_id)
        base_response_message = "" # "再生するわね" や "キューに追加したわ" の部分

        try:
            if current_vc is None or not current_vc.is_connected():
                current_vc = await vc_channel.connect()
                self.set_vc_connection(guild_id, current_vc)
                logger.info(f"VCに接続しました: {vc_channel.name} (ギルド {guild_id})")
                base_response_message = f"{success_message_prefix} 再生するわね 🎶"
                await interaction.followup.send(f"{base_response_message}{added_songs_summary}")
                asyncio.create_task(self._play_next_song(guild_id))
            elif current_vc.channel != vc_channel:
                await current_vc.move_to(vc_channel)
                logger.info(f"VCを移動しました: {vc_channel.name} (ギルド {guild_id})")
                if not (current_vc.is_playing() or current_vc.is_paused()):
                    base_response_message = f"チャンネルを移動したわね。{success_message_prefix} 再生を開始するわ 🎶"
                    await interaction.followup.send(f"{base_response_message}{added_songs_summary}")
                    asyncio.create_task(self._play_next_song(guild_id))
                else:
                    base_response_message = f"{success_message_prefix} キューの最後に追加したわ。"
                    await interaction.followup.send(f"{base_response_message}{added_songs_summary}")
            else: # 同じチャンネルに既に接続済み
                if current_vc.is_playing() or current_vc.is_paused():
                    base_response_message = f"{success_message_prefix} キューの最後に追加したわ。順番が来たら再生するわね。"
                else:
                    base_response_message = f"{success_message_prefix} 再生を開始するわ 🎶"
                await interaction.followup.send(f"{base_response_message}{added_songs_summary}")
                if not (current_vc.is_playing() or current_vc.is_paused()): # 再生中でなければ再生開始
                    asyncio.create_task(self._play_next_song(guild_id))

        except Exception as e:
            logger.error(f"_add_to_queue_and_play 処理中にエラー (ギルド {guild_id}): {e}", exc_info=True)
            # キューから追加しようとした曲を削除するのは複雑なので、エラーメッセージのみ表示
            # (もし厳密にロールバックするなら、追加前のキューの状態を覚えておく必要がある)
            await interaction.followup.send(
                "音楽の再生準備中に問題が発生したわ💦 ちょっと確認してみるわね。"
            )
            # 失敗した場合、キューに追加された曲が残ってしまう可能性があるが、
            # ユーザーは /clearmusicqueue でクリアできるので許容する

    @app_commands.command(name="listmusic", description="再生できる曲の一覧を表示するわ")
    @app_commands.guilds(*GUILDS)
    async def list_music_command(self, interaction: discord.Interaction):
        logger.info(f"/listmusic from {interaction.user} in {interaction.guild.name if interaction.guild else 'DM'}")
        await interaction.response.defer(thinking=True)

        music_files_details = self._get_music_files() # list of (full_path, display_name)
        if not music_files_details:
            await interaction.followup.send(f"ごめんなさいね、'{MUSIC_DIR}' フォルダとそのサブフォルダに再生できる曲が見当たらないわ。")
            return

        view = MusicListView(music_files_details, interaction.user.id)
        embed = discord.Embed(
            title=f"🎵 再生可能な曲リスト ({view.current_page + 1}/{view.total_pages}) 🎵",
            description=view._get_page_content(),
            color=discord.Color.purple()
        )
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="playmusic", description="指定された曲を再生するわよ。再生中ならキューに追加するわ。")
    @app_commands.describe(song_query="再生したい曲の名前 (一覧から選んでね)")
    @app_commands.guilds(*GUILDS)
    async def play_music_command(self, interaction: discord.Interaction, *, song_query: str):
        logger.info(f"/playmusic 曲: {song_query} from {interaction.user} in {interaction.guild.name}")
        await interaction.response.defer(thinking=True)

        if not interaction.guild:
            await interaction.followup.send("このコマンドはサーバー内でのみ使用可能です。")
            return

        guild_id = interaction.guild.id
        self.last_text_channel_ids[guild_id] = interaction.channel.id # コマンドが使われたチャンネルを記憶


        if interaction.user.voice is None or interaction.user.voice.channel is None:
            await interaction.followup.send("ボイスチャンネルに入ってから呼んでちょうだい🎧")
            return

        music_files_details = self._get_music_files() # list of (full_path, display_name)
        if not music_files_details:
            await interaction.followup.send(f"ごめんなさい、'{MUSIC_DIR}' フォルダに再生できる曲が見当たらないわ。`/listmusic` で確認してみて。")
            return

        song_query_lower = song_query.lower()
        
        # 優先度順に検索
        # 優先度1: display_name (フォルダパス含むファイル名) が song_query と完全一致
        level1_matches = list(set([
            (fp, dn) for fp, dn in music_files_details if song_query_lower == dn.lower()
        ]))

        # 優先度2: ファイル名部分(拡張子なし) が song_query と完全一致
        level2_matches = []
        if not level1_matches:
            level2_matches = list(set([
                (fp, dn) for fp, dn in music_files_details 
                if song_query_lower == os.path.splitext(os.path.basename(dn))[0].lower()
            ]))

        # 優先度3: song_query が display_name に含まれる (部分一致)
        level3_matches = []
        if not level1_matches and not level2_matches:
            level3_matches = list(set([
                (fp, dn) for fp, dn in music_files_details if song_query_lower in dn.lower()
            ]))
        
        # 優先度4: song_query が ファイル名部分(拡張子なし) に含まれる (部分一致)
        level4_matches = []
        if not level1_matches and not level2_matches and not level3_matches:
            level4_matches = list(set([
                (fp, dn) for fp, dn in music_files_details 
                if song_query_lower in os.path.splitext(os.path.basename(dn))[0].lower()
            ]))

        final_matches = []
        if level1_matches:
            final_matches = level1_matches
        elif level2_matches:
            final_matches = level2_matches
        elif level3_matches:
            final_matches = level3_matches
        elif level4_matches:
            final_matches = level4_matches
        
        found_song_details_tuple = None # (full_path, display_name)

        if len(final_matches) == 1:
            found_song_details_tuple = final_matches[0]
        elif len(final_matches) > 1:
            files_list_str = "\n".join([f"- {dn}" for _, dn in final_matches[:5]]) # 上位5件を表示
            await interaction.followup.send(
                f"'{song_query}' に合いそうな曲が複数見つかったわ。\n{files_list_str}\nもっと詳しく指定するか、`/listmusic` で確認してちょうだい。"
            )
            return
        
        if not found_song_details_tuple:
            await interaction.followup.send(f"ごめんなさいね、'{song_query}' という曲は見つからなかったわ。`/listmusic` で再生できる曲を確認してみて。")
            return

        song_path_to_play, song_name_to_display = found_song_details_tuple

        if not os.path.exists(song_path_to_play): # 念のため (フルパスのはず)
            await interaction.followup.send(f"あら、'{song_name_to_display}' が見つかったけどファイルが存在しないみたい…？")
            logger.error(f"ファイルが見つかりません (フルパスのはず): {song_path_to_play}")
            return

        songs_to_add = [(song_path_to_play, song_name_to_display)]
        message_prefix = f"わかったわ、'{song_name_to_display}' を" # _add_to_queue_and_play で "再生するわね" などが続く
        await self._add_to_queue_and_play(interaction, songs_to_add, message_prefix)

    @app_commands.command(name="playfolder", description="指定したフォルダ内の曲をまとめて再生/キュー追加するわ")
    @app_commands.describe(folder_path="再生したいフォルダのパス (例: J-POP や アニソン/お気に入り)")
    @app_commands.guilds(*GUILDS)
    async def play_folder_command(self, interaction: discord.Interaction, *, folder_path: str):
        logger.info(f"/playfolder フォルダ: {folder_path} from {interaction.user} in {interaction.guild.name}")
        await interaction.response.defer(thinking=True)

        if not interaction.guild:
            await interaction.followup.send("このコマンドはサーバー内でのみ使用可能です。")
            return

        guild_id = interaction.guild.id
        self.last_text_channel_ids[guild_id] = interaction.channel.id # コマンドが使われたチャンネルを記憶

        if interaction.user.voice is None or interaction.user.voice.channel is None:
            await interaction.followup.send("ボイスチャンネルに入ってから呼んでちょうだい🎧")
            return

        music_files_details = self._get_music_files()
        if not music_files_details:
            await interaction.followup.send(f"ごめんなさい、'{MUSIC_DIR}' フォルダに再生できる曲が見当たらないわ。")
            return

        normalized_folder_path_query_str = str(Path(os.path.normpath(folder_path.lower())))
        
        songs_in_folder = []
        for full_path, display_name in music_files_details:
            # display_name の親ディレクトリのパス文字列を取得し、正規化・小文字化
            # 例: display_name = "J-POP/ArtistX/SongC.mp3" -> parent_dir_str = "j-pop/artistx" (OS依存の区切り文字)
            # Pathオブジェクトを使うことでOS間のパス区切り文字の違いを吸収
            normalized_display_name_obj = Path(os.path.normpath(display_name.lower()))
            current_song_parent_dir_str = str(normalized_display_name_obj.parent)

            # 指定されたフォルダパスが、曲の親フォルダパスと一致するか、
            # または曲の親フォルダパスが指定されたフォルダパスで始まる（サブフォルダ内も含む）場合に合致
            if current_song_parent_dir_str == normalized_folder_path_query_str or \
               current_song_parent_dir_str.startswith(normalized_folder_path_query_str + os.sep):
                songs_in_folder.append((full_path, display_name))
        
        if not songs_in_folder:
            await interaction.followup.send(f"ごめんなさいね、フォルダ '{folder_path}' に曲が見つからなかったわ。パスを確認してみて。")
            return

        # 曲順を display_name でソート (フォルダ内でファイル名順になるように)
        songs_in_folder.sort(key=lambda x: x[1])

        num_added = len(songs_in_folder)
        message_prefix = f"フォルダ '{folder_path}' の {num_added}曲を" # "から" を削除して自然に
        await self._add_to_queue_and_play(interaction, songs_in_folder, message_prefix)

    @app_commands.command(name="skipmusic", description="今の曲をスキップして、キューの次の曲を再生するわ")
    @app_commands.guilds(*GUILDS)
    async def skip_music_command(self, interaction: discord.Interaction):
        logger.info(f"/skipmusic from {interaction.user} in {interaction.guild.name}")
        
        if not interaction.guild:
            await interaction.response.send_message("このコマンドはサーバー内でのみ使用可能です。", ephemeral=True)
            return
        guild_id = interaction.guild.id
        current_vc = self.get_vc_connection(guild_id)

        if not current_vc or not current_vc.is_connected():
            await interaction.response.send_message("アタシ、今ボイスチャンネルにいないみたいよ。", ephemeral=True)
            return
        
        if not (current_vc.is_playing() or current_vc.is_paused()):
            await interaction.response.send_message("今、何も再生してないみたいね。スキップできないわ。", ephemeral=True)
            return

        queue = self.music_queues.get(guild_id)
        if not queue: # キューが空（または存在しない）
            await interaction.response.send_message("キューに次の曲がないわ。今の曲を止めるわね。")
            current_vc.stop() # afterコールバックが呼ばれ、キューが空なので_play_next_songは何もしない
        else:
            # キューの先頭（次に再生される曲）の名前を取得
            _, next_song_name = queue[0] # (full_path, display_name)
            await interaction.response.send_message(f"わかったわ、今の曲をスキップして、次は '{next_song_name}' を再生するわね！")
            current_vc.stop() # これで _after_playing が呼ばれ、_play_next_song が実行される

    @app_commands.command(name="queuemusic", description="今の音楽再生キューを表示するわ")
    @app_commands.guilds(*GUILDS)
    async def queue_music_command(self, interaction: discord.Interaction):
        logger.info(f"/queuemusic from {interaction.user} in {interaction.guild.name}")
        await interaction.response.defer(thinking=True)

        if not interaction.guild:
            await interaction.followup.send("このコマンドはサーバー内でのみ使用可能です。")
            return
        guild_id = interaction.guild.id

        queue = self.music_queues.get(guild_id)
        if not queue:
            await interaction.followup.send("音楽キューは空っぽよ。何かリクエストしてちょうだい💋")
            return

        current_repeat_mode = self.repeat_modes.get(guild_id, RepeatMode.NONE)
        mode_text = "オフ"
        if current_repeat_mode == RepeatMode.ONE:
            mode_text = "現在の曲をリピート"
        elif current_repeat_mode == RepeatMode.ALL:
            mode_text = "キュー全体をリピート"

        embed = discord.Embed(title="🎵 再生待機中の曲リスト 🎵", color=discord.Color.purple())
        
        queue_description = ""
        # キューの曲は (song_path, song_name) のタプル
        # 最大10曲表示（多すぎるとメッセージが長くなるため）
        for i, (_, song_name) in enumerate(queue[:10]): # song_name は表示名 (例: J-POP/曲.mp3)
            queue_description += f"{i+1}. {song_name}\n"
        
        if not queue_description:
             await interaction.followup.send("音楽キューは空っぽみたい。") # 通常ここには来ないはず
             return

        embed.description = queue_description
        if len(queue) > 10:
            queue_description += f"...他{len(queue)-10}曲"
        embed.set_footer(text=f"全 {len(queue)} 曲が待機中 | リピートモード: {mode_text}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="clearmusicqueue", description="音楽再生キューを空にするわ")
    @app_commands.guilds(*GUILDS)
    async def clear_music_queue_command(self, interaction: discord.Interaction):
        logger.info(f"/clearmusicqueue from {interaction.user} in {interaction.guild.name}")

        if not interaction.guild:
            await interaction.response.send_message("このコマンドはサーバー内でのみ使用可能です。", ephemeral=True)
            return
        guild_id = interaction.guild.id

        if guild_id in self.music_queues and self.music_queues[guild_id]:
            self.music_queues[guild_id].clear()
            await interaction.response.send_message("音楽キューを空にしたわ。")
        else:
            await interaction.response.send_message("音楽キューはもう空っぽよ。", ephemeral=True)

    @app_commands.command(name="stopmusic", description="音楽の再生を止めるわ (キューは残るわよ)")
    @app_commands.guilds(*GUILDS)
    async def stop_music_command(self, interaction: discord.Interaction):
        logger.info(f"/stopmusic from {interaction.user} in {interaction.guild.name}")
        
        if not interaction.guild:
            await interaction.response.send_message("このコマンドはサーバー内でのみ使用可能です。", ephemeral=True)
            return
        guild_id = interaction.guild.id
        current_vc = self.get_vc_connection(guild_id)

        if current_vc and (current_vc.is_playing() or current_vc.is_paused()):
            current_vc.stop()
            await interaction.response.send_message("音楽を止めたわよ。キューに残ってる曲は `/playmusic` や `/skipmusic` で続きから再生できるわ。")
        else:
            await interaction.response.send_message("今、何も再生してないみたいね。", ephemeral=True)

    @app_commands.command(name="leavemusic", description="ボイスチャンネルから退出して、キューも空にするわ")
    @app_commands.guilds(*GUILDS)
    async def leave_music_channel_command(self, interaction: discord.Interaction):
        logger.info(f"/leavemusic from {interaction.user} in {interaction.guild.name}")

        if not interaction.guild:
            await interaction.response.send_message("このコマンドはサーバー内でのみ使用可能です。", ephemeral=True)
            return
        guild_id = interaction.guild.id
        current_vc = self.get_vc_connection(guild_id)

        if current_vc and current_vc.is_connected():
            if current_vc.is_playing() or current_vc.is_paused():
                current_vc.stop() # 再生中なら止める
            
            await current_vc.disconnect()
            self.set_vc_connection(guild_id, None)
            
            if guild_id in self.music_queues: # キューもクリア
                self.music_queues[guild_id].clear()
                logger.info(f"音楽キューをクリアしました (ギルド {guild_id})")

            await interaction.response.send_message("ボイスチャンネルから退出したわ。また呼んでちょうだいね💋")
        else:
            # VCにいない場合でもキューが残っている可能性があるのでクリア
            if guild_id in self.music_queues and self.music_queues[guild_id]:
                self.music_queues[guild_id].clear()
                logger.info(f"VCにはいなかったけど、音楽キューをクリアしました (ギルド {guild_id})")
                await interaction.response.send_message("アタシ、今ボイスチャンネルにいないみたいだけど、キューはクリアしておいたわ。", ephemeral=True)
            else:
                await interaction.response.send_message("アタシ、今ボイスチャンネルにいないみたいよ。", ephemeral=True)

    @app_commands.command(name="repeatmusic", description="音楽の再生リピートモードを設定するわ")
    @app_commands.describe(mode="リピートモードを選んでちょうだい (off, one, all)")
    @app_commands.choices(mode=[
        app_commands.Choice(name="オフ (リピートなし)", value="off"),
        app_commands.Choice(name="現在の曲をリピート", value="one"),
        app_commands.Choice(name="キュー全体をリピート", value="all"),
    ])
    @app_commands.guilds(*GUILDS)
    async def repeat_music_command(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        logger.info(f"/repeatmusic mode: {mode.value} from {interaction.user} in {interaction.guild.name}")
        if not interaction.guild:
            await interaction.response.send_message("このコマンドはサーバー内でのみ使用可能です。", ephemeral=True)
            return
        
        guild_id = interaction.guild.id
        chosen_mode_str = mode.value.lower()

        if chosen_mode_str == "off":
            self.repeat_modes[guild_id] = RepeatMode.NONE
            await interaction.response.send_message("リピートをオフにしたわ。")
        elif chosen_mode_str == "one":
            self.repeat_modes[guild_id] = RepeatMode.ONE
            await interaction.response.send_message("今の曲をリピートするわね。")
        elif chosen_mode_str == "all":
            self.repeat_modes[guild_id] = RepeatMode.ALL
            await interaction.response.send_message("キューに入ってる曲を全部リピートするわよ。")
        else: # 通常ここには到達しない
            await interaction.response.send_message("あら、よくわからないモードね。`off`, `one`, `all` から選んでちょうだい。", ephemeral=True)

    async def pause_current_song(self, guild_id: int):
        """指定されたギルドで再生中の音楽を一時停止するわ"""
        logger.info(f"pause_current_song: Attempting to pause for guild {guild_id}. Currently playing info from self: {self.currently_playing_info.get(guild_id)}")
        vc = self.get_vc_connection(guild_id)
        if vc and vc.is_connected() and vc.is_playing():
            current_song_info = self.currently_playing_info.get(guild_id)
            if current_song_info:
                vc.pause()
                # VoiceCogによる中断なので、再開情報を保存
                self.song_details_to_resume_after_voice[guild_id] = current_song_info
                logger.info(f"pause_current_song: Stored song_details_to_resume_after_voice for guild {guild_id}: {current_song_info}")
                logger.info(f"音楽を一時停止しました (曲: {current_song_info['name']})。VoiceCogのため再開情報を保存 (ギルド {guild_id})")
                return True # 正常に情報を保存してpauseした場合のみTrue
            else:
                # 再生中だがこちらの管理情報がない。これは異常系。
                # VoiceCog側で再開を期待させないようにFalseを返す。
                logger.warning(f"pause_current_song: VC is playing, but no current song info in MusicCog's state for guild {guild_id}. Pausing VC, but returning False as resume info cannot be stored.")
                vc.pause() # 念のためVCは止める
                return False # 再開情報がないので、VoiceCogにresumeを期待させない
        else: # VCがない、接続されてない、または再生中でない
            logger.info(f"pause_current_song: Conditions for pause not met. VC Connected: {vc.is_connected() if vc else False}, VC Playing: {vc.is_playing() if vc else False} (Guild {guild_id})")
            return False


    async def resume_current_song(self, guild_id: int):
        """指定されたギルドで一時停止中の音楽を再開するわ"""
        logger.info(f"resume_current_song: Called for guild {guild_id}")
        vc = self.get_vc_connection(guild_id)
        if not vc or not vc.is_connected():
            logger.warning(f"resume_current_song: VCが見つからないか未接続です (ギルド {guild_id})")
            self.song_details_to_resume_after_voice.pop(guild_id, None) # VCがないなら再開情報もクリア
            return False

        details_to_resume = self.song_details_to_resume_after_voice.pop(guild_id, None)
        resumed_or_played_successfully = False

        if details_to_resume:
            song_path = details_to_resume['path']
            song_name = details_to_resume['name']
            logger.info(f"resume_current_song: VoiceCogによる中断から '{song_name}' の再開を試みます (ギルド {guild_id})")

            if not os.path.exists(song_path):
                logger.error(f"resume_current_song: 再開しようとした曲のファイルが見つかりません: {song_path} (ギルド {guild_id})")
                # 再開失敗なので、キューから次に進むことを試みる
            else:
                try:
                    if vc.is_playing() or vc.is_paused(): # VoiceCogの再生が終わった直後は止まっているはずだが念のため
                        vc.stop()
                    
                    # 再開する曲を「現在再生中」として再設定
                    self.currently_playing_info[guild_id] = {'path': song_path, 'name': song_name}
                    
                    source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(song_path), volume=0.1)
                    vc.play(source, after=lambda e: self._after_playing(e, guild_id, song_name))
                    logger.info(f"resume_current_song: 中断された曲 '{song_name}' を再開しました (ギルド {guild_id})")
                    resumed_or_played_successfully = True
                except Exception as e:
                    logger.error(f"resume_current_song: '{song_name}' の再開中にエラー: {e}", exc_info=True)
                    self.currently_playing_info.pop(guild_id, None) # 再生失敗したのでクリア
                    # 再開失敗、キューから次に進むことを試みる

        if not resumed_or_played_successfully:
            logger.info(f"resume_current_song: 中断された曲の再開処理が完了したか、中断情報がありませんでした。VCの状態を確認します。Playing: {vc.is_playing()}, Paused: {vc.is_paused()} (ギルド {guild_id})")
            if not vc.is_playing() and not vc.is_paused(): # VCが何もしていない状態なら
                if self.music_queues.get(guild_id):
                    logger.info(f"resume_current_song: キューに次の曲があるので再生します (ギルド {guild_id})")
                    await self._play_next_song(guild_id) # _play_next_song が成功したかはそちらで判断
                    resumed_or_played_successfully = True # play_next_songが試みられた
                else:
                    logger.info(f"resume_current_song: 再開する曲もキューも空です (ギルド {guild_id})")
            else:
                logger.warning(f"resume_current_song: VCが再生中または一時停止中です。次の曲の再生は行いません (ギルド {guild_id})")

        return resumed_or_played_successfully

# Bot起動時にCogを読み込むsetup関数
async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot), guilds=GUILDS)
    logger.info("MusicCogが正常にロードされました。")