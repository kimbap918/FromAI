# hwan_tab.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QHBoxLayout, QLineEdit, QPushButton, QMessageBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import os
import platform
import subprocess
import webbrowser
from datetime import datetime

from news.src.utils.exchange_utils import (
    capture_exchange_chart,
    capture_multiple_exchange_charts,
    capture_exchange_chart_with_data,
    create_fx_template,
)
from news.src.services.info_LLM import generate_info_news_from_text
from news.src.utils.common_utils import save_news_to_file

CHATBOT_URL = "https://chatgpt.com/g/g-67a44d9d833c8191bf2974019d233d4e-jeongboseong-gisa-caesbos-culceo-sanggwaneobseum"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 버전 : 1.0.0
# 기능 : PyQt5에서 환율 차트 캡처 작업 진행 상태 업데이트하는 함수(프론트)
# ------------------------------------------------------------------
class ExchangeWorker(QThread):
    finished = pyqtSignal(str, str)
    progress = pyqtSignal(str)

    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword

    def run(self):
        try:
            self.progress.emit("환율 차트 검색 중...")
            image_path = capture_exchange_chart(self.keyword)
            self.progress.emit("이미지 캡처 및 저장 중...")
            if image_path:
                self.progress.emit("환율 차트 캡처 성공! 결과가 클립보드에 복사되었습니다.")
                self.finished.emit(image_path, "")
            else:
                self.progress.emit("환율 차트 캡처에 실패했습니다.")
                self.finished.emit("", "환율 차트 캡처에 실패했습니다.")
        except Exception as e:
            self.progress.emit(f"오류 발생: {str(e)}")
            self.finished.emit("", f"오류 발생: {str(e)}")

# ------------------------------------------------------------------
# 작성자 : 팀
# 작성일 : 2025-10-13
# 기능 : 여러 통화 차트 캡처 후 텍스트 기반 LLM으로 종합 환율 뉴스 생성 워커(프론트)
# ------------------------------------------------------------------
class FXNewsWorker(QThread):
    finished = pyqtSignal(str, str)  # (saved_path, error)
    progress = pyqtSignal(str)

    def __init__(self, currencies: list[str]):
        super().__init__()
        self.currencies = currencies

    def run(self):
        try:
            self.progress.emit("여러 통화 환율 차트 캡처 시작...")
            images_dict, data_dict = capture_multiple_exchange_charts(self.currencies, progress_callback=self.progress.emit)
            if not images_dict:
                self.finished.emit("", "환율 차트 캡처 결과가 없습니다.")
                return

            # 텍스트 기반 LLM 생성을 위한 info_dict 구성
            info_dict = {
                "통화목록": list(images_dict.keys()),
                "이미지": images_dict,
                "수치": data_dict,
            }
            self.progress.emit("LLM을 통해 종합 환율 뉴스 생성 중...")
            news = generate_info_news_from_text("주요국 환율 종합", info_dict, domain="fx")
            if not news:
                self.finished.emit("", "LLM 뉴스 생성에 실패했습니다.")
                return

            # 본문 서두 템플릿 삽입 (날짜/시간은 템플릿에서만 사용)
            template_text = create_fx_template()
            import re as _re
            if _re.search(r'(\[본문\]|본문)', news):
                replacement_text = f"[본문]\n{template_text} "
                final_output = _re.sub(r'(\[본문\]|본문)\s+', replacement_text, news, count=1)
            else:
                final_output = template_text + '\n\n' + news

            # 중복 선두 템플릿 제거: 모델이 동일 성격의 시간 문구를 한 번 더 생성한 경우
            try:
                anchor = "기준, 네이버페이 증권에 따르면"
                first_idx = final_output.find(anchor)
                if first_idx != -1:
                    first_end = first_idx + len(anchor)
                    second_idx = final_output.find(anchor, first_end)
                    # 선두 근방(첫 200자 이내)에 동일 앵커가 한 번 더 나오면 첫 번째 이후 ~ 두 번째 앵커까지 제거
                    if second_idx != -1 and (second_idx - first_end) < 200:
                        # 두 번째 앵커까지 포함하여 제거
                        cut_end = second_idx + len(anchor)
                        final_output = final_output[:first_end] + final_output[cut_end:]
            except Exception:
                pass

            # 집계(종합) 기사는 캡처 이미지가 저장된 오늘자 환율 폴더에 저장
            try:
                first_image_path = next(iter(images_dict.values()))
                custom_dir = os.path.dirname(first_image_path)
            except Exception:
                custom_dir = None

            self.progress.emit("생성된 뉴스를 파일로 저장 중...")
            saved_path = save_news_to_file(
                "주요국 환율 종합",
                domain="fx",
                news_content=final_output,
                open_after_save=True,
                custom_save_dir=custom_dir,
            )
            if saved_path:
                self.finished.emit(saved_path, "")
            else:
                self.finished.emit("", "뉴스 저장에 실패했습니다.")
        except Exception as e:
            self.finished.emit("", f"오류 발생: {str(e)}")

