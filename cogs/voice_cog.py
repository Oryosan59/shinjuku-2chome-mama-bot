# c:\Users\super\デスクトOP\新宿二丁目のオネエ\cogs\voice_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
import os # output.wavを削除するために追加
from config import BASE_VOICE_PROMPT, GUILDS # configから読み込み
from handlers.gemini_handler import GeminiHandler
from handlers.voicevox_handler import synthesize_voice


logger = logging.getLogger(__name__)

class VoiceCog(commands.Cog):
    def __init__(self, bot: commands.Bot, gemini_handler: GeminiHandler):
        self.bot = bot
        self.gemini_handler = gemini_handler
        self.vc_connections = {}  # ギルドIDをキーにしたVC接続の辞書
        self.music_pause_states = {} # ギルドID: bool (Trueならvoice再生前にmusicをpauseした)
        self.auto_disconnect_tasks = {} # ギルドIDをキーにした自動退出タスクの辞書
        if not BASE_VOICE_PROMPT:
            logger.warning("voiceコマンド用のベースプロンプトが読み込まれていません。")

    def get_vc_connection(self, guild_id: int) -> discord.VoiceClient | None:
        return self.vc_connections.get(guild_id)

    def set_vc_connection(self, guild_id: int, vc: discord.VoiceClient | None):
        if vc is None and guild_id in self.vc_connections:
            del self.vc_connections[guild_id]
        elif vc:
            self.vc_connections[guild_id] = vc

    async def _check_and_auto_disconnect(self, guild_id: int, initial_vc_channel_id: int):
        logger.info(f"自動退出監視開始: ギルド {guild_id}, チャンネル {initial_vc_channel_id}")
        await asyncio.sleep(10) # 初期遅延

        while True:
            vc = self.get_vc_connection(guild_id)
            if not vc or not vc.is_connected() or vc.channel.id != initial_vc_channel_id:
                logger.info(f"自動退出監視: VC切断またはチャンネル移動のため監視終了 (ギルド {guild_id})")
                if guild_id in self.auto_disconnect_tasks: # タスクリストからも削除
                    del self.auto_disconnect_tasks[guild_id]
                return # タスク終了

            # ボット自身を除いたメンバー数をカウント
            human_members = [member for member in vc.channel.members if not member.bot]
            if not human_members: # ボット以外のメンバーがいない
                logger.info(f"VC ({vc.channel.name}) に他のユーザーがいなくなったため退出します (ギルド {guild_id})")
                await vc.disconnect()
                self.set_vc_connection(guild_id, None)
                if guild_id in self.auto_disconnect_tasks: # タスクリストからも削除
                    del self.auto_disconnect_tasks[guild_id]
                return # タスク終了
            
            await asyncio.sleep(20) # チェック間隔

    @app_commands.command(name="voice", description="ママに喋ってもらうわよ♪")
    @app_commands.guilds(*GUILDS)
    async def voice_gemini_command(self, interaction: discord.Interaction, *, question: str):
        logger.info(f"/voice 質問: {question} from {interaction.user} in {interaction.guild.name}")
        await interaction.response.defer(thinking=True)

        if not interaction.guild:
            await interaction.followup.send("このコマンドはサーバー内でのみ使用可能です。")
            return
        
        guild_id = interaction.guild.id

        if not BASE_VOICE_PROMPT:
            await interaction.followup.send(f"ごめんなさい、voice用の設定がうまくいってないみたい…")
            return

        try:
            full_prompt = BASE_VOICE_PROMPT + question
            answer_text = await self.gemini_handler.generate_response(full_prompt)

            if not answer_text:
                await interaction.followup.send("返答が生成できなかったわ…もう一度試してみて。")
                return

            await interaction.followup.send(f"🎤 **読み上げるわね♪**\n> {question}\n\n{answer_text}")

            output_filename = f"output_{guild_id}.wav" # ギルドごとにファイル名を分ける
            wav_path = synthesize_voice(answer_text, output_path=output_filename)
            if not wav_path:
                await interaction.followup.send("VOICEVOXで音声を生成できなかったわ…ごめんなさいね。")
                return
            
            # --- MusicCog連携 ---
            music_cog = self.bot.get_cog("MusicCog")
            self.music_pause_states[guild_id] = False # 初期化
            active_music_vc = None

            if music_cog and hasattr(music_cog, 'pause_current_song') and hasattr(music_cog, 'resume_current_song'):
                active_music_vc = music_cog.get_vc_connection(guild_id)
                if active_music_vc and active_music_vc.is_connected() and active_music_vc.is_playing():
                    if await music_cog.pause_current_song(guild_id):
                        self.music_pause_states[guild_id] = True
                        logger.info(f"音楽を一時停止しました (ギルド {guild_id}) for voice playback")
            # --- MusicCog連携ここまで ---

            if interaction.user.voice is None or interaction.user.voice.channel is None:
                await interaction.followup.send("ボイスチャンネルに入ってから呼んでちょうだい🎧")
                if os.path.exists(wav_path): os.remove(wav_path)
                return

            vc_channel = interaction.user.voice.channel
            target_vc_for_voice = None # 音声再生に使うVC

            # MusicCogがユーザーと同じチャンネルに接続済みなら、それを利用
            if active_music_vc and active_music_vc.is_connected() and active_music_vc.channel == vc_channel:
                target_vc_for_voice = active_music_vc
                logger.info(f"MusicCogのVCを音声再生に使用します (ギルド {guild_id})")
                # VoiceCog自身のVC管理は更新しない (MusicCogがプライマリの可能性)
            else:
                # MusicCogがいないか、違うチャンネルにいる場合、VoiceCogが接続/移動
                voice_cog_vc = self.get_vc_connection(guild_id)
                if voice_cog_vc is None or not voice_cog_vc.is_connected():
                    target_vc_for_voice = await vc_channel.connect()
                    self.set_vc_connection(guild_id, target_vc_for_voice) # VoiceCogが管理
                elif voice_cog_vc.channel != vc_channel:
                    await voice_cog_vc.move_to(vc_channel)
                    target_vc_for_voice = voice_cog_vc # VoiceCogが管理
                else:
                    target_vc_for_voice = voice_cog_vc # VoiceCogが管理

            if target_vc_for_voice.is_playing(): # 何か再生中なら止める (MusicCogの再生は既にpauseされているはず)
                target_vc_for_voice.stop()

            target_vc_for_voice.play(discord.FFmpegPCMAudio(source=wav_path), after=lambda e: self.after_playing(e, wav_path, guild_id))
            
            # 自動退出タスクの管理 (VoiceCogがVCを能動的に確保した場合のみ)
            # MusicCogのVCを借りている場合は、MusicCogの管理に任せる（現状MusicCogに自動退出はない）
            # もしtarget_vc_for_voice が self.get_vc_connection(guild_id) と同じなら、VoiceCogが管理しているVC

            if guild_id in self.auto_disconnect_tasks and self.auto_disconnect_tasks[guild_id]:
                if not self.auto_disconnect_tasks[guild_id].done():
                    self.auto_disconnect_tasks[guild_id].cancel()
                    logger.info(f"既存の自動退出タスクをキャンセルしました (ギルド {guild_id})")
                del self.auto_disconnect_tasks[guild_id] # 古いタスクを削除

            # 新しい自動退出タスクを開始
            # target_vc_for_voice が self.vc_connections[guild_id] と同じインスタンスか確認
            if self.get_vc_connection(guild_id) == target_vc_for_voice and target_vc_for_voice.is_connected():
                 logger.info(f"自動退出監視タスクを開始します (ギルド {guild_id}, チャンネル {target_vc_for_voice.channel.id})")
                 task = self.bot.loop.create_task(self._check_and_auto_disconnect(guild_id, target_vc_for_voice.channel.id))
                 self.auto_disconnect_tasks[guild_id] = task
            else:
                logger.warning(f"VC接続がないため自動退出監視を開始しません (ギルド {guild_id})")

        except Exception as e:
            logger.error(f"/voice コマンドエラー (ギルド {guild_id}): {e}", exc_info=True)
            await interaction.followup.send("読み上げ中に問題が発生したわ💦 ちょっと確認してみるわね。")
            # エラー時にも音声ファイルを削除トライ
            if 'wav_path' in locals() and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception as ex_rem:
                    logger.error(f"エラー後の音声ファイル削除に失敗: {ex_rem}")


    def after_playing(self, error, filepath: str, guild_id: int):
        if error:
            logger.error(f'音声再生エラー (ギルド {guild_id}): {error}')
        else:
            logger.info(f'音声再生完了 (ギルド {guild_id}): {filepath}')
        
        # 再生が終わったファイルを削除
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                logger.info(f"音声ファイルを削除しました: {filepath}")
            except Exception as e:
                logger.error(f"音声ファイルの削除に失敗しました: {filepath}, エラー: {e}")
       
        # --- MusicCog連携: 音楽の再開 ---
        was_music_paused = self.music_pause_states.pop(guild_id, False)
        if was_music_paused:
            music_cog = self.bot.get_cog("MusicCog")
            if music_cog and hasattr(music_cog, 'resume_current_song'):
                logger.info(f"音声再生完了、音楽の再開を試みます (ギルド {guild_id})")
                if self.bot.loop.is_running():
                    asyncio.run_coroutine_threadsafe(music_cog.resume_current_song(guild_id), self.bot.loop)
                else:
                    logger.warning(f"ボットループが実行されていないため、音楽を再開できません (ギルド {guild_id})")
            elif music_cog:
                logger.warning(f"MusicCogにresume_current_songメソッドがありません (ギルド {guild_id})")
            else:
                logger.warning(f"MusicCogが見つかりません。音楽を再開できません (ギルド {guild_id})")
        # --- MusicCog連携ここまで ---

        # 自動退出タスクがまだ動いていなければ（例えば手動で切断された後など）、
        # 再度起動する必要はないかもしれないが、状況に応じて検討。
        # ここでは、再生終了後に自動退出タスクがまだ存在し、かつVCが接続されていれば
        # そのまま監視を継続させる。もしVCが切断されていればタスクは自動的に終了するはず。
        vc = self.get_vc_connection(guild_id)
        if not (vc and vc.is_connected()):
             logger.info(f"再生終了後、VCが切断されているため自動退出タスクの再確認は不要 (ギルド {guild_id})")
             if guild_id in self.auto_disconnect_tasks:
                 if not self.auto_disconnect_tasks[guild_id].done():
                     self.auto_disconnect_tasks[guild_id].cancel() #念のためキャンセル
                 del self.auto_disconnect_tasks[guild_id]


async def setup(bot: commands.Bot):
    # VoiceCogに渡すGeminiHandlerはAskCogと同じインスタンスを使い回すか、
    # もしくはここで新しく生成するか。今回はAskCogで生成したものを渡す想定ではないので新しく作る。
    # ただし、リソース効率を考えると、botインスタンスにhandlerを持たせて共有するのがベター。
    # ここでは簡単のため、各Cogで必要に応じて生成する形を取るが、改善の余地あり。
    gemini_h = GeminiHandler()
    await bot.add_cog(VoiceCog(bot, gemini_h), guilds=GUILDS)
    logger.info("VoiceCogが正常にロードされました。")

