# PressAI Filter & Upscale 모듈

PressAI의 **Image Repository** 내에 새롭게 통합 요청할 `filter & upscale` 기능에 대한 기술 및 가이드입니다. 본 문서는 Python(PyQt6 + Pillow) 코드를 기반으로 작성되었습니다.

---

## 1. 프로그램의 역할 (Role)

이 모듈은 삽입 된 이미지의 필터 적용 및 업스케일링 이미지 후처리 도구 입니다. 사용자가 업로드한 이미지의 해상도를 AI 기술(Waifu2x)을 통해 복원하고, 다양한 필터와 크기 조절을 통해 2차 가공을 수행할 수 있도록 돕습니다.

- **개발 요청 위치:** PressAI > Image Repository > **Filter & Upscale**(New)
    
- **핵심 역할:** 저해상도 이미지의 품질 저하 없는 확대(Upscaling) 및 대량 이미지의 일괄 변환(Batch Processing) 

---

## 2. 주요 기능 (Key Features)

이 프로그램은 크게 **입출력(IO), 처리(Processing), UI/UX** 세 가지 영역으로 나뉩니다.

- **이미지 처리 (Image Processing)**
    
    - **AI 업스케일링:** `waifu2x-ncnn-vulkan` 바이너리를 래핑하여 실행. 노이즈 제거(Denoise) 강도 조절 및 1.5배/2배 확대 지원.
        
    - **기본 필터링:** Pillow 라이브러리를 활용한 6종 필터(흑백, 세피아, 밝게, 고대비, 채도, 블러) 및 강도(0~100%) 조절.
        
    - **리사이징:** 가로 픽셀 기준 정해진 규격(400px ~ 1280px)으로 비율 유지 리사이징 (Lanczos 알고리즘).
        
    - **포맷 변환:** JPEG, PNG, WebP, JFIF 등 다양한 포맷으로 내보내기 지원.
        
- **워크플로우 (Workflow)**
    
    - **배치 프로세싱 (Batch Processing):** Drag & Drop을 통해 여러 장의 이미지를 동시에 처리 및 저장.
        
    - **실시간 미리보기:** 필터나 설정 적용 시 결과를 UI에서 즉시 확인 (퍼포먼스를 위해 미리보기 시에는 AI 업스케일 대신 일반 리사이즈 적용).
        
    - **자동 파일명 생성:** 원본 파일 덮어쓰기 방지를 위한 `_edit`, `_1` 등의 접미사 자동 처리.
        
이 프로그램은 크게 **이미지 로드 → 옵션 조절(미리보기) → 실행(저장)**의 흐름을 가집니다. 

#### **1. 이미지 불러오기 (Import)**

사용자가 파일을 프로그램으로 가져오는 진입점입니다. 단일 파일과 다중 파일(일괄 처리)의 분기점이 이곳에서 발생합니다.

| **단계**        | **사용자 행동 (User Action)** | **코드 실행 흐름 (Code Execution)**                                                                                                                                                        |
| ------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **A. 열기 버튼**  | '이미지 열기' 버튼 클릭           | 1. `btn_open.clicked` 시그널 발생<br><br>  <br><br>2. **`open_image()`** 호출<br><br>  <br><br>3. `QFileDialog`로 파일 선택<br><br>  <br><br>4. **`load_image(path)`** 실행 (이미지 메모리 적재 & 미리보기 갱신) |
| **B. 드래그&드롭** | 윈도우로 파일(들)을 드래그          | 1. **`dragEnterEvent()`**: 확장자 검사 (`is_image_file`) 후 허용 여부 결정<br><br>  <br><br>2. **`dropEvent()`**: 드롭된 파일 경로 리스트(`paths`) 확보                                                      |
| **C. 분기 처리**  | (드롭 후 자동 실행)             | • **파일이 1개일 때:** `load_image(path)` → **편집 모드** 진입<br><br>  <br><br>• **파일이 여러 개일 때:** `batch_process(paths)` → **즉시 일괄 변환** 시작                                                      |

---

#### **2. 옵션 조절 및 실시간 미리보기 (Previewing)**

사용자가 설정을 변경할 때마다 즉각적인 피드백을 제공하는 단계입니다. **퍼포먼스 최적화 로직**이 포함되어 있어 개발팀의 주의가 필요합니다.

