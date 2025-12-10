import sys
import os
import subprocess
import tempfile
import json
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageEnhance, ImageFilter

# ----------------- [SVG] 추가된 모듈 -----------------
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel, QFileDialog,
    QVBoxLayout, QHBoxLayout, QSlider, QGroupBox, QButtonGroup, QMessageBox,
    QStyle, QProgressBar, QInputDialog
)
from PyQt6.QtGui import QPixmap, QImage, QIcon, QPainter
from PyQt6.QtCore import Qt
from PyQt6.QtSvg import QSvgRenderer
# -----------------------------------------------------


def resource_path(relative_path: str) -> str:
    """
    PyInstaller로 빌드된 exe 안/밖 모두에서 쓸 수 있는 리소스 경로 헬퍼.
    """
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# 실행 파일 기준 설정 저장 위치
CONFIG_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
PRESET_FILE = os.path.join(CONFIG_DIR, "presets.json")

# waifu2x-ncnn-vulkan.exe 경로 (빌드 후에도 동작)
WAIFU2X_PATH = resource_path(os.path.join("waifu2x-ncnn-vulkan", "waifu2x-ncnn-vulkan.exe"))

SIZE_OPTIONS = [("원본", None), ("400px", 400), ("600px", 600),
                ("800px", 800), ("960px", 960), ("1280px", 1280)]
UPSCALE_OPTIONS = [("없음", 1.0), ("1.5배", 1.5), ("2배", 2.0), ("3배", 3.0), ("4배", 4.0)]
UPSCALE_STRENGTH_OPTIONS = [("부드럽게", 0), ("보통", 1), ("강하게", 2)]
FILTER_OPTIONS = ["없음", "흑백", "세피아", "밝게", "고대비", "채도", "블러"]
FORMAT_OPTIONS = ["원본 유지", "JPEG", "JPG", "PNG", "WebP", "JFIF"]

# 드래그/열기 대상 확장자
SUPPORTED_EXTS = [
    ".png", ".jpg", ".jpeg", ".webp", ".jfif", ".bmp",
    ".gif", ".tif", ".tiff", ".avif", ".heic",
    ".svg",
]


@dataclass
class ImageState:
    original: Optional[Image.Image] = None
    processed: Optional[Image.Image] = None
    original_format: Optional[str] = None
    size_width: Optional[int] = None
    upscale: float = 1.0
    upscale_strength: int = 1       # 0=부드럽게,1=보통,2=강하게
    filter_name: str = "없음"
    intensity: float = 1.0          # 필터 강도 (0~1)
    output_format: str = "원본 유지"


