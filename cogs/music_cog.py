# c:\Users\super\.github\新宿二丁目のママ\cogs\music_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
import asyncio
from config import GUILDS # configからGUILDSを読み込み

logger = logging.getLogger(__name__)

MUSIC_DIR = "music" # プロジェクトルートからの相対パス

class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.vc_connections = {}  # ギルドID: discord.VoiceClient
        self.music_queues = {}    # ギルドID: list[tuple[str, str]] (song_path, song_name)
        self.currently_playing_info = {} # ギルドID: {'path': str, 'name': str} 現在再生中の曲情報
        self.song_details_to_resume_after_voice = {} # ギルドID: {'path': str, 'name': str} VoiceCogによる中断後再開する曲
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

    def _get_music_files(self) -> list[str]:
        if not os.path.exists(MUSIC_DIR) or not os.path.isdir(MUSIC_DIR):
            return []
        # サポートする可能性のある拡張子 (FFmpegが対応するもの)
        supported_extensions = ('.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac')
        return [f for f in os.listdir(MUSIC_DIR) if os.path.isfile(os.path.join(MUSIC_DIR, f)) and f.lower().endswith(supported_extensions)]

    def _after_playing(self, error, guild_id: int, song_name_played: str):
        logger.info(f'_after_playing: Song "{song_name_played}" finished/stopped for guild {guild_id}. Error: {error}')
        self.currently_playing_info.pop(guild_id, None) # 現在再生中の情報をクリア

        if error:
            logger.error(f'音楽再生エラー (ギルド {guild_id}, 曲: {song_name_played}): {error}')

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
            current_vc.play(source, after=lambda e: self._after_playing(e, guild_id, song_name))
            logger.info(f"_play_next_song: '{song_name}' の再生を開始しました (ギルド {guild_id}) - 音量0.1")
        except Exception as e:
            logger.error(f"_play_next_song: 再生開始時にエラー (ギルド {guild_id}, 曲: {song_name}): {e}", exc_info=True)
            if current_vc.channel:
                try:
                    await current_vc.channel.send(f"'{song_name}' の再生中に問題が発生したわ。スキップするわね。")
                except Exception as send_e:
                    logger.error(f"再生エラー通知の送信エラー: {send_e}")
            self.currently_playing_info.pop(guild_id, None) # 再生失敗したのでクリア
            await self._play_next_song(guild_id) # エラーが発生した場合でも、次の曲の再生を試みる

    @app_commands.command(name="listmusic", description="再生できる曲の一覧を表示するわ")
    @app_commands.guilds(*GUILDS)
    async def list_music_command(self, interaction: discord.Interaction):
        logger.info(f"/listmusic from {interaction.user} in {interaction.guild.name if interaction.guild else 'DM'}")
        await interaction.response.defer(thinking=True)

        music_files = self._get_music_files()
        if not music_files:
            await interaction.followup.send(f"ごめんなさいね、'{MUSIC_DIR}' フォルダに再生できる曲が見当たらないわ。")
            return

        embed = discord.Embed(title="🎵 再生可能な曲リスト 🎵", color=discord.Color.purple())
        description = ""
        for i, song in enumerate(music_files):
            description += f"{i+1}. {song}\n"
        embed.description = description
        await interaction.followup.send(embed=embed)

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

        if interaction.user.voice is None or interaction.user.voice.channel is None:
            await interaction.followup.send("ボイスチャンネルに入ってから呼んでちょうだい🎧")
            return

        music_files = self._get_music_files()
        if not music_files:
            await interaction.followup.send(f"ごめんなさい、'{MUSIC_DIR}' フォルダに再生できる曲が見当たらないわ。`/listmusic` で確認してみて。")
            return

        # 曲検索ロジック (修正版)
        found_song_name = None
        song_query_lower = song_query.lower()

        # 1. 完全一致 (ファイル名 + 拡張子)
        for mf in music_files:
            if song_query_lower == mf.lower():
                found_song_name = mf
                break
        
        # 2. 完全一致 (ファイル名のみ、拡張子なし)
        if not found_song_name:
            matches_ext_agnostic = []
            for mf in music_files:
                name_no_ext, _ = os.path.splitext(mf)
                if song_query_lower == name_no_ext.lower():
                    matches_ext_agnostic.append(mf)
            if len(matches_ext_agnostic) == 1:
                found_song_name = matches_ext_agnostic[0]
            elif len(matches_ext_agnostic) > 1:
                files_list_str = "\n".join([f"- {m}" for m in matches_ext_agnostic[:5]])
                await interaction.followup.send(
                    f"'{song_query}' に合う曲が複数見つかったわ (拡張子違いの完全一致)。\n{files_list_str}\nもっと詳しく指定してちょうだい。"
                )
                return

        # 3. 部分一致 (ファイル名のみ、拡張子なし)
        if not found_song_name:
            partial_matches_name_only = []
            for mf in music_files:
                name_no_ext, _ = os.path.splitext(mf)
                if song_query_lower in name_no_ext.lower(): # query が ファイル名の一部に含まれる
                    partial_matches_name_only.append(mf)
            
            if len(partial_matches_name_only) == 1:
                found_song_name = partial_matches_name_only[0]
            elif len(partial_matches_name_only) > 1:
                files_list_str = "\n".join([f"- {m}" for m in partial_matches_name_only[:5]])
                await interaction.followup.send(
                    f"'{song_query}' に合う曲が複数見つかったわ (ファイル名部分一致)。\n{files_list_str}\nもっと詳しく指定してちょうだい。"
                )
                return

        # 4. 部分一致 (フルファイル名、拡張子含む) - 上記で見つからなかった場合
        if not found_song_name:
            partial_matches_full = []
            for mf in music_files:
                if song_query_lower in mf.lower(): # query が フルファイル名の一部に含まれる
                    partial_matches_full.append(mf)
            
            if len(partial_matches_full) == 1:
                found_song_name = partial_matches_full[0]
            elif len(partial_matches_full) > 1:
                files_list_str = "\n".join([f"- {m}" for m in partial_matches_full[:5]])
                await interaction.followup.send(
                    f"'{song_query}' に合う曲が複数見つかったわ (フルネーム部分一致)。\n{files_list_str}\nもっと詳しく指定してちょうだい。"
                )
                return

        if not found_song_name:
            await interaction.followup.send(f"ごめんなさいね、'{song_query}' という曲は見つからなかったわ。`/listmusic` で再生できる曲を確認してみて。")
            return

        song_path = os.path.join(MUSIC_DIR, found_song_name)
        if not os.path.exists(song_path): # 念のため
            await interaction.followup.send(f"あら、'{found_song_name}' が見つかったけどファイルが存在しないみたい…？")
            logger.error(f"ファイルが見つかりません: {song_path}")
            return

        # キューの初期化 (ギルドごと)
        if guild_id not in self.music_queues:
            self.music_queues[guild_id] = []
        
        self.music_queues[guild_id].append((song_path, found_song_name)) # (パス, 表示名) のタプルをキューに追加

        vc_channel = interaction.user.voice.channel
        current_vc = self.get_vc_connection(guild_id)

        try:
            if current_vc is None or not current_vc.is_connected():
                current_vc = await vc_channel.connect()
                self.set_vc_connection(guild_id, current_vc)
                logger.info(f"VCに接続しました: {vc_channel.name} (ギルド {guild_id})")
                await interaction.followup.send(f"わかったわ、'{found_song_name}' を再生するわね 🎶")
                # _play_next_song はキューから取り出すので、ここでは呼び出すだけ
                asyncio.create_task(self._play_next_song(guild_id))
            elif current_vc.channel != vc_channel:
                await current_vc.move_to(vc_channel)
                logger.info(f"VCを移動しました: {vc_channel.name} (ギルド {guild_id})")
                if not (current_vc.is_playing() or current_vc.is_paused()):
                    await interaction.followup.send(f"チャンネルを移動したわね。'{found_song_name}' をキューに追加して、再生を開始するわ 🎶")
                    asyncio.create_task(self._play_next_song(guild_id))
                else:
                    await interaction.followup.send(f"'{found_song_name}' をキューの最後に追加したわ。")
            else: # 同じチャンネルに既に接続済み
                if current_vc.is_playing() or current_vc.is_paused():
                    await interaction.followup.send(f"'{found_song_name}' をキューの最後に追加したわ。順番が来たら再生するわね。")
                else:
                    await interaction.followup.send(f"'{found_song_name}' をキューに追加して、再生を開始するわ 🎶")
                    asyncio.create_task(self._play_next_song(guild_id))

        except Exception as e:
            logger.error(f"/playmusic コマンドエラー (ギルド {guild_id}): {e}", exc_info=True)
            # キューから追加しようとした曲を削除 (失敗した場合)
            if self.music_queues.get(guild_id) and self.music_queues[guild_id][-1] == (song_path, found_song_name):
                self.music_queues[guild_id].pop()
            await interaction.followup.send("音楽の再生準備中に問題が発生したわ💦 ちょっと確認してみるわね。")

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
            current_vc.stop() # afterコールバックが呼ばれるが、キューは空なので_play_next_songは何もしない
        else:
            # キューの先頭（次に再生される曲）の名前を取得
            _, next_song_name = queue[0]
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

        embed = discord.Embed(title="🎵 再生待機中の曲リスト 🎵", color=discord.Color.purple())
        
        queue_description = ""
        # キューの曲は (song_path, song_name) のタプル
        for i, (_, song_name) in enumerate(queue): # enumerate(self.music_queues[guild_id])
            queue_description += f"{i+1}. {song_name}\n"
        
        if not queue_description:
             await interaction.followup.send("音楽キューは空っぽみたい。") # 通常ここには来ないはず
             return

        embed.description = queue_description
        embed.set_footer(text=f"全 {len(queue)} 曲が待機中") # len(self.music_queues[guild_id])
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