# c:\Users\super\デスクトップ\新宿二丁目のオネエ\handlers\gemini_handler.py
import google.generativeai as genai
import logging
from config import GEMINI_API_KEY, GEMINI_MODEL_NAME # configから読み込み

logger = logging.getLogger(__name__)

class GeminiHandler:
    def __init__(self):
        if not GEMINI_API_KEY:
            logger.error("Gemini APIキーが設定されていません。")
            raise ValueError("Gemini APIキーが設定されていません。")
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        logger.info(f"Geminiモデルを初期化しました: {GEMINI_MODEL_NAME}")

    async def generate_response(self, prompt: str) -> str | None:
        """
        指定されたプロンプトに基づいてGeminiから応答を生成します。
        """
        try:
            response = await self.model.generate_content_async(prompt)
            if response and hasattr(response, "text") and response.text.strip():
                logger.info("Geminiからの応答を正常に取得しました。")
                return response.text.strip()
            else:
                logger.warning("Geminiからの応答が空か、期待した形式ではありませんでした。")
                return None
        except Exception as e:
            logger.error(f"Gemini APIでの応答生成中にエラー: {e}")
            return None