| **단계**      | **사용자 행동 (User Action)** | **코드 실행 흐름 (Code Execution)**                                                                                                                                                                                                                                       |
| ----------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **사이즈 변경**  | 400px ~ 1280px 버튼 클릭     | `on_size_changed()` → `state.size_width` 갱신 → `update_preview()`                                                                                                                                                                                                    |
| **업스케일 설정** | 1.5배 / 2배, 강도 조절         | `on_upscale_changed()` / `on_upscale_strength_changed()` → `update_preview()`                                                                                                                                                                                       |
| **필터/강도**   | 필터 선택 or 슬라이더 조절         | `on_filter_changed()` / `on_intensity_changed()` → `update_preview()`                                                                                                                                                                                               |
| **화면 갱신**   | (내부 로직)                  | **`update_preview()`** 핵심 로직:<br><br>  <br><br>1. 원본 이미지(`state.original`) 복사<br><br>  <br><br>2. **중요:** 미리보기 속도를 위해 **NCNN(AI) 대신 Pillow(일반) 리사이즈 사용**<br><br>  <br><br>3. `apply_filter()` 적용<br><br>  <br><br>4. `pil_to_qimage()` 변환 후 라벨(`preview_label`)에 표시 |

> **개발팀 참고:** 사용자는 미리보기에서 "AI 업스케일링"의 품질을 확인할 수 없습니다. 미리보기는 속도를 위해 일반 확대만 보여주며, 실제 AI 적용은 '다운로드' 시에만 이루어집니다.

---

#### **3. 단일 이미지 저장 (Single Process & Save)**

사용자가 눈으로 확인한 설정을 바탕으로 실제 고화질 변환을 수행하는 단계입니다.

|**단계**|**사용자 행동 (User Action)**|**코드 실행 흐름 (Code Execution)**|
|---|---|---|
|**폴더 지정**|(저장 전) 폴더 미지정 시|`choose_download_folder()` → `QFileDialog`로 경로 획득 및 `self.download_dir` 저장|
|**다운로드**|'다운로드 (단일)' 버튼 클릭|1. **`save_image()`** 호출<br><br>  <br><br>2. `progress_busy()`: UI 프리징 방지용 '처리 중' 표시<br><br>  <br><br>3. **`build_processed_image()`**: **실제 변환 엔진 가동** (아래 설명)<br><br>  <br><br>4. `_unique_save_path()`: 파일명 중복 체크 (예: `image_1.png`)<br><br>  <br><br>5. `img.save()`: 최종 파일 쓰기<br><br>  <br><br>6. `QMessageBox`: 완료 알림|

---

#### **4. 일괄 처리 (Batch Processing)**

UI 조작 없이, 드래그 앤 드롭만으로 여러 장을 설정된 옵션대로 변환하는 자동화 단계입니다.

|**단계**|**사용자 행동 (User Action)**|**코드 실행 흐름 (Code Execution)**|
|---|---|---|
|**실행 트리거**|여러 파일을 드롭함|`dropEvent()`에서 파일 개수 > 1 확인 후 **`batch_process(paths)`** 진입|
|**루프 실행**|(자동 진행)|1. `progress_bar` 범위 설정 (0 ~ 전체 개수)<br><br>  <br><br>2. `for path in paths`: 루프 시작<br><br>  <br><br>3. 각 이미지 로드 (`Image.open`)<br><br>  <br><br>4. **`build_processed_image()`**: 변환 엔진 호출<br><br>  <br><br>5. 결과 저장 및 프로그레스바 `setValue()` 업데이트<br><br>  <br><br>6. 완료 후 결과 리포트(성공/실패 개수) 출력|

---

#### **5. 핵심 변환 엔진 (The Core Engine)**

`save_image`와 `batch_process`가 공통으로 호출하는 **실제 이미지 처리 함수**입니다.

- **함수명:** `build_processed_image(base_img)`
    
- **실행 순서:**
    
    1. **Resize:** 사용자가 지정한 가로 폭(`size_width`)이 있다면 먼저 리사이즈 (Pillow Lanczos).
        
    2. **Upscale (Heavy Task):** 업스케일 배율이 1.0보다 크면 **`upscale_with_ncnn()`** 호출.
        
        - _Subprocess:_ 외부 `waifu2x-ncnn-vulkan.exe`를 실행하여 GPU/CPU 연산 수행.
            
    3. **Filter:** **`apply_filter()`** 호출하여 색상/필터 효과 적용.
        
    4. **Return:** 최종 가공된 `Image` 객체 반환.
        

---

## 3. NCNN 프로그램 내용 (Waifu2x Integration)

