# ui_components.py - 재사용 가능한 커스텀 UI 컴포넌트
# ===================================================================================
# 파일명     : ui_components.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : PyQt5 기본 위젯을 확장한 특수 목적 컴포넌트 및
#              다중 선택 콤보박스, 정수 정렬 테이블 아이템 등 커스텀 UI 요소
# ===================================================================================
#
# 【주요 기능】
# - PyQt5 기본 위젯을 확장한 특수 목적 컴포넌트
# - 다중 선택 콤보박스, 정수 정렬 테이블 아이템 등
# - 여행 및 날씨 탭에서 공통 사용되는 UI 요소
#
# 【핵심 컴포넌트】
#
# 1. IntItem (QTableWidgetItem 확장)
#    - 정수 값을 올바르게 정렬하는 테이블 아이템
#    - 문자열 "1,000" → 숫자 1000으로 비교
#    - 리뷰 수 등 숫자 데이터 정렬에 사용
#
# 2. CheckableComboBox
#    - 다중 체크박스 선택이 가능한 콤보박스
#    - 선택된 항목들을 "항목1, 항목2" 또는 "항목1 외 2개" 형태로 표시
#    - 시/군/구, 읍/면/동 선택에 사용
#
# 3. SelectAllCheckableComboBox
#    - CheckableComboBox + 상단 "전체 선택/해제" 헤더
#    - 헤더 클릭으로 모든 항목 토글 가능
#    - 카테고리, 리뷰 카테고리 선택에 사용
#
# 【기능 세부사항】
# - 동적 텍스트 업데이트: 선택 상태 변경 시 즉시 표시 텍스트 갱신
# - 팝업 크기 조정: 항목 텍스트 길이에 따라 드롭다운 폭 자동 조정
# - 상태 관리: checked_items(), set_checked() 등 편의 메서드 제공
#
# 【테이블 설정 함수】
# - setup_place_table(): 장소 검색 결과 테이블 초기 설정
#   * 컬럼 구성, 크기 조정, 정렬 활성화
#   * 가로 스크롤, 행 높이 자동 조정
#   * 편집 금지, 워드랩 활성화
#
# 【사용처】
# - travel_ui.py: 필터 콤보박스들
# - travel_tab.py: 테이블 설정 및 정수 정렬
# - weather_tab.py: 지역 선택 콤보박스 (필요시)
# ===================================================================================

from PyQt5.QtWidgets import (QComboBox, QCheckBox, QTableWidget, QTableWidgetItem, 
                             QWidget, QVBoxLayout, QHBoxLayout, QListView, QHeaderView, QAbstractItemView)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QStandardItemModel, QStandardItem

class IntItem(QTableWidgetItem):
    def __init__(self, value: int):
        super().__init__(str(value))
        self._v = int(value)
    def __lt__(self, other):
        try:
            ov = other._v if isinstance(other, IntItem) else int(str(other.text()).replace(',', '') or 0)
        except Exception:
            return super().__lt__(other)
        return self._v < ov

class CheckableComboBox(QComboBox):
    """체크 가능한 QComboBox (헤더/전체선택 없음: 시/군/구, 읍/면/동용)"""
    def __init__(self, placeholder="전체", parent=None):
        super().__init__(parent)
        self.setModel(QStandardItemModel(self))
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self._placeholder = placeholder
        self._updating = False

        self.setView(QListView())
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)

        self.model().itemChanged.connect(self._on_item_changed)
        self._update_text()

    def add_checkable_items(self, items, checked=True):
        self.model().clear()
        state = Qt.Checked if checked else Qt.Unchecked
        for text in items:
            it = QStandardItem(text)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setData(state, Qt.CheckStateRole)
            self.model().appendRow(it)
        self._update_text()

    def clear_items(self):
        self.model().clear()
        self._update_text()

    def checked_items(self):
        out = []
        for i in range(self.model().rowCount()):
            it = self.model().item(i)
            if it and it.checkState() == Qt.Checked:
                out.append(it.text())
        return out

    def set_checked(self, labels):
        self._updating = True
        labels_set = set(labels or [])
        for i in range(self.model().rowCount()):
            it = self.model().item(i)
            if it:
                it.setCheckState(Qt.Checked if it.text() in labels_set else Qt.Unchecked)
        self._updating = False
        self._update_text()

    def check_all(self):
        self._set_all(Qt.Checked)

    def uncheck_all(self):
        self._set_all(Qt.Unchecked)

    def _set_all(self, state):
        self._updating = True
        for i in range(self.model().rowCount()):
            it = self.model().item(i)
            if it:
                it.setCheckState(state)
        self._updating = False
        self._update_text()

    def _on_item_changed(self, _item):
        if not self._updating:
            self._update_text()

    def _update_text(self):
        items = self.checked_items()
        if not items:
            self.lineEdit().setText(self._placeholder)
        elif len(items) <= 3:
            self.lineEdit().setText(", ".join(items))
        else:
            self.lineEdit().setText(f"{items[0]} 외 {len(items)-1}")

    def showPopup(self):
        # 팝업 폭 넉넉히 (유지)
        fm = self.fontMetrics()
        maxw = 0
        for i in range(self.model().rowCount()):
            it = self.model().item(i)
            if it:
                maxw = max(maxw, fm.horizontalAdvance(it.text()))
        padding = 80
        self.view().setMinimumWidth(max(self.width(), maxw + padding))
        super().showPopup()


