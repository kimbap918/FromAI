# settings_dialog.py

import os
import sys
from pathlib import Path
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from dotenv import load_dotenv, set_key

def get_app_data_path():
    """응용 프로그램 데이터를 저장할 경로를 반환하고, 기존 .env가 있으면 복사합니다."""
    # 개발 중인 경우 또는 리눅스/맥의 경우 기본 경로
    default_path = str(Path(__file__).parent.parent.parent.parent / '.env')
    
    if not getattr(sys, 'frozen', False):
        return default_path
        
    # EXE로 패키징된 경우
    if sys.platform == 'win32':
        app_data = os.getenv('APPDATA')
        app_name = 'NewsGenerator'
        app_dir = Path(app_data) / app_name
        app_dir.mkdir(exist_ok=True, parents=True)
        new_env_path = str(app_dir / '.env')
        
        # 기존 .env 파일이 있고, 새 경로에 .env가 없으면 복사
        if os.path.exists(default_path) and not os.path.exists(new_env_path):
            try:
                import shutil
                shutil.copy2(default_path, new_env_path)
                print(f"기존 .env 파일을 새 위치로 복사했습니다: {new_env_path}")
            except Exception as e:
                print(f"기존 .env 파일 복사 중 오류 발생: {e}")
                
        return new_env_path
        
    return default_path

# .env 파일 경로 설정
DOTENV_PATH = get_app_data_path()

# 디버깅을 위한 정보 출력
print(f"Current working directory: {os.getcwd()}")
print(f"Using .env path: {DOTENV_PATH}")

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API 키 설정")
        self.setModal(True)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout()

        # API Key 설정
        api_key_layout = QHBoxLayout()
        api_key_label = QLabel("Google API Key:")
        self.api_key_input = QLineEdit()
        api_key_layout.addWidget(api_key_label)
        api_key_layout.addWidget(self.api_key_input)
        layout.addLayout(api_key_layout)

        # 버튼
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("저장")
        self.save_button.clicked.connect(self.save_settings)
        self.cancel_button = QPushButton("취소")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def load_settings(self):
        # .env 파일이 없으면 생성
        if not os.path.exists(DOTENV_PATH):
            open(DOTENV_PATH, 'a').close()
        
        load_dotenv(dotenv_path=DOTENV_PATH)
        api_key = os.getenv("GOOGLE_API_KEY", "")
        self.api_key_input.setText(api_key)

    def save_settings(self):
        new_api_key = self.api_key_input.text().strip()

        if not new_api_key:
            QMessageBox.warning(self, "입력 오류", "API 키를 입력해주세요.")
            return

        try:
            # .env 파일에 키 저장
            set_key(DOTENV_PATH, "GOOGLE_API_KEY", new_api_key)
            # 현재 실행 중인 세션의 환경 변수에도 즉시 반영
            os.environ["GOOGLE_API_KEY"] = new_api_key
            QMessageBox.information(self, "저장 완료", "API 키가 성공적으로 저장되었습니다. 프로그램을 재시작해주세요.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", f"API 키를 저장하는 중 오류가 발생했습니다:\n{e}")
