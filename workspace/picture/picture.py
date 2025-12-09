import sys
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageEnhance, ImageFilter
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel, QFileDialog,
    QVBoxLayout, QHBoxLayout, QSlider, QGroupBox, QButtonGroup, QMessageBox,
    QStyle, QProgressBar
)
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PyQt6.QtCore import Qt


def resource_path(relative_path: str) -> str:
    """
    PyInstaller로 빌드된 exe 안/밖 모두에서 쓸 수 있는 리소스 경로 헬퍼.
    """
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# waifu2x-ncnn-vulkan.exe 경로 (빌드 후에도 동작)
WAIFU2X_PATH = resource_path(os.path.join("waifu2x-ncnn-vulkan", "waifu2x-ncnn-vulkan.exe"))

SIZE_OPTIONS = [("원본", None), ("400px", 400), ("600px", 600),
                ("800px", 800), ("960px", 960), ("1280px", 1280)]
UPSCALE_OPTIONS = [("없음", 1.0), ("1.5배", 1.5), ("2배", 2.0)]
UPSCALE_STRENGTH_OPTIONS = [("부드럽게", 0), ("보통", 1), ("강하게", 2)]
FILTER_OPTIONS = ["없음", "흑백", "세피아", "밝게", "고대비", "채도", "블러"]
FORMAT_OPTIONS = ["원본 유지", "JPEG", "PNG", "WebP", "JFIF"]