class PresetButton(QPushButton):
    """
    좌클릭: 프리셋 불러오기
    우클릭: 현재 설정 저장 + 이름 변경
    """
    def __init__(self, index: int, owner: "MainWindow"):
        super().__init__()
        self.index = index
        self.owner = owner

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.owner.on_preset_right_clicked(self.index)
        elif event.button() == Qt.MouseButton.LeftButton:
            self.owner.on_preset_left_clicked(self.index)
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("사진 ncnn 업스케일 & 필터 도구 v1.0.0 by 최준혁")
        self.setAcceptDrops(True)  # 드래그 앤 드롭 허용

        icon_path = resource_path("pic.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.state = ImageState()
        self.current_image_path: Optional[str] = None
        self.download_dir: Optional[str] = None

        # 프리셋 관련
        self.preset_buttons = []
        self.presets = []  # [{ "name": str, "settings": dict | None }, ... ]

        self._build_ui()
        self.load_presets()
        self.refresh_preset_buttons()

    # ---------------- UI 구성 ----------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)

        # 왼쪽 패널
        controls_layout = QVBoxLayout()
        main_layout.addLayout(controls_layout, 0)

        # 열기/다운로드
        io_layout = QHBoxLayout()
        self.btn_open = QPushButton("이미지 열기")
        self.btn_save = QPushButton("다운로드 (단일)")
        self.btn_save.setEnabled(False)
        self.btn_open.clicked.connect(self.open_image)
        self.btn_save.clicked.connect(self.save_image)
        io_layout.addWidget(self.btn_open)
        io_layout.addWidget(self.btn_save)
        controls_layout.addLayout(io_layout)

        # 다운로드 폴더 지정
        folder_layout = QHBoxLayout()

        self.btn_select_folder = QPushButton("다운로드 폴더 지정")
        self.btn_select_folder.clicked.connect(self.choose_download_folder)

        self.btn_open_folder = QPushButton()
        self.btn_open_folder.setToolTip("다운로드 폴더 열기")
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        self.btn_open_folder.clicked.connect(self.open_download_folder)

        self.lbl_download_folder = QLabel("지정 안 됨")
        self.lbl_download_folder.setStyleSheet("color: gray;")

        folder_layout.addWidget(self.btn_select_folder)
        folder_layout.addWidget(self.btn_open_folder)
        folder_layout.addWidget(self.lbl_download_folder)

        controls_layout.addLayout(folder_layout)

        # 이미지 크기
        self.size_group = self._create_button_group(
            "이미지 크기", SIZE_OPTIONS, self.on_size_changed
        )
        controls_layout.addWidget(self.size_group["group_box"])

        # 업스케일 배율
        self.upscale_group = self._create_button_group(
            "업스케일 (배율, 1.5배~2배 권장)", UPSCALE_OPTIONS, self.on_upscale_changed
        )
        controls_layout.addWidget(self.upscale_group["group_box"])

        # 업스케일 강도
        self.upscale_strength_group = self._create_button_group(
            "업스케일 강도", UPSCALE_STRENGTH_OPTIONS, self.on_upscale_strength_changed
        )
        controls_layout.addWidget(self.upscale_strength_group["group_box"])

        # 필터
        filter_group_box = QGroupBox("필터")
        filter_layout = QHBoxLayout()
        filter_group_box.setLayout(filter_layout)
        self.filter_button_group = QButtonGroup()
        self.filter_button_group.setExclusive(True)
        for name in FILTER_OPTIONS:
            btn = QPushButton(name)
            btn.setCheckable(True)
            if name == "없음":
                btn.setChecked(True)
            self.filter_button_group.addButton(btn)
            self.filter_button_group.setId(btn, FILTER_OPTIONS.index(name))
            filter_layout.addWidget(btn)
        self.filter_button_group.buttonClicked.connect(self.on_filter_changed)
        controls_layout.addWidget(filter_group_box)

        # 강도 슬라이더
        slider_layout = QVBoxLayout()
        row = QHBoxLayout()
        row.addWidget(QLabel("필터 강도"))
        self.lbl_intensity_value = QLabel("100%")
        row.addStretch()
        row.addWidget(self.lbl_intensity_value)
        slider_layout.addLayout(row)

        self.slider_intensity = QSlider(Qt.Orientation.Horizontal)
        self.slider_intensity.setMinimum(0)
        self.slider_intensity.setMaximum(100)
        self.slider_intensity.setValue(100)
        self.slider_intensity.valueChanged.connect(self.on_intensity_changed)
        slider_layout.addWidget(self.slider_intensity)
        controls_layout.addLayout(slider_layout)

        # 파일 형식
        format_group_box = QGroupBox("파일 형식")
        format_layout = QHBoxLayout()
        format_group_box.setLayout(format_layout)
        self.format_button_group = QButtonGroup()
        self.format_button_group.setExclusive(True)
        for name in FORMAT_OPTIONS:
            btn = QPushButton(name)
            btn.setCheckable(True)
            if name == "원본 유지":
                btn.setChecked(True)
            self.format_button_group.addButton(btn)
            self.format_button_group.setId(btn, FORMAT_OPTIONS.index(name))
            format_layout.addWidget(btn)
        self.format_button_group.buttonClicked.connect(self.on_format_changed)
        controls_layout.addWidget(format_group_box)

        # ----------- 설정 프리셋 버튼 5개 -----------
        preset_group_box = QGroupBox("설정 프리셋 (좌클릭: 불러오기 / 우클릭: 저장·이름변경)")
        preset_layout = QHBoxLayout()
        preset_group_box.setLayout(preset_layout)

        for i in range(5):
            btn = PresetButton(i, self)
            btn.setText(f"프리셋 {i+1}")
            btn.setToolTip("좌클릭: 프리셋 불러오기 / 우클릭: 현재 설정 저장 및 이름 변경")
            self.preset_buttons.append(btn)
            preset_layout.addWidget(btn)

        controls_layout.addWidget(preset_group_box)
        # ----------------------------------------

        controls_layout.addStretch()

        # 진행 상태 표시용 프로그레스바
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("대기 중")
        controls_layout.addWidget(self.progress_bar)

        # 오른쪽: 미리보기 + 라이선스
        right_layout = QVBoxLayout()
        main_layout.addLayout(right_layout, 1)

        self.preview_label = QLabel("이미지를 불러오세요.\n(여러 장을 드래그하면 일괄 처리)")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 투명 배경이 잘 보이도록 배경색 설정
        self.preview_label.setStyleSheet("background-color: #f0f0f0;")
        right_layout.addWidget(self.preview_label, 1)

        # waifu2x 라이선스 표시 (오른쪽 아래 작게)
        self.license_label = QLabel(
            'This software uses "waifu2x-ncnn-vulkan" (MIT License)'
        )
        self.license_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.license_label.setStyleSheet("color: gray; font-size: 9px;")
        right_layout.addWidget(self.license_label, 0)

    def _create_button_group(self, title, options, callback):
        group_box = QGroupBox(title)
        layout = QHBoxLayout()
        group_box.setLayout(layout)
        button_group = QButtonGroup()
        button_group.setExclusive(True)
        for idx, (label, _value) in enumerate(options):
            btn = QPushButton(label)
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)
            button_group.addButton(btn)
            button_group.setId(btn, idx)
            layout.addWidget(btn)
        button_group.buttonClicked.connect(lambda _: callback())
        return {"group_box": group_box, "button_group": button_group, "options": options}

    # ---------------- 프리셋 로드/세이브 ----------------
    def load_presets(self):
        """presets.json 에서 프리셋 불러오기 (없으면 기본값 생성)."""
        self.presets = []
        if os.path.exists(PRESET_FILE):
            try:
                with open(PRESET_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for i in range(5):
                        if i < len(data) and isinstance(data[i], dict):
                            name = data[i].get("name", f"프리셋 {i+1}")
                            settings = data[i].get("settings")
                            self.presets.append({"name": name, "settings": settings})
                        else:
                            self.presets.append({"name": f"프리셋 {i+1}", "settings": None})
                    return
            except Exception as e:
                print(f"[Preset] 로드 실패: {e}")

        # 파일 없거나 실패 시 기본값
        self.presets = [{"name": f"프리셋 {i+1}", "settings": None} for i in range(5)]

    def save_presets(self):
        """현재 self.presets를 presets.json에 저장."""
        try:
            with open(PRESET_FILE, "w", encoding="utf-8") as f:
                json.dump(self.presets, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Preset] 저장 실패: {e}")

    def refresh_preset_buttons(self):
        """버튼 텍스트를 self.presets 기준으로 갱신."""
        for i, btn in enumerate(self.preset_buttons):
            if i < len(self.presets):
                name = self.presets[i].get("name", f"프리셋 {i+1}")
            else:
                name = f"프리셋 {i+1}"
            btn.setText(name)

    # ---------------- 프리셋 버튼 동작 ----------------
    def on_preset_left_clicked(self, index: int):
        """좌클릭: 프리셋 불러오기."""
        if index >= len(self.presets):
            return
        preset = self.presets[index]
        settings = preset.get("settings")
        if not settings:
            QMessageBox.information(
                self,
                "프리셋 없음",
                "저장된 설정이 없습니다.\n우클릭으로 현재 설정을 이 프리셋에 저장할 수 있습니다.",
            )
            return
        self.apply_preset(settings)

    def on_preset_right_clicked(self, index: int):
        """우클릭: 현재 설정 저장 + 이름 변경."""
        if index >= len(self.presets):
            return
        if not self.state:
            return

        # 이름 입력
        current_name = self.presets[index].get("name", f"프리셋 {index+1}")
        name, ok = QInputDialog.getText(
            self,
            "프리셋 저장",
            "프리셋 이름을 입력하세요:",
            text=current_name,
        )
        if not ok or not name.strip():
            return

        # 현재 상태 저장
        settings = {
            "size_width": self.state.size_width,
            "upscale": self.state.upscale,
            "upscale_strength": self.state.upscale_strength,
            "filter_name": self.state.filter_name,
            "intensity": self.state.intensity,
            "output_format": self.state.output_format,
        }
        self.presets[index] = {"name": name.strip(), "settings": settings}
        self.refresh_preset_buttons()
        self.save_presets()

        QMessageBox.information(
            self,
            "프리셋 저장",
            f"현재 설정을 '{name}' 프리셋에 저장했습니다.\n(좌클릭으로 불러올 수 있습니다.)",
        )

    def apply_preset(self, settings: dict):
        """딕셔너리로 저장된 설정을 상태 + UI에 반영."""
        # 상태 복원
        self.state.size_width = settings.get("size_width")
        self.state.upscale = settings.get("upscale", 1.0)
        self.state.upscale_strength = settings.get("upscale_strength", 1)
        self.state.filter_name = settings.get("filter_name", "없음")
        self.state.intensity = settings.get("intensity", 1.0)
        self.state.output_format = settings.get("output_format", "원본 유지")

        # 크기 버튼 복원
        sw = self.state.size_width
        size_idx = 0
        for i, (_, val) in enumerate(self.size_group["options"]):
            if val == sw:
                size_idx = i
                break
        self.size_group["button_group"].button(size_idx).setChecked(True)

        # 업스케일 배율 버튼 복원
        up = self.state.upscale
        up_idx = 0
        for i, (_, val) in enumerate(self.upscale_group["options"]):
            if val == up:
                up_idx = i
                break
        self.upscale_group["button_group"].button(up_idx).setChecked(True)

        # 업스케일 강도 복원
        st = self.state.upscale_strength
        st_idx = 0
        for i, (_, val) in enumerate(self.upscale_strength_group["options"]):
            if val == st:
                st_idx = i
                break
        self.upscale_strength_group["button_group"].button(st_idx).setChecked(True)

        # 필터 복원
        try:
            f_idx = FILTER_OPTIONS.index(self.state.filter_name)
        except ValueError:
            f_idx = 0
            self.state.filter_name = FILTER_OPTIONS[0]
        self.filter_button_group.button(f_idx).setChecked(True)

        # 강도 슬라이더 복원
        v = int(self.state.intensity * 100)
        v = max(0, min(100, v))
        self.slider_intensity.setValue(v)
        self.lbl_intensity_value.setText(f"{v}%")

        # 파일 형식 복원
        try:
            fmt_idx = FORMAT_OPTIONS.index(self.state.output_format)
        except ValueError:
            fmt_idx = 0
            self.state.output_format = FORMAT_OPTIONS[0]
        self.format_button_group.button(fmt_idx).setChecked(True)

        # 미리보기 갱신
        self.update_preview()

    # ---------------- 진행 상태 헬퍼 ----------------
    def progress_busy(self, text: str):
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFormat(text)
        self.progress_bar.setTextVisible(True)
        QApplication.processEvents()

    def progress_reset(self, text: str = "대기 중"):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(text)
        self.progress_bar.setTextVisible(True)
        QApplication.processEvents()

    # ---------------- 다운로드 폴더 ----------------
    def choose_download_folder(self) -> bool:
        folder = QFileDialog.getExistingDirectory(
            self,
            "다운로드 폴더 선택",
            self.download_dir or "",
        )
        if folder:
            self.download_dir = folder
            self.lbl_download_folder.setText(self._shorten_path(folder))
            self.lbl_download_folder.setStyleSheet("color: black;")
            self.btn_open_folder.setEnabled(True)
            return True
        return False

    def open_download_folder(self):
        if not self.download_dir:
            QMessageBox.warning(self, "경고", "다운로드 폴더가 지정되지 않았습니다.")
            return

        path = self.download_dir

        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(
                self,
                "폴더 열기 실패",
                f"폴더를 열 수 없습니다.\n\n경로: {path}\n에러: {e}",
            )

    @staticmethod
    def _shorten_path(path: str, max_len: int = 40) -> str:
        if len(path) <= max_len:
            return path
        return "..." + path[-(max_len - 3):]

    # ---------------- 파일/이미지 로딩 ----------------
    def is_image_file(self, path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in SUPPORTED_EXTS

    def load_image(self, file_path: str):
        try:
            # [SVG] SVG는 QSvgRenderer로 렌더링 후 PIL로 변환
            if file_path.lower().endswith(".svg"):
                img = self.load_svg_to_pil(file_path)
                self.state.original_format = "SVG"
            else:
                img = Image.open(file_path)
                self.state.original_format = img.format or "PNG"

            # 무조건 RGB 변환 금지. RGBA도 유지.
            if img.mode not in ["RGB", "RGBA"]:
                img = img.convert("RGBA")

        except Exception as e:
            QMessageBox.warning(
                self,
                "이미지 열기 실패",
                f"이미지를 열 수 없습니다.\n\n파일: {file_path}\n에러: {e}",
            )
            return

        self.current_image_path = file_path
        self.state.original = img
        self.btn_save.setEnabled(True)
        self.update_preview()

    def open_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "이미지 선택",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.jfif *.bmp *.gif *.tif *.tiff *.avif *.heic *.svg);;All Files (*)",
        )
        if not file_path:
            return
        self.load_image(file_path)

    # ---------------- [SVG] SVG 로딩 함수 ----------------
    def load_svg_to_pil(self, path: str) -> Image.Image:
        """
        QSvgRenderer를 사용하여 SVG를 렌더링 후 PIL Image로 변환.
        """
        renderer = QSvgRenderer(path)
        if not renderer.isValid():
            raise ValueError(f"유효하지 않은 SVG 파일입니다: {path}")

        size = renderer.defaultSize()
        w, h = size.width(), size.height()

        if w <= 0 or h <= 0:
            w, h = 1000, 1000

        qimg = QImage(w, h, QImage.Format.Format_ARGB32)
        qimg.fill(Qt.GlobalColor.transparent)

        painter = QPainter(qimg)
        renderer.render(painter)
        painter.end()

        return self.qimage_to_pil_static(qimg)

    @staticmethod
    def qimage_to_pil_static(qimg: QImage) -> Image.Image:
        qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
        width = qimg.width()
        height = qimg.height()

        ptr = qimg.bits()
        ptr.setsize(qimg.sizeInBytes())
        arr = ptr.asstring(qimg.sizeInBytes())

        pil_img = Image.frombuffer("RGBA", (width, height), arr, "raw", "RGBA", 0, 1)
        return pil_img

    # ---------------- 단일 저장 ----------------
    def save_image(self):
        if not self.state.original:
            return

        if not self.download_dir:
            if not self.choose_download_folder():
                QMessageBox.warning(self, "경고", "다운로드 폴더가 지정되지 않았습니다.")
                return

        self.progress_busy("이미지 처리 중...")

        try:
            img = self.build_processed_image(self.state.original)
            self.state.processed = img

            if self.current_image_path:
                orig_name, orig_ext = os.path.splitext(os.path.basename(self.current_image_path))
            else:
                orig_name, orig_ext = "output", ".png"

            fmt = self.state.output_format
            is_svg = (orig_ext.lower() == ".svg")

            if fmt == "원본 유지":
                if is_svg:
                    save_format = "PNG"   # SVG는 PNG로 저장
                    out_ext = "png"
                else:
                    out_ext = orig_ext.lstrip(".") or "png"
                    save_format = (self.state.original_format or out_ext).upper()
                    if save_format == "SVG":
                        save_format = "PNG"
                        out_ext = "png"
            else:
                fmt_upper = fmt.upper()

                if fmt_upper == "WEBP":
                    save_format = "WEBP"
                    out_ext = "webp"

                elif fmt_upper == "JFIF":
                    save_format = "JPEG"
                    out_ext = "jfif"

                elif fmt_upper == "JPEG":
                    save_format = "JPEG"
                    out_ext = "jpeg"

                elif fmt_upper == "JPG":
                    save_format = "JPEG"
                    out_ext = "jpg"

                elif fmt_upper == "PNG":
                    save_format = "PNG"
                    out_ext = "png"

                else:
                    save_format = fmt_upper
                    out_ext = save_format.lower()

            target_path = self._unique_save_path(self.download_dir, orig_name, out_ext)

            # JPEG 등 투명 미지원 포맷은 흰색 배경 합성
            if save_format in ["JPEG", "JFIF", "BMP"] and img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode == "RGBA" and save_format not in ["PNG", "WEBP"]:
                img = img.convert("RGB")

            img.save(target_path, format=save_format)
            print(f"[SAVE] {target_path}")

            QMessageBox.information(self, "저장 완료", f"이미지가 저장되었습니다.\n{target_path}")
        finally:
            self.progress_reset()

    @staticmethod
    def _unique_save_path(folder: str, base_name: str, ext: str) -> str:
        candidate = os.path.join(folder, f"{base_name}.{ext}")
        if not os.path.exists(candidate):
            return candidate
        idx = 1
        while True:
            candidate = os.path.join(folder, f"{base_name}_{idx}.{ext}")
            if not os.path.exists(candidate):
                return candidate
            idx += 1

    # ---------------- 공통 처리 파이프라인 ----------------
    def build_processed_image(self, base_img: Image.Image) -> Image.Image:
        img = base_img

        if self.state.size_width:
            w = self.state.size_width
            ow, oh = img.size
            h = int(oh * (w / ow))
            img = img.resize((w, h), Image.Resampling.LANCZOS)

        if self.state.upscale > 1.0:
            img = self.upscale_with_ncnn(
                img,
                self.state.upscale,
                self.state.upscale_strength
            )

        img = self.apply_filter(img, self.state.filter_name, self.state.intensity)
        return img

    # ---------------- 상태 변경 콜백 ----------------
    def on_size_changed(self):
        idx = self.size_group["button_group"].checkedId()
        _, width = self.size_group["options"][idx]
        self.state.size_width = width
        self.update_preview()

    def on_upscale_changed(self):
        idx = self.upscale_group["button_group"].checkedId()
        _, factor = self.upscale_group["options"][idx]
        self.state.upscale = factor
        self.update_preview()

    def on_upscale_strength_changed(self):
        idx = self.upscale_strength_group["button_group"].checkedId()
        _, level = self.upscale_strength_group["options"][idx]
        self.state.upscale_strength = level

    def on_filter_changed(self):
        idx = self.filter_button_group.checkedId()
        self.state.filter_name = FILTER_OPTIONS[idx]
        self.update_preview()

    def on_intensity_changed(self, value):
        self.state.intensity = max(0.0, min(1.0, value / 100.0))
        self.lbl_intensity_value.setText(f"{value}%")
        self.update_preview()

    def on_format_changed(self):
        idx = self.format_button_group.checkedId()
        self.state.output_format = FORMAT_OPTIONS[idx]

    # ---------------- 미리보기 ----------------
    def update_preview(self):
        if not self.state.original:
            return

        img = self.state.original

        if self.state.size_width:
            w = self.state.size_width
            ow, oh = img.size
            h = int(oh * (w / ow))
            img = img.resize((w, h), Image.Resampling.LANCZOS)

        if self.state.upscale > 1.0:
            w, h = img.size
            new_size = (int(w * self.state.upscale), int(h * self.state.upscale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        img = self.apply_filter(img, self.state.filter_name, self.state.intensity)
        self.state.processed = img

        qimg = self.pil_to_qimage(img)
        pixmap = QPixmap.fromImage(qimg)
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.state.processed:
            qimg = self.pil_to_qimage(self.state.processed)
            pixmap = QPixmap.fromImage(qimg)
            self.preview_label.setPixmap(
                pixmap.scaled(
                    self.preview_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    # ---------------- 드래그 & 드롭 ----------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and self.is_image_file(url.toLocalFile()):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if self.is_image_file(path):
                    paths.append(path)

        if not paths:
            event.ignore()
            return

        if len(paths) == 1:
            self.load_image(paths[0])
        else:
            self.batch_process(paths)

        event.acceptProposedAction()

    # ---------------- 배치 처리 ----------------
    def batch_process(self, paths):
        if not self.download_dir:
            if not self.choose_download_folder():
                QMessageBox.warning(self, "경고", "다운로드 폴더가 지정되지 않았습니다.")
                return

        total = len(paths)
        success_count = 0
        fail_count = 0

        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"배치 처리 중... (0/{total})")
        QApplication.processEvents()

        for idx, path in enumerate(paths):
            try:
                # SVG 별도 처리
                if path.lower().endswith(".svg"):
                    img = self.load_svg_to_pil(path)
                    original_format = "SVG"
                else:
                    img = Image.open(path)
                    original_format = img.format or "PNG"

                if img.mode not in ["RGB", "RGBA"]:
                    img = img.convert("RGBA")

            except Exception as e:
                fail_count += 1
                print(f"로드 실패: {path} -> {e}")
                self.progress_bar.setValue(idx + 1)
                self.progress_bar.setFormat(f"배치 처리 중... ({idx + 1}/{total})")
                QApplication.processEvents()
                continue

            try:
                processed = self.build_processed_image(img)
            except Exception as e:
                fail_count += 1
                print(f"처리 실패: {path} -> {e}")
                self.progress_bar.setValue(idx + 1)
                self.progress_bar.setFormat(f"배치 처리 중... ({idx + 1}/{total})")
                QApplication.processEvents()
                continue

            base_name = os.path.basename(path)
            name, ext = os.path.splitext(base_name)

            fmt = self.state.output_format
            is_svg = (ext.lower() == ".svg") or (original_format == "SVG")

            if fmt == "원본 유지":
                if is_svg:
                    save_format = "PNG"
                    out_ext = "png"
                else:
                    current_fmt = original_format if original_format else ext.lstrip(".").upper()
                    save_format = current_fmt
                    out_ext = ext.lstrip(".")
            else:
                fmt_upper = fmt.upper()

                if fmt_upper == "WEBP":
                    save_format = "WEBP"
                    out_ext = "webp"

                elif fmt_upper == "JFIF":
                    save_format = "JPEG"
                    out_ext = "jfif"

                elif fmt_upper == "JPEG":
                    save_format = "JPEG"
                    out_ext = "jpeg"

                elif fmt_upper == "JPG":
                    save_format = "JPEG"
                    out_ext = "jpg"

                elif fmt_upper == "PNG":
                    save_format = "PNG"
                    out_ext = "png"

                else:
                    save_format = fmt_upper
                    out_ext = save_format.lower()

            out_path = self._unique_save_path(self.download_dir, f"{name}_edit", out_ext)

            try:
                # 배치 저장 시 투명도 처리
                if save_format in ["JPEG", "JFIF", "BMP"] and processed.mode == "RGBA":
                    bg = Image.new("RGB", processed.size, (255, 255, 255))
                    bg.paste(processed, mask=processed.split()[3])
                    processed = bg
                elif processed.mode == "RGBA" and save_format not in ["PNG", "WEBP"]:
                    processed = processed.convert("RGB")

                processed.save(out_path, format=save_format)
                success_count += 1
            except Exception as e:
                print(f"저장 실패: {out_path} -> {e}")
                fail_count += 1

            self.progress_bar.setValue(idx + 1)
            self.progress_bar.setFormat(f"배치 처리 중... ({idx + 1}/{total})")
            QApplication.processEvents()

        self.progress_reset()

        QMessageBox.information(
            self,
            "배치 처리 완료",
            f"총 {total}개 중 {success_count}개 성공, {fail_count}개 실패했습니다.\n"
            f"저장 폴더: {self.download_dir}",
        )

    # ---------------- ncnn 업스케일 ----------------
    def upscale_with_ncnn(self, img: Image.Image, scale: float, strength: int) -> Image.Image:
        """
        waifu2x-ncnn-vulkan을 이용한 업스케일.
        - scale: 원하는 최종 배율 (1.5, 2, 3, 4 등)
        - 내부적으로는 2배 또는 4배로 업스케일 후, 나머지는 Pillow로 보정
        """
        if scale <= 1.0:
            return img

        # waifu2x 실행 불가 → Pillow로 대체
        if not WAIFU2X_PATH or not os.path.exists(WAIFU2X_PATH):
            print("[NCNN] 경로 없음 또는 잘못됨, Pillow 리사이즈로 대체")
            w, h = img.size
            new_size = (int(w * scale), int(h * scale))
            return img.resize(new_size, Image.Resampling.LANCZOS)

        exe_dir = os.path.dirname(WAIFU2X_PATH)
        model_dir = os.path.join(exe_dir, "models-cunet")
        if not os.path.isdir(model_dir):
            print(f"[NCNN] 모델 폴더 없음: {model_dir}")
            w, h = img.size
            new_size = (int(w * scale), int(h * scale))
            return img.resize(new_size, Image.Resampling.LANCZOS)

        noise_level = {0: 0, 1: 1, 2: 2}.get(strength, 1)

        # waifu2x에서 사용할 기저 배율: 2배 또는 4배
        if scale <= 2.0:
            waifu_scale = 2
        else:
            waifu_scale = 4

        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "in.png")
            mid_path = os.path.join(tmpdir, "mid.png")

            img.save(in_path, format="PNG")

            cmd = [
                WAIFU2X_PATH,
                "-i", in_path,
                "-o", mid_path,
                "-n", str(noise_level),
                "-s", str(waifu_scale),
                "-f", "png",
            ]

            try:
                print("[NCNN] 실행:", " ".join(cmd))
                creationflags = 0
                startupinfo = None
                if sys.platform.startswith("win"):
                    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                subprocess.run(
                    cmd,
                    check=True,
                    cwd=exe_dir,
                    creationflags=creationflags,
                    startupinfo=startupinfo,
                )

                print("[NCNN] 성공, 결과 읽는 중")
                if os.path.exists(mid_path):
                    with Image.open(mid_path) as temp_img:
                        up_img = temp_img.convert("RGBA").copy()
                else:
                    raise FileNotFoundError("Output file not created")

            except Exception as e:
                print("[NCNN] 실행 실패, Pillow fallback:", e)
                w, h = img.size
                new_size = (int(w * scale), int(h * scale))
                return img.resize(new_size, Image.Resampling.LANCZOS)

            # 최종 목표 크기(원본 * 원하는 배율)로 리사이즈
            orig_w, orig_h = img.size
            target_size = (int(orig_w * scale), int(orig_h * scale))

            if up_img.size != target_size:
                up_img = up_img.resize(target_size, Image.Resampling.LANCZOS)

            return up_img

    # ---------------- 필터 ----------------
    def apply_filter(self, img: Image.Image, name: str, intensity: float) -> Image.Image:
        if name == "없음" or intensity <= 0:
            return img

        alpha = None
        if img.mode == "RGBA":
            alpha = img.split()[3]
            base_img = img.convert("RGB")
        else:
            base_img = img.convert("RGB")

        if name == "흑백":
            gray = base_img.convert("L").convert("RGB")
            filtered = Image.blend(base_img, gray, intensity)

        elif name == "세피아":
            sepia = Image.new("RGB", base_img.size)
            pixels = sepia.load()
            src = base_img.load()
            width, height = base_img.size
            for y in range(height):
                for x in range(width):
                    r, g, b = src[x, y]
                    tr = int(0.393 * r + 0.769 * g + 0.189 * b)
                    tg = int(0.349 * r + 0.686 * g + 0.168 * b)
                    tb = int(0.272 * r + 0.534 * g + 0.131 * b)
                    pixels[x, y] = (min(255, tr), min(255, tg), min(255, tb))
            filtered = Image.blend(base_img, sepia, intensity)

        elif name == "밝게":
            factor = 0.5 + intensity * 1.5
            filtered = ImageEnhance.Brightness(base_img).enhance(factor)

        elif name == "고대비":
            factor = 0.5 + intensity * 1.5
            filtered = ImageEnhance.Contrast(base_img).enhance(factor)

        elif name == "채도":
            factor = 0.5 + intensity * 1.5
            filtered = ImageEnhance.Color(base_img).enhance(factor)

        elif name == "블러":
            radius = intensity * 5.0
            filtered = base_img.filter(ImageFilter.GaussianBlur(radius))
        else:
            filtered = base_img

        if alpha:
            filtered.putalpha(alpha)

        return filtered

    # ---------------- 유틸 ----------------
    @staticmethod
    def pil_to_qimage(pil_img: Image.Image) -> QImage:
        if pil_img.mode != "RGBA":
            pil_img = pil_img.convert("RGBA")
        data = pil_img.tobytes("raw", "RGBA")
        qimg = QImage(
            data,
            pil_img.size[0],
            pil_img.size[1],
            QImage.Format.Format_RGBA8888,
        )
        return qimg


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(900, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
