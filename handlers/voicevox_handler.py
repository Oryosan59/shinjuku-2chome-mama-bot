# c:\Users\super\デスクトップ\新宿二丁目のオネエ\handlers\voicevox_handler.py
import requests
import logging
from config import VOICEVOX_BASE_URL, VOICEVOX_SPEAKER_ID # configから読み込み

logger = logging.getLogger(__name__)

def synthesize_voice(text: str, speaker: int = VOICEVOX_SPEAKER_ID, output_path="output.wav"):
    """
    VOICEVOX APIを使用して音声を合成する関数。
    """
    try:
        # 音声生成のためのクエリ作成
        query_url = f"{VOICEVOX_BASE_URL}/audio_query"
        query_params = {"text": text, "speaker": speaker}
        response_query = requests.post(query_url, params=query_params)
        response_query.raise_for_status()  # エラーがあれば例外を発生

        # 実際の音声を合成
        synthesis_url = f"{VOICEVOX_BASE_URL}/synthesis"
        synthesis_params = {"speaker": speaker}
        synthesis_headers = {"Content-Type": "application/json"}
        response_synthesis = requests.post(
            synthesis_url,
            params=synthesis_params,
            headers=synthesis_headers,
            json=response_query.json()
        )
        response_synthesis.raise_for_status() # エラーがあれば例外を発生

        # 合成した音声をファイルとして保存
        with open(output_path, "wb") as f:
            f.write(response_synthesis.content)
        logger.info(f"音声を合成しました: {output_path}")
        return output_path
    except requests.exceptions.RequestException as e:
        logger.error(f"VOICEVOX APIリクエストエラー: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"VOICEVOX APIレスポンス: {e.response.status_code} {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"VOICEVOX音声合成中に予期せぬエラー: {e}")
        return None