# ------------------------------------------------------------------
# 작성자 : 팀
# 작성일 : 2025-10-13
# 기능 : 콤마로 구분된 통화 목록을 순회하며 통화별 FX 기사 생성 및 저장
# 저장 위치: 해당 통화의 차트가 저장된 오늘자 환율 폴더(예: 환율차트/환율YYYYMMDD)
# ------------------------------------------------------------------
class FXPerCurrencyWorker(QThread):
    finished = pyqtSignal(str, str)  # (last_saved_path, error)
    progress = pyqtSignal(str)

    def __init__(self, currencies: list[str]):
        super().__init__()
        self.currencies = currencies

    def run(self):
        try:
            last_saved = ""
            total = len(self.currencies)
            for i, cur in enumerate(self.currencies, start=1):
                cur = cur.strip()
                if not cur:
                    continue
                self.progress.emit(f"[{i}/{total}] '{cur}' 환율 차트 캡처 및 기사 생성 시작...")
                image_path, data = capture_exchange_chart_with_data(cur, progress_callback=self.progress.emit)
                if not image_path:
                    self.progress.emit(f"[{i}/{total}] '{cur}' 이미지 캡처 실패, 건너뜀")
                    continue

                # LLM 입력 구성 (단일 통화)
                info_dict = {
                    "통화": cur,
                    "이미지": {cur: image_path},
                    "수치": {cur: data or {}},
                }
                self.progress.emit(f"[{i}/{total}] '{cur}' LLM 기사 생성 중...")
                news = generate_info_news_from_text(f"{cur} 환율", info_dict, domain="fx")
                if not news:
                    self.progress.emit(f"[{i}/{total}] '{cur}' 기사 생성 실패, 건너뜀")
                    continue

                # 본문 서두 템플릿 삽입 및 중복 제거
                template_text = create_fx_template()
                import re as _re
                if _re.search(r'(\[본문\]|본문)', news):
                    replacement_text = f"[본문]\n{template_text} "
                    final_output = _re.sub(r'(\[본문\]|본문)\s+', replacement_text, news, count=1)
                else:
                    final_output = template_text + '\n\n' + news
                anchor = "기준, 네이버페이 증권에 따르면"
                first_idx = final_output.find(anchor)
                if first_idx != -1:
                    first_end = first_idx + len(anchor)
                    second_idx = final_output.find(anchor, first_end)
                    if second_idx != -1 and (second_idx - first_end) < 200:
                        cut_end = second_idx + len(anchor)
                        final_output = final_output[:first_end] + final_output[cut_end:]

                # 저장 경로: 이미지가 저장된 폴더(오늘자 환율 폴더)
                custom_dir = os.path.dirname(image_path)
                last_saved = save_news_to_file(f"{cur} 환율", domain="fx", news_content=final_output, open_after_save=False, custom_save_dir=custom_dir)
                if last_saved:
                    self.progress.emit(f"[{i}/{total}] '{cur}' 기사 저장 완료: {last_saved}")
                else:
                    self.progress.emit(f"[{i}/{total}] '{cur}' 기사 저장 실패")

            if last_saved:
                self.finished.emit(last_saved, "")
            else:
                self.finished.emit("", "처리 가능한 항목이 없습니다.")
        except Exception as e:
            self.finished.emit("", f"오류 발생: {str(e)}")

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 버전 : 1.0.0
# 기능 : PyQt5에서 환율 차트 탭 위젯 및 레이아웃 설정(프론트)
# ------------------------------------------------------------------
class HwanTab(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.last_image_path = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        title_label = QLabel("💱 환율 차트")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # 기존 status_label 관련 코드 제거
        # 캡처 완료 시에만 주의 메시지 표시

        input_group = QGroupBox("입력")
        input_layout = QVBoxLayout()

        keyword_layout = QHBoxLayout()
        keyword_label = QLabel("환율 키워드:")
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("예: 달러, 엔, 유로, 위안, 엔환율 등(화폐명만 입력해도 됩니다)")
        self.keyword_input.returnPressed.connect(self.capture_chart)
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        input_layout.addLayout(keyword_layout)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        button_layout = QHBoxLayout()
        self.capture_btn = QPushButton("📊 차트 캡처")
        self.capture_btn.clicked.connect(self.capture_chart)
        self.reset_btn = QPushButton("🔄 리셋")
        self.reset_btn.clicked.connect(self.reset_inputs)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_capture)
        self.cancel_btn.setEnabled(False)
        self.open_folder_btn = QPushButton("📁 폴더 열기")
        self.open_folder_btn.clicked.connect(self.open_folder)
        self.open_chatbot_btn = QPushButton("🌐 챗봇 열기")
        self.open_chatbot_btn.clicked.connect(self.open_chatbot)
        self.generate_fx_btn = QPushButton("📰 종합 환율 뉴스 생성")
        self.generate_fx_btn.clicked.connect(self.generate_fx_news)

        button_layout.addWidget(self.capture_btn)
        button_layout.addWidget(self.reset_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.open_folder_btn)
        button_layout.addWidget(self.open_chatbot_btn)
        button_layout.addWidget(self.generate_fx_btn)
        layout.addLayout(button_layout)

        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)

        self.result_label = QLabel("")
        self.result_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.result_label)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 입력 필드 리셋하는 함수(프론트)
    # ------------------------------------------------------------------
    def reset_inputs(self):
        self.keyword_input.clear()
        self.result_label.setText("")
        self.progress_label.setText("")
        self.capture_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 환율 차트 폴더 열기 함수(프론트)
    # ------------------------------------------------------------------
    def open_folder(self):
        today = datetime.now().strftime('%Y%m%d')
        folder_path = os.path.join("환율차트", f"환율{today}")
        if os.path.exists(folder_path):
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", folder_path])
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", folder_path])
        else:
            QMessageBox.information(self, "폴더 없음", "아직 캡처된 이미지가 없습니다.")

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 챗봇 열기 함수(프론트)
    # ------------------------------------------------------------------
    def open_chatbot(self):
        webbrowser.open(CHATBOT_URL, new=0)
        QMessageBox.information(self, "챗봇 열기", "정보성 기사 챗봇이 열렸습니다.")

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 환율 차트 캡처 함수(프론트)
    # ------------------------------------------------------------------
    def capture_chart(self):
        raw = self.keyword_input.text().strip()
        if not raw:
            QMessageBox.warning(self, "입력 오류", "환율 키워드를 입력해주세요.")
            return

        # 콤마로 분리하여 복수 통화 처리
        currencies = [s.strip() for s in raw.split(',') if s.strip()]
        self.capture_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.result_label.setText("")
        self.progress_label.setText("환율 차트 캡처 및 기사 생성 중...")

        # 단일/복수 통화 모두 FX 기사 생성 워커로 처리
        self.worker = FXPerCurrencyWorker(currencies)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_capture_finished)
        self.worker.start()

    # ------------------------------------------------------------------
    # 작성자 : 팀
    # 작성일 : 2025-10-13
    # 기능 : 종합 환율 뉴스 생성 트리거(프론트)
    # ------------------------------------------------------------------
    def generate_fx_news(self):
        currencies = [
            "달러",
            "엔",
            "유로",
            "위안",
            "캐나다 달러",
            "루피아",
            "레알",
        ]
        self.capture_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.generate_fx_btn.setEnabled(False)
        self.result_label.setText("")
        self.progress_label.setText("종합 환율 뉴스 생성 처리 중...")

        self.worker = FXNewsWorker(currencies)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_capture_finished)
        self.worker.start()

    def worker_run_with_progress(self):
        try:
            image_path = capture_exchange_chart(self.worker.keyword, progress_callback=self.worker.progress.emit)
            if image_path:
                self.worker.progress.emit("환율 차트 캡처 성공! 결과가 클립보드에 복사되었습니다.")
                self.worker.finished.emit(image_path, "")
            else:
                self.worker.progress.emit("환율 차트 캡처에 실패했습니다.")
                self.worker.finished.emit("", "환율 차트 캡처에 실패했습니다.")
        except Exception as e:
            self.worker.progress.emit(f"오류 발생: {str(e)}")
            self.worker.finished.emit("", f"오류 발생: {str(e)}")

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 환율 차트 캡처 취소 함수(프론트)
    # ------------------------------------------------------------------
    def cancel_capture(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
        self.progress_label.setText("⛔️ 캡처 취소됨")
        self.capture_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        try:
            self.generate_fx_btn.setEnabled(True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 환율 차트 캡처 진행 상태 업데이트하는 함수(프론트)
    # ------------------------------------------------------------------
    def update_progress(self, message):
        if any(x in message for x in ["성공", "주의", "확인", "오류"]):
            self.progress_label.setStyleSheet("color: #FFA500; font-weight: bold;")
        else:
            self.progress_label.setStyleSheet("color: black;")
        self.progress_label.setText(message)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 환율 차트 캡처 완료 시 처리하는 함수(프론트)
    # ------------------------------------------------------------------
    def on_capture_finished(self, image_path, error):
        self.capture_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        try:
            self.generate_fx_btn.setEnabled(True)
        except Exception:
            pass
        if error:
            QMessageBox.warning(self, "캡처 실패", error)
            self.progress_label.setText("")
            return

        self.result_label.setText(f"저장됨: {image_path}\n이미지가 클립보드에 복사되었습니다.")
        self.progress_label.setText("기사 작성시 내용의 오류가 없는지 확인하세요!")
        self.progress_label.setStyleSheet("color: #FFA500; font-weight: bold;")