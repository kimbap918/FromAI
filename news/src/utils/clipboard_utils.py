# utils/clipboard_utils.py

import io
from PIL import Image

try:
    import win32clipboard
    import win32con
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 이미지를 클립보드에 복사하는 함수(공통 유틸)
# ------------------------------------------------------------------
def copy_image_to_clipboard(image_path: str) -> bool:
    """
    주어진 이미지 파일을 윈도우 클립보드에 복사합니다 (Windows 전용)
    :param image_path: 이미지 경로
    :return: 성공 여부
    """
    if not CLIPBOARD_AVAILABLE:
        print("❌ 클립보드 복사 기능이 지원되지 않는 환경입니다.")
        return False

    try:
        image = Image.open(image_path).convert('RGB')
        output = io.BytesIO()
        image.save(output, 'BMP')
        data = output.getvalue()[14:]  # BMP 헤더 제거
        output.close()

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, data)
        win32clipboard.CloseClipboard()

        print("✅ 이미지가 클립보드에 복사되었습니다.")
        return True

    except Exception as e:
        try:
            win32clipboard.CloseClipboard()
        except:
            pass
        print(f"❌ 클립보드 복사 실패: {e}")
        return False
