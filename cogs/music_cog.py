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
        if error:
            logger.error(f'音楽再生エラー (ギルド {guild_id}, 曲: {song_name_played}): {error}')
        else:
            logger.info(f'音楽再生完了 (ギルド {guild_id}, 曲: {song_name_played})')
        
        # 次の曲を再生するためのタスクを作成
        # afterコールバックは同期的なコンテキストで実行されるため、非同期処理はスレッドセーフに呼び出す
        if self.bot.loop.is_running(): # ボットがまだ動作しているか確認
            asyncio.run_coroutine_threadsafe(self._play_next_song(guild_id), self.bot.loop)
        else:
            logger.warning(f"ボットループが実行されていないため、次の曲の再生を開始できません (ギルド {guild_id})")

    async def _play_next_song(self, guild_id: int):
        """キューから次の曲を再生する内部メソッド"""
        if guild_id not in self.music_queues or not self.music_queues[guild_id]:
            logger.info(f"音楽キューが空です (ギルド {guild_id})。再生を停止します。")
            # オプション: キューが空になったらVCから自動退出するロジック
            # vc = self.get_vc_connection(guild_id)
            # if vc and vc.is_connected():
            #     # await vc.channel.send("キューが空になったので、少ししたら退出するわね。")
            #     # await asyncio.sleep(60) # 60秒後に退出など
            #     # if not self.music_queues.get(guild_id): # 再度キューが空か確認
            #     #    await vc.disconnect()
            #     #    self.set_vc_connection(guild_id, None)
            return

        current_vc = self.get_vc_connection(guild_id)
        if not current_vc or not current_vc.is_connected():
            logger.warning(f"VCに接続されていません。次の曲を再生できません (ギルド {guild_id})。")
            if guild_id in self.music_queues: # VCがないならキューもクリアした方が安全
                self.music_queues[guild_id].clear()
            return

        if current_vc.is_playing() or current_vc.is_paused():
            # 通常、_after_playing から呼ばれるので、この状態は稀だが念のため
            logger.info(f"VCは既に何かを再生/一時停止中です。_play_next_songの処理をスキップします (ギルド {guild_id})。")
            return

        song_path, song_name = self.music_queues[guild_id].pop(0) # キューの先頭から取得して削除

        if not os.path.exists(song_path):
            logger.error(f"次の曲のファイルが見つかりません: {song_path} (ギルド {guild_id})")
            if current_vc.channel:
                try:
                    await current_vc.channel.send(f"あら、キューにあった '{song_name}' が見つからないみたい…？ スキップするわね。")
                except Exception as e:
                    logger.error(f"ファイル欠損通知の送信エラー: {e}")
            await self._play_next_song(guild_id) # 次の曲へ
            return

        try:
            audio_source = discord.FFmpegPCMAudio(song_path)
            current_vc.play(audio_source, after=lambda e: self._after_playing(e, guild_id, song_name))
            logger.info(f"'{song_name}' の再生を開始しました (ギルド {guild_id})")
        except Exception as e:
            logger.error(f"_play_next_song でエラー (ギルド {guild_id}, 曲: {song_name}): {e}", exc_info=True)
            if current_vc.channel:
                try:
                    await current_vc.channel.send(f"'{song_name}' の再生中に問題が発生したわ。スキップするわね。")
                except Exception as send_e:
                    logger.error(f"再生エラー通知の送信エラー: {send_e}")
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
        vc = self.get_vc_connection(guild_id)
        if vc and vc.is_connected() and vc.is_playing():
            vc.pause()
            logger.info(f"音楽を一時停止しました (ギルド {guild_id}) - 外部呼び出し")
            return True
        return False

    async def resume_current_song(self, guild_id: int):
        """指定されたギルドで一時停止中の音楽を再開するわ"""
        vc = self.get_vc_connection(guild_id)
        if vc and vc.is_connected() and vc.is_paused():
            vc.resume()
            logger.info(f"音楽を再開しました (ギルド {guild_id}) - 外部呼び出し")
            return True
        elif vc and vc.is_connected() and not vc.is_playing() and self.music_queues.get(guild_id):
            logger.info(f"音楽は停止していましたが、キューに曲があるので次の曲を再生します (ギルド {guild_id})")
            await self._play_next_song(guild_id) # 完全に止まっていたら次の曲を再生
            return True
        return False

async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot), guilds=GUILDS)
    logger.info("MusicCogが正常にロードされました。")