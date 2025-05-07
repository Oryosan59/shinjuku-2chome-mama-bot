
# 新宿二丁目のママDiscordボット ReadMe

このボットは、新宿二丁目のママ「シズエ」が、あなたのDiscordサーバーで愛と毒のあるアドバイスをくれたり、おしゃべりしたり、時には素敵な音楽を流したりするボットよ💋

## 💖 プロジェクト構成

アタシたちの秘密基地はこんな感じになっているわ。

``` bash
新宿二丁目のママ/
│
├── bot.py             # メインの起動ファイル：アタシを目覚めさせる呪文が書いてあるわ
├── config.py          # 設定ファイル：APIキーとか、秘密の合言葉をしまっておく場所よ
├── .env               # 環境変数ファイル (例)：ここにも秘密の鍵を隠しておくの (Gitには含めないでね！)
├── requirements.txt   # 必要な魔法の材料リスト (Pythonライブラリ)
├── prompt/            # プロンプトファイル用フォルダ：アタシの人格設定が書かれてるの
│   ├── q.txt          # /q コマンド用のアタシの台本
│   └── voice.txt      # /voice コマンド用のアタシの台本 (140字以内の指示とかね)
├── cogs/              # コマンド関連のモジュール (Cog) を入れるフォルダ：アタシの得意技が増える場所よ
│   ├── __init__.py     # cogsフォルダをPythonに「ここも見てちょうだい」と教えるおまじない
│   ├── ask_cog.py      # /q コマンド (テキストで質問) の魔法
│   ├── voice_cog.py    # /voice コマンド (音声で質問) とボイスチャット関連の魔法
│   └── music_cog.py    # 音楽再生関連の魔法 (NEW!)
├── handlers/          # 外部サービスとの連携処理：GeminiちゃんやVOICEVOXさんとお話しするための道具箱よ
│   ├── __init__.py    # handlersフォルダもPythonに教えてあげるおまじない
│   ├── gemini_handler.py  # Gemini AIとお話しするための魔法
│   └── voicevox_handler.py # VOICEVOXでアタシの美声を合成するための魔法
└── music/                 # 音楽ファイルを置くフォルダ (NEW!)
```

## 🚀 セットアップ方法

アタシをアンタのサーバーに呼ぶための準備よ。

1. **Pythonの準備**:
    * Python 3.10以上を推奨するわ。
    * 仮想環境 (venv) を使うと、他のプロジェクトと魔法が混ざらなくて安心よ。

        ```bash
        python -m venv venv
        source venv/bin/activate  # Linux/macOS の場合
        venv\Scripts\activate     # Windows の場合
        ```

2. **必要な魔法の材料 (ライブラリ) を集める**:
    * `requirements.txt` を作って、以下の材料を書いておくの。

        ```txt
        # 新宿二丁目のママ\requirements.txt の内容例
        discord.py
        google-generativeai
        python-dotenv
        requests
        # 他にも使っているライブラリがあれば追記してね
        PyNaCl # Discord.pyの音声機能を使うなら入れておくと安心よ
        ```

    * そして、この呪文で材料をインストールするのよ。

        ```bash
        pip install -r requirements.txt
        ```

3. **秘密の鍵 (.envファイル) を用意する**:
    * `新宿二丁目のママ` フォルダに `.env` という名前のファイルを作って、こんな感じで秘密の情報を書くの。

        ```env
        #.env の内容例
        DISCORD_BOT_TOKEN="あなたのDiscordボットトークン"
        GEMINI_API_KEY="あなたのGemini APIキー"
        DISCORD_GUILD_IDS="XXXXXXXXXXXXXXXXXXX,XXXXXXXXXXXXXXXXXXX"
        ```

    * **注意**: この `.env` ファイルは、絶対にGitとかで公開しちゃダメよ！秘密は守るものよ。

