# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-08-23
# 기능 : 신규상장을 API로 불러와서 데이터(캐쉬)로 저장 관리 하는 함수
# ------------------------------------------------------------------
from . import domestic_list
import datetime

class DataManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DataManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        # __init__은 매번 호출될 수 있으므로, 초기화는 한 번만 실행되도록 합니다.
        if not hasattr(self, 'initialized'):
            self.new_listings = []
            self.last_updated = None
            self.initialized = True
            self.load_new_listings()

    def load_new_listings(self):
        today = datetime.date.today()
        if self.last_updated == today and self.new_listings:
            return

        try:
            # domestic_list.main_process()가 이제 리스트를 반환합니다.
            loaded_data = domestic_list.main_process()
            if loaded_data:
                self.new_listings = loaded_data
                self.last_updated = today
            else:
                self.new_listings = [] # 실패 시 빈 리스트로 초기화
        except Exception as e:
            self.new_listings = []

    def is_newly_listed(self, keyword_input):
        if not keyword_input:
            return False

        # 종목코드와 종목명을 가지고 신규상장 목록과 비교 함수
        is_numeric_input = keyword_input.isdigit()

        for item in self.new_listings:
            item_title = item.get('title', '')
            item_code = item.get('code', '')

            # 1. 종목코드를 가지고 비교를 해서 신규상장 목록에 있으면 True 값을 반환
            if is_numeric_input and keyword_input == item_code:
                return True
            
            # 2. 종목명을 가지고 비교를 해서 신규상장 목록에 있으면 True 값을 반환
            if not is_numeric_input and keyword_input == item_title:
                return True
                
        return False

# 다른 모듈에서 쉽게 사용할 수 있도록 데이터 관리자 인스턴스를 생성합니다.
# 이 인스턴스를 임포트하여 사용하면 항상 동일한 객체를 참조하게 됩니다.
data_manager = DataManager()