# 드래그/열기 대상 확장자
SUPPORTED_EXTS = [
    ".png", ".jpg", ".jpeg", ".webp", ".jfif", ".bmp",
    ".gif", ".tif", ".tiff", ".avif", ".heic"
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("사진 ncnn 업스케일 & 필터 도구 v1.0 by 최준혁")
        self.setAcceptDrops(True)  # 드래그 앤 드롭 허용

        # 아이콘 설정 (pic.png)
        self.setWindowIcon(QIcon(resource_path("pic.png")))

        self.state = ImageState()

        # 현재 이미지 경로/이름, 다운로드 폴더
        self.current_image_path: Optional[str] = None
        self.download_dir: Optional[str] = None

        self._build_ui()

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

        # 폴더 열기 버튼
        self.btn_open_folder = QPushButton()
        self.btn_open_folder.setToolTip("다운로드 폴더 열기")
        self.btn_open_folder.setEnabled(False)  # 처음엔 비활성화
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
            "업스케일 (배율)", UPSCALE_OPTIONS, self.on_upscale_changed
        )
        controls_layout.addWidget(self.upscale_group["group_box"])

        # 업스케일 강도 (waifu2x noise level)
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

        # 강도 슬라이더 (필터 강도)
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

        # 빈 공간(위쪽으로 밀기)
        controls_layout.addStretch()

        # 진행 상태 표시용 프로그레스바 (왼쪽 패널 맨 아래)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("대기 중")
        controls_layout.addWidget(self.progress_bar)

        # 오른쪽: 미리보기
        self.preview_label = QLabel("이미지를 불러오세요.\n(여러 장을 드래그하면 일괄 처리)")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.preview_label, 1)

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

    # ---------------- 진행 상태 헬퍼 ----------------
    def progress_busy(self, text: str):
        """무한 로딩(업스케일/처리 중) 표시."""
        self.progress_bar.setRange(0, 0)  # busy 상태
        self.progress_bar.setFormat(text)
        self.progress_bar.setTextVisible(True)
        QApplication.processEvents()

    def progress_reset(self, text: str = "대기 중"):
        """처리 완료 후 초기 상태."""
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
        """
        지정된 다운로드 폴더를 파일 탐색기로 연다.
        """
        if not self.download_dir:
            QMessageBox.warning(self, "경고", "다운로드 폴더가 지정되지 않았습니다.")
            return

        path = self.download_dir

        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # Windows
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])  # macOS
            else:
                subprocess.Popen(["xdg-open", path])  # Linux
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
            img = Image.open(file_path)
        except Exception as e:
            QMessageBox.warning(
                self,
                "이미지 열기 실패",
                f"이미지를 열 수 없습니다.\n\n파일: {file_path}\n에러: {e}",
            )
            return

        self.current_image_path = file_path
        self.state.original_format = img.format or "PNG"
        self.state.original = img.convert("RGB")
        self.btn_save.setEnabled(True)
        self.update_preview()

    def open_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "이미지 선택",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.jfif *.bmp *.gif *.tif *.tiff *.avif *.heic);;All Files (*)",
        )
        if not file_path:
            return
        self.load_image(file_path)

    # ---------------- 단일 저장 (바로 저장) ----------------
    def save_image(self):
        if not self.state.original:
            return

        # 다운로드 폴더 없으면 먼저 지정 요청
        if not self.download_dir:
            if not self.choose_download_folder():
                QMessageBox.warning(self, "경고", "다운로드 폴더가 지정되지 않았습니다.")
                return

        # 진행 표시: 단일 이미지 처리
        self.progress_busy("이미지 처리 중...")

        try:
            img = self.build_processed_image(self.state.original)
            self.state.processed = img

            # 파일 형식 & 확장자 결정
            if self.current_image_path:
                orig_name, orig_ext = os.path.splitext(os.path.basename(self.current_image_path))
            else:
                orig_name, orig_ext = "output", ".png"

            fmt = self.state.output_format
            if fmt == "원본 유지":
                # 원본 확장자 사용
                out_ext = orig_ext.lstrip(".") or "png"
                save_format = (self.state.original_format or out_ext).upper()
            else:
                save_format = fmt.upper()
                if save_format == "WEBP":
                    out_ext = "webp"
                elif save_format == "JFIF":
                    out_ext = "jfif"
                    save_format = "JPEG"
                elif save_format == "JPEG":
                    out_ext = "jpg"
                elif save_format == "PNG":
                    out_ext = "png"
                else:
                    out_ext = save_format.lower()

            # 같은 이름으로 저장 (이미 존재하면 _1, _2... 붙이기)
            target_path = self._unique_save_path(self.download_dir, orig_name, out_ext)
            img.save(target_path, format=save_format)
            print(f"[SAVE] {target_path}")

            QMessageBox.information(self, "저장 완료", f"이미지가 저장되었습니다.\n{target_path}")
        finally:
            self.progress_reset()

    @staticmethod
    def _unique_save_path(folder: str, base_name: str, ext: str) -> str:
        """
        folder/base_name.ext 가 있으면 base_name_1.ext, base_name_2.ext ... 로 저장.
        원본 파일은 건드리지 않고, 바뀐 파일만 새로 생성.
        """
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

        # 1) 크기(가로 기준)
        if self.state.size_width:
            w = self.state.size_width
            ow, oh = img.size
            h = int(oh * (w / ow))
            img = img.resize((w, h), Image.Resampling.LANCZOS)

        # 2) ncnn 업스케일
        if self.state.upscale > 1.0:
            img = self.upscale_with_ncnn(
                img,
                self.state.upscale,
                self.state.upscale_strength
            )

        # 3) 필터
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

        # 미리보기에서는 속도 때문에 Pillow 업스케일만 사용
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

        # 1개면 단일 로딩
        if len(paths) == 1:
            self.load_image(paths[0])
        else:
            # 여러 개면 배치 처리
            self.batch_process(paths)

        event.acceptProposedAction()

    # ---------------- 배치 처리 ----------------
    def batch_process(self, paths):
        # 다운로드 폴더 없으면 먼저 지정
        if not self.download_dir:
            if not self.choose_download_folder():
                QMessageBox.warning(self, "경고", "다운로드 폴더가 지정되지 않았습니다.")
                return

        total = len(paths)
        success_count = 0
        fail_count = 0

        # 배치 처리용 프로그레스바 (0 ~ total)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"배치 처리 중... (0/{total})")
        QApplication.processEvents()

        for idx, path in enumerate(paths):
            try:
                img = Image.open(path).convert("RGB")
            except Exception as e:
                fail_count += 1
                print(f"로드 실패: {path} -> {e}")
                # 진행도 업데이트
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

            # 파일 이름/확장자 결정
            base_name = os.path.basename(path)
            name, ext = os.path.splitext(base_name)

            fmt = self.state.output_format
            original_format = (Image.open(path).format or "PNG")  # 원본 포맷 확인
            if fmt == "원본 유지":
                fmt = original_format
            save_format = fmt.upper()

            if save_format == "WEBP":
                out_ext = "webp"
            elif save_format == "JFIF":
                out_ext = "jfif"
                save_format = "JPEG"
            elif save_format == "JPEG":
                out_ext = "jpg"
            elif save_format == "PNG":
                out_ext = "png"
            else:
                out_ext = save_format.lower()

            # 배치는 원본이름_edit 형식으로 저장 (원본 보호)
            out_path = self._unique_save_path(self.download_dir, f"{name}_edit", out_ext)

            try:
                processed.save(out_path, format=save_format)
                success_count += 1
            except Exception as e:
                print(f"저장 실패: {out_path} -> {e}")
                fail_count += 1

            # 진행도 업데이트
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

    # ---------------- ncnn 업스케일 호출 ----------------
    def upscale_with_ncnn(self, img: Image.Image, scale: float, strength: int) -> Image.Image:
        """
        waifu2x-ncnn-vulkan을 이용한 업스케일.
        - scale: 1.5 또는 2.0 (UI 기준)
        - strength: 0(부드럽게) / 1(보통) / 2(강하게) → noise level 매핑
        """
        if not WAIFU2X_PATH or not os.path.exists(WAIFU2X_PATH):
            print("[NCNN] 경로 없음 또는 잘못됨, Pillow 리사이즈로 대체")
            w, h = img.size
            new_size = (int(w * scale), int(h * scale))
            return img.resize(new_size, Image.Resampling.LANCZOS)

        # 모델 폴더 체크 (exe와 같은 폴더 기준)
        exe_dir = os.path.dirname(WAIFU2X_PATH)
        model_dir = os.path.join(exe_dir, "models-cunet")
        if not os.path.isdir(model_dir):
            print(f"[NCNN] 모델 폴더 없음: {model_dir}")
            print("       waifu2x-ncnn-vulkan.zip 전체를 풀어서 exe와 models-* 폴더들이 함께 있어야 합니다.")
            w, h = img.size
            new_size = (int(w * scale), int(h * scale))
            return img.resize(new_size, Image.Resampling.LANCZOS)

        noise_level = {0: 0, 1: 1, 2: 2}.get(strength, 1)

        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "in.png")
            mid_path = os.path.join(tmpdir, "mid.png")
            out_path = os.path.join(tmpdir, "out.png")

            img.save(in_path, format="PNG")

            waifu_scale = 2 if scale > 1.0 else 1
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

                # 🔹 Windows에서 waifu2x 콘솔 창 숨기기
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
                up_img = Image.open(mid_path).convert("RGB")
            except Exception as e:
                print("[NCNN] 실행 실패, Pillow fallback:", e)
                w, h = img.size
                new_size = (int(w * scale), int(h * scale))
                return img.resize(new_size, Image.Resampling.LANCZOS)

            if scale == 1.5:
                w0, h0 = img.size
                target_size = (int(w0 * 1.5), int(h0 * 1.5))
                up_img = up_img.resize(target_size, Image.Resampling.LANCZOS)

            up_img.save(out_path, format="PNG")
            return up_img

    # ---------------- 필터 ----------------
    def apply_filter(self, img: Image.Image, name: str, intensity: float) -> Image.Image:
        if name == "없음" or intensity <= 0:
            return img

        if name == "흑백":
            gray = img.convert("L").convert("RGB")
            return Image.blend(img, gray, intensity)

        elif name == "세피아":
            sepia = Image.new("RGB", img.size)
            pixels = sepia.load()
            src = img.load()
            for y in range(img.size[1]):
                for x in range(img.size[0]):
                    r, g, b = src[x, y]
                    tr = int(0.393 * r + 0.769 * g + 0.189 * b)
                    tg = int(0.349 * r + 0.686 * g + 0.168 * b)
                    tb = int(0.272 * r + 0.534 * g + 0.131 * b)
                    pixels[x, y] = (min(255, tr), min(255, tg), min(255, tb))
            return Image.blend(img, sepia, intensity)

        elif name == "밝게":
            factor = 0.5 + intensity * 1.5
            return ImageEnhance.Brightness(img).enhance(factor)

        elif name == "고대비":
            factor = 0.5 + intensity * 1.5
            return ImageEnhance.Contrast(img).enhance(factor)

        elif name == "채도":
            factor = 0.5 + intensity * 1.5
            return ImageEnhance.Color(img).enhance(factor)

        elif name == "블러":
            radius = intensity * 5.0
            return img.filter(ImageFilter.GaussianBlur(radius))

        return img

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
