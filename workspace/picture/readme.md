# PressAI Filter & Upscale 모듈


PressAI의 **Image Repository** 내에 새롭게 통합될 `filter & upscale` 기능에 대한 기술 및 가이드입니다.
본 문서는 Python (PyQt6 + Pillow) 기반 데스크톱 도구 코드를 바탕으로 작성되었습니다.

<br>

Google Drive : https://drive.google.com/file/d/1v-pThOJqVrfXUjsTklRKgZL4K9K-O-wg/view?usp=sharing
![](https://i.imgur.com/44DEOwu.png)

<br>

## 1. 프로그램의 역할 (Role)

이 모듈은 삽입된 이미지에 대해 **필터 적용 + 업스케일링**을 수행하는 이미지 후처리 도구입니다.
사용자가 업로드(또는 URL/드래그)한 이미지를 기반으로 해상도를 AI 기술(Waifu2x)로 복원하고, 다양한 필터와 크기 조절을 통해 2차 가공을 수행할 수 있도록 돕습니다.

* **개발 요청 위치:**
  PressAI > Image Repository > **Filter & Upscale** (New)

* **핵심 역할:**

  * 저해상도 이미지의 품질 저하 없는 확대(Upscaling)
  * 다양한 필터 및 리사이즈를 통한 후처리
  * 다수 이미지의 **일괄 변환(Batch Processing)**

* **이미지 소스 다양화**

  * 로컬 파일 업로드
  * HTTP/HTTPS 이미지 URL 직접 입력
  * 웹 브라우저에서 이미지를 **드래그 & 드롭** 시 URL 인식 후 자동 처리

* **포맷 확장**

  * PNG, JPG/JPEG, WEBP, JFIF, BMP, GIF, TIF/TIFF, AVIF, HEIC, **SVG까지 지원**

<br>


## 2. 주요 기능 (Key Features)

이 프로그램은 크게 **입출력(IO), 처리(Processing), UI/UX** 세 가지 영역으로 나뉩니다.

### 2-1. 이미지 처리 (Image Processing)

#### AI 업스케일링 (Waifu2x / NCNN / Vulkan)

* `waifu2x-ncnn-vulkan.exe` 바이너리를 서브프로세스로 실행하는 래퍼 함수 `upscale_with_ncnn` 사용
* 노이즈 제거(Denoise) 강도:

  * **부드럽게(0) / 보통(1) / 강하게(2)**
* 업스케일 배율:

  * **1.5배 / 2배 / 3배 / 4배**
* 내부적으로는 2배 또는 4배 업스케일 후, Pillow 리사이즈로 최종 목표 배율 맞춤

#### 기본 필터링 (Pillow 기반)

* 지원 필터:

  * **없음, 흑백, 세피아, 밝게, 고대비, 채도, 블러**
* 필터 강도:

  * 0 ~ 100% 슬라이더 → 내부적으로 0.0 ~ 1.0으로 변환 (`intensity`)
* 구현 방식:

  * `ImageEnhance` / `ImageFilter` 를 활용해 픽셀 단위 조정
  * 알파 채널(RGBA)은 분리 후 필터를 RGB에만 적용하고, 다시 합성

#### 리사이징 (Resize)

* 기준:

  * 가로 크기 기준 비율 유지 리사이즈
* 옵션:

  * **원본, 400px, 600px, 800px, 960px, 1280px**
* 알고리즘:

  * `Image.Resampling.LANCZOS` (고품질 리사이즈)

#### 포맷 변환 (Format Conversion)

* 출력 포맷 옵션:

  * **원본 유지, JPEG, JPG, PNG, WebP, JFIF**
* 원본 유지:

  * 일반 이미지: 원본 포맷 유지 시도
  * SVG: 실제 렌더링 결과를 **PNG**로 저장
* 투명도 처리:

  * JPEG/JFIF/BMP 등 투명도 미지원 포맷은 **흰 배경에 합성 후 저장**

#### SVG 지원

* `QSvgRenderer`를 이용해 SVG를 오프스크린 렌더링
* `QImage → PIL.Image` 로 변환 후, 나머지 파이프라인(리사이즈/업스케일/필터)을 동일하게 적용

<br>


### 2-2. 워크플로우 (Workflow)

프로그램의 흐름은 **이미지 로드 → 옵션 조절(미리보기) → 실행(저장)** 으로 구성됩니다.

<br>


#### 1) 이미지 불러오기 (Import)

사용자는 세 가지 방식으로 이미지를 가져올 수 있습니다.

| **경로**            | **사용자 행동 (User Action)**                      | **코드 흐름 (Code Execution)**                                              |
| ----------------- | --------------------------------------------- | ----------------------------------------------------------------------- |
| **A. 파일 열기 버튼**   | “이미지 열기” 버튼 클릭                                | `open_image()` → `QFileDialog` → 선택 경로로 `load_image(path)` 호출           |
| **B. 로컬 드래그&드롭**  | 이미지 파일(다중 가능)을 프로그램 창으로 드래그 & 드롭              | `dragEnterEvent()`에서 확장자 검사 → `dropEvent()`에서 경로 리스트 생성 및 분기            |
| **C. 이미지 주소 입력**  | 좌측 패널의 “이미지 주소” 입력창에 URL 입력 후 엔터 또는 “불러오기” 클릭 | `on_url_load_clicked()` → `load_image_from_url(url)`                    |
| **D. 웹 이미지를 드래그** | 브라우저에서 이미지를 직접 프로그램 창으로 드래그 & 드롭              | MIME의 URL/text에서 이미지 URL 추출 → `url_input` 자동 채움 → `load_image_from_url` |

**URL 처리 특징**

* `http://`, `https://` 로 시작하는 URL만 허용
* `ssl + certifi`를 이용해 CA 번들을 명시, HTTPS 인증서 에러 최소화
* SVG URL은 임시 파일로 저장 후 기존 `load_image()` 재사용
* URL에서 내려받은 이미지는 `current_image_path`에 **URL 문자열**로 저장
  → 이후 파일명 생성 시, 쿼리 스트링 제거/정규화

<br>

#### 2) 옵션 조절 및 실시간 미리보기 (Previewing)

사용자가 설정을 변경할 때마다 `update_preview()`가 실행되어 빠른 피드백을 제공합니다.

| **단계**      | **사용자 행동**             | **코드 흐름**                                                             |
| ----------- | ---------------------- | --------------------------------------------------------------------- |
| **사이즈 변경**  | 400px ~ 1280px 버튼 클릭   | `on_size_changed()` → `state.size_width` 갱신 → `update_preview()`      |
| **업스케일 설정** | 1.5배 / 2배 / 3배 / 4배 선택 | `on_upscale_changed()` → `state.upscale` 갱신 → `update_preview()`      |
| **업스케일 강도** | “부드럽게/보통/강하게” 선택       | `on_upscale_strength_changed()` → 강도 저장 (실제 처리에서만 사용)                 |
| **필터/강도**   | 필터 버튼 선택 및 슬라이더 조절     | `on_filter_changed()` / `on_intensity_changed()` → `update_preview()` |
| **미리보기 렌더** | (내부)                   | Pillow 리사이즈 + 필터만 적용, QImage/QPixmap으로 변환 후 라벨에 표시                    |

> ⚠️ **주의:** 미리보기에서는 속도 때문에 **NCNN 업스케일을 사용하지 않습니다.**
> 실제 Waifu2x 업스케일 결과는 저장 시에만 적용됩니다.

<br>

#### 3) 단일 이미지 저장 (Single Process & Save)

사용자가 설정을 확인한 후, **현재 한 장의 이미지를 확정 처리 + 저장**하는 단계입니다.

| **단계**   | **사용자 행동**              | **코드 흐름**                                                                        |
| -------- | ----------------------- | -------------------------------------------------------------------------------- |
| 폴더 지정    | (최초 1회) “다운로드 폴더 지정” 클릭 | `choose_download_folder()` → 성공 시 `download_dir`에 저장                             |
| 다운로드 실행  | “다운로드 (단일)” 버튼 클릭       | `save_image()` 진입                                                                |
| 처리 파이프라인 | -                       | `build_processed_image(self.state.original)` 호출 (Resize → NCNN Upscale → Filter) |
| 저장 경로 결정 | -                       | `_unique_save_path(download_dir, base_name, ext)` 로 중복/문자 문제 없는 파일명 생성           |
| 파일 저장    | -                       | Pillow `img.save(target_path, format=save_format)`                               |
| 결과 안내    | -                       | `QMessageBox.information()` 로 최종 경로 안내                                           |

**파일명 정리 로직**

* URL 기반 경로의 경우 `os.path.basename(url)` 이 `call?cmd=VIEW&id=...` 형태가 될 수 있음
* `_unique_save_path` 내부에서:

  * `?` 이후 쿼리 스트링 및 `#` fragment 제거
  * `\ / : * ? " < > |` 등 Windows에서 불가능한 문자를 `_`로 치환
  * 완전히 비어 있으면 `output` 으로 대체
    → 예: `call?cmd=VIEW&id=...` → `call.png` 로 안전한 파일명 보장

<br>

#### 4) 일괄 처리 (Batch Processing)

여러 장을 **한 번에 같은 옵션으로 처리**하는 자동화 단계입니다.

| **단계**  | **사용자 행동**                 | **코드 흐름**                                                          |
| ------- | -------------------------- | ------------------------------------------------------------------ |
| 트리거     | 여러 파일을 창에 드롭               | `dropEvent()` 에서 파일 개수 > 1 → `batch_process(paths)` 호출             |
| 다운로드 폴더 | (필요 시) 자동으로 폴더 선택 다이얼로그 호출 | `choose_download_folder()`                                         |
| 루프 처리   | -                          | `for path in paths:` 루프 돌며 각 이미지에 대해 `build_processed_image()` 호출  |
| SVG 처리  | -                          | `.svg` 확장자는 `load_svg_to_pil()` 사용, 나머지는 `Image.open()`            |
| 저장 파일명  | -                          | 원본 파일명을 기준으로 `{name}_edit.ext` 형태로 저장, `_unique_save_path` 로 중복 방지 |
| 진행 표시   | -                          | `QProgressBar` 를 0~총 개수로 설정 후, 각 루프마다 `setValue()` 및 포맷 문자열 업데이트   |
| 완료 리포트  | -                          | 성공/실패 개수와 저장 경로를 `QMessageBox`로 알림                                 |

<br>

### 2-3. UI/UX 구성

* **좌측 패널**

  * 파일 열기 / 단일 다운로드 버튼
  * 다운로드 폴더 지정 & 바로 열기 버튼
  * 이미지 크기 / 업스케일 배율 / 업스케일 강도 / 필터 / 필터 강도 / 출력 포맷 옵션 그룹
  * **프리셋 버튼 5개**

    * 좌클릭: 프리셋 불러오기
    * 우클릭: 현재 설정 저장 + 이름 변경
    * `presets.json` 파일로 실행 파일 기준 디렉토리에 저장/로드
  * **이미지 주소 입력란 + “불러오기” 버튼**
  * 진행 상태 표시용 ProgressBar

* **우측 패널**

  * 미리보기 이미지 영역 (`QLabel`, `QPixmap` 기반)
  * 하단 라이선스 표시:
    “This software uses waifu2x-ncnn-vulkan (MIT License)”

<br>

## 3. NCNN 프로그램 내용 (Waifu2x Integration)

이 모듈의 핵심인 고해상도 복원 기능은 Python 내부 라이브러리가 아니라, 외부 **C++ 바이너리(NCNN / Vulkan)** 를 호출하여 수행됩니다.

### 기술 스택

* 실행 파일: `waifu2x-ncnn-vulkan.exe`
* 프레임워크: NCNN + Vulkan
* 모델 폴더: `models-cunet` (실행 파일 디렉토리 하위)

### 동작 방식 (Subprocess Interaction)

1. Python에서 현재 이미지(PIL)를 임시 폴더에 `in.png` 로 저장
2. `subprocess.run()` 으로 `waifu2x-ncnn-vulkan.exe` 실행:

   ```bash
   waifu2x-ncnn-vulkan.exe -i in.png -o mid.png -n {noise_level} -s {scale} -f png
   ```
3. 성공 시 생성된 `mid.png` 를 다시 열어 `up_img` 로 가져옴
4. 원본 크기 × 사용자가 지정한 배율로 최종 `resize` 후 반환

### 예외 및 Fallback

* 실행 파일 경로 또는 모델 폴더 부재, Vulkan 호환 문제, 실행 실패 시:

  * 콘솔에 `[NCNN] 실행 실패, Pillow fallback: ...` 로그 출력
  * `Image.resize(..., LANCZOS)` 로 대체 업스케일 수행 (AI 업스케일 대신 일반 확대)

### 윈도우 환경 처리

* `CREATE_NO_WINDOW`, `STARTF_USESHOWWINDOW` 를 사용해
  waifu2x 실행 시 별도 콘솔 창이 뜨지 않도록 처리

<br>


## 4. 코드별 핵심 기능 분석 (Core Functions)

PressAI로 포팅 시 특히 참고해야 할 주요 함수들입니다.

### A. 처리 파이프라인 마스터 (`build_processed_image`)

```python
def build_processed_image(self, base_img: Image.Image) -> Image.Image:
    img = base_img

    # 1. 리사이즈
    if self.state.size_width:
        ...

    # 2. AI 업스케일 (배율 > 1.0일 경우)
    if self.state.upscale > 1.0:
        img = self.upscale_with_ncnn(img, self.state.upscale, self.state.upscale_strength)

    # 3. 필터 적용
    img = self.apply_filter(img, self.state.filter_name, self.state.intensity)
    return img
```

**역할**

* 단일/배치 처리에서 **공통으로 호출되는 최상위 처리 파이프라인**
* PressAI 환경에 이식 시, 이 함수만 잘 감싸면 외부에서 “한 장 변환” API로 재사용 가능

<br>


### B. NCNN 실행 래퍼 (`upscale_with_ncnn`)

```python
def upscale_with_ncnn(self, img: Image.Image, scale: float, strength: int) -> Image.Image:
    # 1. waifu2x 실행 가능 여부 확인 (경로, 모델 폴더)
    # 2. 임시 디렉토리 생성, in.png 저장
    # 3. subprocess로 waifu2x 실행
    # 4. mid.png 읽어와 PIL 이미지로 로드
    # 5. 원하는 최종 배율로 보정 리사이즈
    # 6. 실패 시 Pillow 리사이즈로 Fallback
```

**역할**

* Python ↔ 외부 바이너리 사이의 인터페이스
* 실패 시에도 항상 유효한 `Image` 를 반환하도록 설계

<br>


### C. 필터 적용 로직 (`apply_filter`)

```python
def apply_filter(self, img: Image.Image, name: str, intensity: float) -> Image.Image:
    # name, intensity에 따라 Brightness/Contrast/Color/Blur/흑백/세피아 적용
    # RGBA의 알파 채널을 고려해 RGB만 조정 후 다시 합성
```

**역할**

* LUT 수준의 색 보정 및 스타일 필터 역할
* 향후 PressAI 쪽에서 필터 리스트를 확장하거나, 프리셋화하여 재사용 가능

<br>


### D. 배치 처리 및 저장 (`batch_process`)

```python
def batch_process(self, paths):
    # 1. 다운로드 폴더 지정 확인
    # 2. 각 path에 대해 SVG/일반 이미지 분기
    # 3. build_processed_image() 호출
    # 4. _unique_save_path() + "{name}_edit" 이름으로 저장
    # 5. 프로그레스바 업데이트 및 성공/실패 집계
```

**역할**

* UI 기반 자동화 엔진
* 추후 CLI 또는 API에서 프리셋 기반 배치 처리 기능으로 이식 가능

<br>


### E. URL/드래그 통합 로딩 (`load_image_from_url`, Drag & Drop)

```python
def load_image_from_url(self, url: str):
    # 1. URL 정규화(// → https://)
    # 2. ssl + certifi 기반 HTTPS 요청
    # 3. SVG / 일반 이미지 분기
    # 4. self.state.original 에 이미지 설정, 미리보기 갱신
```

```python
def dragEnterEvent(self, event):
    # 파일 URL / HTTP 이미지 URL / 텍스트 내 URL까지 검사

def dropEvent(self, event):
    # 로컬 이미지: 단일/배치 분기
    # HTTP 이미지: URL 자동 채움 + load_image_from_url()
```

**역할**

* PressAI 웹/데스크톱 통합 시, **이미지 소스를 유연하게 가져오는 입구**로 참고 가능

<br>


## 5. 참고 및 향후 개선 포인트

### 비동기 처리

현재 `build_processed_image`, `batch_process`, `upscale_with_ncnn` 이 모두 **메인 스레드에서 실행**됩니다.

* 고해상도 이미지 + Waifu2x 사용 시 UI 프리징이 발생할 수 있음
* PressAI에 통합 시에는 다음과 같은 리팩토링을 고려하는 것이 좋습니다.

  * 데스크톱:

    * `QThread` / `QRunnable` + `QThreadPool` 기반 비동기 작업 처리
  * 서버/백엔드:

    * Celery, RQ, 비동기 워커 등으로 오프로드

### 프리셋 공유

* 현재는 로컬 `presets.json`을 사용
* PressAI UI와 연동 시 **계정/프로젝트 단위의 프리셋 관리 API**로 확장 가능

### 로그/에러 수집

* 현재는 `print` 및 `QMessageBox` 중심
* 실제 서비스 통합 시:

  * 중앙 로그 시스템(예: Sentry, ELK 등)으로 통합할 수 있도록 인터페이스 분리 권장

<br>