class SelectAllCheckableComboBox(CheckableComboBox):
    """위에 '전체 선택/해제' 헤더가 있는 체크 콤보 (특정 콤보에만 사용)"""
    def __init__(self, placeholder="전체", parent=None):
        super().__init__(placeholder, parent)

        # 헤더 추가 (맨 위 0행)
        self._add_select_all_header()
        self.view().pressed.connect(self._on_view_pressed)

    def _add_select_all_header(self):
        if self.model().rowCount() == 0 or self.model().item(0).text() != "전체 선택/해제":
            head = QStandardItem("전체 선택/해제")
            head.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # 체크박스 없음
            self.model().insertRow(0, head)

    def _on_view_pressed(self, index):
        if index.row() != 0:
            return

        # 하나라도 미체크면 모두 체크, 아니면 모두 해제 (0행은 건너뜀)
        any_unchecked = any(
            (self.model().item(i).flags() & Qt.ItemIsUserCheckable) and
            self.model().item(i).checkState() != Qt.Checked
            for i in range(1, self.model().rowCount())
        )
        state = Qt.Checked if any_unchecked else Qt.Unchecked

        self._updating = True
        for i in range(1, self.model().rowCount()):
            it = self.model().item(i)
            if it and (it.flags() & Qt.ItemIsUserCheckable):
                it.setCheckState(state)
        self._updating = False
        self._update_text()

        # 🔑 헤더 클릭 시 팝업 닫히지 않도록 즉시 다시 열기
        QTimer.singleShot(0, self.showPopup)

    # 헤더가 있으니 아래 메서드들은 0행 건너뛰도록 살짝 오버라이드
    def add_checkable_items(self, items, checked=True):
        self._add_select_all_header()
        state = Qt.Checked if checked else Qt.Unchecked
        for text in items:
            it = QStandardItem(text)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setData(state, Qt.CheckStateRole)
            self.model().appendRow(it)
        self._update_text()

    def clear_items(self):
        self.model().clear()
        self._add_select_all_header()
        self._update_text()

    def checked_items(self):
        out = []
        for i in range(1, self.model().rowCount()):
            it = self.model().item(i)
            if it and it.checkState() == Qt.Checked:
                out.append(it.text())
        return out

    def _set_all(self, state):
        self._updating = True
        for i in range(1, self.model().rowCount()):
            it = self.model().item(i)
            if it and (it.flags() & Qt.ItemIsUserCheckable):
                it.setCheckState(state)
        self._updating = False
        self._update_text()


def setup_place_table(table_widget):
    """장소 테이블 초기 설정"""
    table_widget.setColumnCount(10)
    table_widget.setHorizontalHeaderLabels(["", "장소명", "카테고리", "주소", "키워드", "이 리뷰수", "리뷰 요약", "소개", "sel", "id"])
    table_widget.setColumnHidden(8, True)
    table_widget.setColumnHidden(9, True) # id 컬럼 숨기기
    table_widget.setSortingEnabled(True)

    header = table_widget.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
    # 1~4: 인터랙티브(수동폭 조절)
    for col in (1, 2, 3, 4):
        header.setSectionResizeMode(col, QHeaderView.Interactive)
    # 5: 이 리뷰수는 내용 크기에 맞춤
    header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
    # 6,7: 리뷰요약/소개도 인터랙티브로 (가로 스크롤 사용)
    header.setSectionResizeMode(6, QHeaderView.Interactive)
    header.setSectionResizeMode(7, QHeaderView.Interactive)

    # ✅ 마지막 열 늘려 채우기 끄기 + 가로 스크롤 켜기
    header.setStretchLastSection(False)
    table_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    table_widget.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

    table_widget.setColumnWidth(1, 120)  # 장소명
    table_widget.setColumnWidth(2, 120)  # 카테고리
    table_widget.setColumnWidth(3, 240)  # 주소
    table_widget.setColumnWidth(4, 160)  # 키워드
    table_widget.setColumnWidth(6, 280)  # 리뷰 요약
    table_widget.setColumnWidth(7, 320)  # 소개

    table_widget.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table_widget.setWordWrap(True)