4. **VOICEVOXの準備**:
    * アタシの美声を聴きたいなら、VOICEVOXエンジンをダウンロードして、起動しておいてちょうだいね。
        * VOICEVOX公式サイト: [https://voicevox.hiroshiba.jp/](https://voicevox.hiroshiba.jp/)
        * CPU版とGPU版があるけど、よくわからなければCPU版で大丈夫よ。
        * ダウンロードしたら、解凍して `run.exe` (Windowsの場合) を実行すればエンジンが起動するわ。
    * `新宿二丁目のママ\config.py` の `VOICEVOX_BASE_URL` が、アンタのVOICEVOXエンジンのアドレスと合っているか確認してね (通常は `http://127.0.0.1:50021` よ)。
    * VOICEVOXエンジンが起動していないと、`/voice` コマンドでアタシは喋れないから気をつけてね。

5. **音楽再生の準備 (NEW!)**:
    * `https://discord.com/developers/applications/` でアンタのボットを選んで、「Bot」セクションに行くの。
    * 「Privileged Gateway Intents」のところにある「MESSAGE CONTENT INTENT」をオンにしてちょうだい。アタシがアンタたちのメッセージを読めるようにするためよ。
    * **FFmpegのインストール**:
        音楽を再生するには FFmpeg が必要よ。お使いのシステムにインストールして、実行ファイルへのパスが通っている（環境変数PATHに追加されている）ことを確認してちょうだい。
        * FFmpeg公式サイト: <https://ffmpeg.org/download.html>
        * Windowsなら、「FFmpeg Builds」(<https://www.gyan.dev/ffmpeg/builds/>) から `ffmpeg-release-essentials.zip` などをダウンロードして、解凍したフォルダの中の `bin` フォルダにパスを通すのが簡単かしらね。
    * **`music` フォルダの作成**:
        プロジェクトのルートディレクトリ（`bot.py` がある場所）に `music` という名前のフォルダを作成して、そこに再生したい音楽ファイル（例: `my_song.mp3`, `theme.wav`）を入れてね。
        `.gitignore` に `music/*` を追加しておくと、個々の音楽ファイルがリポジトリに含まれなくてスッキリするわよ。

6. **Discord Developer Portalでの設定**:
    * `https://discord.com/developers/applications/` でアンタのボットを選んで、「Bot」セクションに行くの。
    * 「Privileged Gateway Intents」のところにある「MESSAGE CONTENT INTENT」をオンにしてちょうだい。アタシがアンタたちのメッセージを読めるようにするためよ。

7. **プロンプトファイルの確認**:
    * `新宿二丁目のママ\prompt\` フォルダに `q.txt` と `voice.txt` がちゃんとあるか確認してね。アタシの人格形成に不可欠なの。

## 💃 ボットの起動

準備が整ったら、いよいよアタシの出番よ！

```bash
cd 新宿二丁目のママ
python bot.py
```

これでアタシがDiscordにログインして、アンタたちとお話しできるようになるわ。

## 🎤 アタシの得意技 (主なコマンド)

アタシにできることをちょっとだけ教えてあげるわね💋

* **おしゃべり系**:
  * `/q [質問文]` : アタシにテキストで質問できるわ。愛と毒のあるアドバイスをあげる。
  * `/voice [話してほしいこと]` : アタシがボイスチャンネルで直接お話しするわよ。
* **音楽再生系 (NEW!)**:
  * `/listmusic` : `music` フォルダにある再生可能な曲の一覧を表示するわ。
  * `/playmusic [曲名]` : 指定された曲を再生するわ。再生中ならキューに追加するの。
  * `/stopmusic` : 今再生している音楽を止めるわ（キューは残るわよ）。
  * `/skipmusic` : 今の曲をスキップして、キューの次の曲を再生するわ。
  * `/queuemusic` : 今の音楽再生キューを表示するわ。
  * `/clearmusicqueue` : 音楽再生キューを空にするわ。
  * `/leavemusic` : ボイスチャンネルから退出して、キューも空にするわ。

他にも隠れた機能があるかもしれないから、色々試してみてちょうだいね。

---

## ✨ コマンドの拡張方法 (アタシに新しい得意技を教える方法)

アタシにもっといろんなことをさせたい？いいじゃない、その心意気！
新しいスラッシュコマンドを追加する方法を教えてあげるわね。

1. **新しいCogファイルを作る**:
    * `新宿二丁目のママ\cogs\` フォルダに、新しいPythonファイルを作るの。例えば、おみくじ機能なら `omikuji_cog.py` みたいな感じね。

2. **Cogクラスを定義する**:
    * その新しいファイルに、`discord.ext.commands.Cog` を継承したクラスを作るのよ。

        ```python
        # 新宿二丁目のママ\cogs\omikuji_cog.py の例
        import discord
        from discord.ext import commands
        from discord import app_commands
        from config import GUILDS # ギルドIDをconfigから読み込む
        # 必要なら他のhandlerとかもインポートしてね

        class OmikujiCog(commands.Cog):
            def __init__(self, bot: commands.Bot):
                self.bot = bot

            @app_commands.command(name="omikuji", description="今日の運勢を占ってあげるわよ💋")
            @app_commands.guilds(*GUILDS) # どのサーバーで使えるようにするか指定
            async def omikuji_command(self, interaction: discord.Interaction):
                await interaction.response.send_message("今日のアンタの運勢は… 大吉よ！いいことあるわよ、きっと💋") # ここに実際の処理を書くの

        async def setup(bot: commands.Bot):
            await bot.add_cog(OmikujiCog(bot), guilds=GUILDS)
            print("OmikujiCogがロードされたわよ！") # ログに出ると分かりやすいわね
        ```

3. **`bot.py` に新しいCogを登録する**:
    * `新宿二丁目のママ\bot.py` を開いて、`INITIAL_EXTENSIONS` のリストに、新しいCogのファイル名（`.py` はナシよ）を追加するの。

        ```python
        # 新宿二丁目のママ\bot.py の一部
        INITIAL_EXTENSIONS = [
            'cogs.ask_cog',
            'cogs.voice_cog',
            'cogs.omikuji_cog'  # ← こんな感じで追加するのよ
        ]
        ```

4. **ボットを再起動する**:
    * 変更を保存したら、ボットを再起動してちょうだい。そうすれば、新しいコマンドが使えるようになるわ。

もし新しいコマンドがGeminiちゃんやVOICEVOXさんみたいな外部のサービスと連携する必要があるなら、`新宿二丁目のママ\handlers\` フォルダに新しい `handler.py` を作って、それをCogから呼び出すようにすると、コードがスッキリしていいわよ。

## 🛠️ トラブルシューティング

* **`ImportError: attempted relative import beyond top-level package`**:
    CogファイルやHandlerファイルからの `config.py` や他のHandlerのインポートは、`from config import ...` や `from handlers.something_handler import ...` のように、プロジェクトのルートディレクトリ (`新宿二丁目のママ\`) からのパスで書くようにしてちょうだい。
* **`discord.errors.PrivilegedIntentsRequired`**:
    Discord Developer Portalで「MESSAGE CONTENT INTENT」を有効にしてね。
* **コマンドがDiscordに表示されない / 反映されない**:
  * `bot.py` の `on_ready` 内で `bot.tree.sync(guild=GUILD_OBJECT)` が各ギルドに対して実行されているか確認して。
  * Cogの `setup` 関数で `await bot.add_cog(...)` が呼ばれているか確認して。
  * ボットがDiscordサーバーに「アプリケーションコマンドの作成」権限を持って招待されているか確認してね。
  * コマンドを変更した後は、ボットを再起動する必要があるわ。
* **音楽が再生されない**:
  * FFmpegが正しくインストールされていて、パスが通っているか確認してちょうだい。
  * `music` フォルダに再生したい音楽ファイルが入っているか確認してね。
  * ボットがボイスチャンネルに接続する権限を持っているか確認して。
* **`/voice` コマンド実行中に `WARNING:discord.gateway:Shard ID None voice heartbeat blocked` が出る**:
  * これは、VOICEVOXへの音声合成リクエストが長引いて、Discordとの通信が一時的に滞った時に出ることがあるわ。
  * `handlers/voicevox_handler.py` の `requests.post` にタイムアウトを設定することで、ある程度は緩和できるかもしれないわね。根本的には、音声合成処理を非同期化 (例: `aiohttp` を使う) することを検討してみて。

これで、アンタも立派なボット使いよ。何か困ったことがあったら、いつでもアタシに聞いてちょうだいね💋

## 📜 ライセンス

このプロジェクトは MITライセンス のもとで公開されているわ。詳細は `LICENSE.md` ファイルを見てちょうだいね。
