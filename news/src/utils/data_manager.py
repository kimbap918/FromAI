# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-08-23
# 기능 : 신규상장을 API로 불러와서 데이터(캐쉬)로 저장 관리 하는 함수
# ------------------------------------------------------------------
from . import domestic_list
import datetime

class DataManager:
    """
    신규 상장 기업 데이터를 관리하는 싱글톤(Singleton) 클래스.
    애플리케이션 전체에서 단 하나의 인스턴스만 존재하도록 보장하여
    데이터를 한 번만 로드하고 캐시하여 사용하도록 함.
    """
    _instance = None # 싱글톤 인스턴스를 저장할 클래스 변수

    def __new__(cls, *args, **kwargs):
        """
        클래스의 새 인스턴스를 생성할 때 호출되는 메서드.
        인스턴스가 없으면 생성하고, 있으면 기존 인스턴스를 반환하여 싱글톤 패턴을 구현.
        """
        if not cls._instance:
            cls._instance = super(DataManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        """
        인스턴스 초기화 메서드.
        'initialized' 속성을 확인하여 최초 한 번만 초기화 로직이 실행되도록 함.
        """
        # initialized 속성이 없으면, 아직 초기화되지 않았다는 의미
        if not hasattr(self, 'initialized'):
            self.new_listings = [] # 신규 상장 목록을 저장할 리스트
            self.last_updated = None # 데이터가 마지막으로 업데이트된 날짜
            self.initialized = True # 초기화되었음을 표시
            self.load_new_listings() # 인스턴스 생성 시 신규 상장 데이터를 로드

    def load_new_listings(self):
        """
        KRX에서 신규 상장 기업 목록을 가져와 캐시에 저장.
        데이터는 하루에 한 번만 업데이트하여 불필요한 API 호출을 방지.
        """
        today = datetime.date.today()
        # 마지막 업데이트 날짜가 오늘이고, 목록에 데이터가 이미 있으면 함수를 종료 (캐시 활용)
        if self.last_updated == today and self.new_listings:
            return

        try:
            # domestic_list 모드의 main_process 함수를 호출하여 신규 상장 목록을 가져옴
            loaded_data = domestic_list.main_process()
            if loaded_data:
                self.new_listings = loaded_data # 성공 시 데이터 저장
                self.last_updated = today # 마지막 업데이트 날짜 기록
            else:
                self.new_listings = [] # 실패 시 빈 리스트로 초기화
        except Exception as e:
            # 예외 발생 시, 목록을 비워 오류 상태를 방지
            self.new_listings = []

    def is_newly_listed(self, keyword_input):
        """
        입력된 키워드(종목명 또는 종목코드)가 오늘 신규 상장된 종목인지 확인.
        :param keyword_input: 확인할 종목명(str) 또는 종목코드(str)
        :return: 신규 상장 종목이면 True, 아니면 False
        """
        # 입력값이 없는 경우 False 반환
        if not keyword_input:
            return False

        # 입력값이 숫자로만 이루어져 있는지 확인하여 종목코드인지 종목명인지 판별
        is_numeric_input = keyword_input.isdigit()

        # 캐시된 신규 상장 목록을 순회하며 비교
        for item in self.new_listings:
            item_title = item.get('title', '') # 종목명
            item_code = item.get('code', '') # 종목코드

            # 1. 입력값이 숫자(종목코드)일 경우, 코드와 일치하는지 확인
            if is_numeric_input and keyword_input == item_code:
                return True
            
            # 2. 입력값이 문자(종목명)일 경우, 이름과 일치하는지 확인
            if not is_numeric_input and keyword_input == item_title:
                return True
                
        # 목록에서 일치하는 항목을 찾지 못하면 False 반환
        return False

# DataManager의 싱글톤 인스턴스를 생성.
# 다른 모듈에서 'from .data_manager import data_manager'로 임포트하여
# 항상 동일한 데이터 캐시를 참조할 수 있음.
data_manager = DataManager()