이 모듈의 핵심인 고해상도 복원 기능은 Python 내부 라이브러리가 아닌, 외부 **C++ 바이너리(NCNN)**를 호출하여 수행됩니다.

- **기술 스택:** `waifu2x-ncnn-vulkan` (Tencent의 NCNN 프레임워크 기반, Vulkan API 사용)
    
- **동작 방식 (Subprocess Interaction):**
    
    1. Python에서 현재 메모리에 있는 이미지를 임시 폴더(`tempfile`)에 `in.png`로 저장.
        
    2. `subprocess` 모듈을 통해 `waifu2x-ncnn-vulkan.exe`를 실행하며 인자값(입력 경로, 출력 경로, 노이즈 레벨, 스케일) 전달.
        
    3. 외부 프로그램이 GPU(또는 CPU)를 사용해 연산 후 `out.png` 생성.
        
    4. Python이 `out.png`를 다시 로드하여 메모리에 적재하고 임시 파일 삭제.
        
- **통합 시 주의사항:**
    
    - **종속성:** `waifu2x-ncnn-vulkan.exe` 파일뿐만 아니라, `models-cunet` 등의 **모델 폴더**가 실행 파일과 같은 디렉토리에 반드시 존재해야 함.
        
    - **예외 처리:** Vulkan 호환 CPU/GPU가 없거나 실행 파일 경로가 잘못된 경우, 자동으로 Pillow의 `Lanczos` 리사이즈(일반 확대)로 대체되는 Fallback 로직이 구현되어 있음.
        
    - **Windows 호환:** 실행 시 콘솔 창(검은 창)이 뜨지 않도록 `STARTUPINFO` 및 `CREATE_NO_WINDOW` 플래그 처리가 되어 있음.
        

---

## 4. 코드별 핵심 기능 분석 (Core Functions)

개발팀이 PressAI로 포팅 시 참고해야 할 주요 함수들의 로직입니다.

#### A. 처리 파이프라인 마스터 (`build_processed_image`)

모든 이미지 처리는 이 함수를 통해 순차적으로 일어납니다.

``` python
def build_processed_image(self, base_img: Image.Image) -> Image.Image:
    # 1. 리사이즈 (사용자가 지정한 가로 크기가 있을 경우)
    # 2. AI 업스케일링 (ncnn 호출, 배율이 1.0 초과일 때)
    # 3. 필터 적용 (색상, 밝기, 블러 등)
    return img
```

#### B. NCNN 실행 래퍼 (`upscale_with_ncnn`)

외부 프로세스를 제어하는 가장 중요한 부분입니다.

``` python
def upscale_with_ncnn(self, img: Image.Image, scale: float, strength: int) -> Image.Image:
    # 1. 모델/실행파일 경로 검증 (없으면 일반 리사이즈 리턴)
    # 2. 임시 디렉토리 생성 (tempfile)
    # 3. subprocess.run()으로 CLI 명령어 실행
    #    cmd 예시: waifu2x-ncnn-vulkan.exe -i in.png -o out.png -n 2 -s 2
    # 4. 생성된 이미지 로드 및 리턴
```

#### C. 필터 적용 로직 (`apply_filter`)

Pillow(`PIL`)의 기능을 활용하여 픽셀 데이터를 조작합니다.

``` python
def apply_filter(self, img: Image.Image, name: str, intensity: float) -> Image.Image:
    # ImageEnhance 모듈(Brightness, Contrast, Color) 활용
    # ImageFilter 모듈(GaussianBlur) 활용
    # Image.blend()를 사용하여 원본과 필터 적용본 사이의 강도(intensity) 조절
```

#### D. 배치 처리 및 저장 (`batch_process`)

여러 파일을 처리할 때의 루프 및 예외 처리 로직입니다.

``` python
def batch_process(self, paths):
    # 1. 다운로드 경로 확인
    # 2. 파일 목록 순회 (for path in paths)
    # 3. build_processed_image() 호출하여 변환
    # 4. _unique_save_path()를 통해 파일명 중복 방지 (원본_edit.png)
    # 5. 진행률(ProgressBar) 업데이트 및 결과 리포트
```

## 5. 참고

- **비동기 처리:** 현재 `batch_process`나 `upscale`이 메인 스레드에서 동작하여 UI 프리징(멈춤) 현상이 발생할 수 있습니다. `multiprocessing`을 통한 비동기 작업으로 리팩토링이 필요할것 같습니다.