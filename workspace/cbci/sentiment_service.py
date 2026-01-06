import os
from typing import Tuple

# 가벼운 비용/의존성으로 동작하도록 설계
# 1) 우선 transformers 파이프라인 시도 (있으면 사용)
# 2) 없거나 모델 로드 실패 시 키워드 기반 간단 폴백

class SentimentService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._use_transformers = False
        self._threshold = float(os.getenv("SENTIMENT_THRESHOLD", "0.6"))
        self._neutral_floor = float(os.getenv("SENTIMENT_NEUTRAL_FLOOR", "0.5"))
        # 개선 파라미터: 중립 판정 대역폭/키워드 가중치/최소 신뢰도
        self._neutral_margin = float(os.getenv("SENTIMENT_NEUTRAL_MARGIN", "0.2"))  # |evidence|<margin → neutral
        self._kw_weight = float(os.getenv("SENTIMENT_KEYWORD_WEIGHT", "0.12"))      # 키워드 차이의 가중치
        self._min_conf = float(os.getenv("SENTIMENT_MIN_CONF", "0.55"))             # 최소 신뢰도 하한
        self._model_name = os.getenv("SENTIMENT_MODEL_NAME", "")  # 비워두면 폴백

        # 긍/부정 키워드 가중치 사전 (3단계 계층화)
        # Tier 3 (Critical): 2.0 / Tier 2 (Strong): 1.5 / Tier 1 (Standard): 1.0
        self._pos_weights = {
            # Critical (2.0)
            "신년사": 2.0, "팀스피릿": 2.0, "신기록": 2.0, "사상최대": 2.0, "V-자": 2.0,
            # Strong (1.5)
            "호재": 1.5, "흑자": 1.5, "승인": 1.5, "최초": 1.5, "계약": 1.5, "유치": 1.5, 
            "상회": 1.5, "MOU": 1.4, "체결": 1.5, "파트너십": 1.5, "상생": 1.5, "성장동력": 1.5,
            # Standard (1.0)
            "상승": 1.2, "성장": 1.2, "개선": 1.3, "확대": 1.1, "최대": 1.2, "돌파": 1.1, 
            "호조": 1.3, "성과": 1.2, "협력": 1.3, "진출": 1.3, "출시": 1.1, "성공": 1.4, 
            "혁신": 1.3, "비전": 1.4, "도약": 1.4, "가속": 1.2, "팀워크": 1.5, "최고치": 1.5,
        }
        
        self._neg_weights = {
            # Critical (2.0)
            "횡령": 2.0, "배임": 2.0, "파산": 2.0, "마약": 2.0, "사망": 2.0, "압수수색": 2.0, "적자전환": 2.0,
            # Strong (1.5)
            "악재": 1.5, "적자": 1.5, "위기": 1.5, "패소": 1.8, "중단": 1.5, "징계": 1.7, "리콜": 1.7, 
            "수사": 1.8, "혐의": 1.7, "의혹": 1.6, "범죄": 1.8, "구속": 1.9, "적발": 1.6, "비리": 1.8, 
            "불법": 1.8, "과징금": 1.7, "배상": 1.5, "기소": 1.7, "피의자": 1.7,
            # Standard (1.0)
            "하락": 1.2, "감소": 1.0, "부진": 1.3, "논란": 1.4, "사태": 1.3, "지연": 1.2, 
            "경고": 1.3, "제재": 1.4, "부담": 1.1, "악화": 1.3, "고소": 1.4, "피해": 1.2,
            "손실": 1.4, "쇼크": 1.5, "하회": 1.4, "송사": 1.4,
        }

        # transformers가 있으면 로딩 시도
        try:
            if self._model_name:
                print(f"🤖 [SENTIMENT] AI 모델 로딩 시도: {self._model_name}...")
                from transformers import pipeline  # type: ignore
                self._clf = pipeline("text-classification", model=self._model_name, device=-1)
                self._use_transformers = True
                print("✅ [SENTIMENT] AI 모델 로드 완료. 실시간 맥락 분석을 사용합니다.")
            else:
                self._clf = None
                print("ℹ️ [SENTIMENT] 모델명이 지정되지 않았습니다. 키워드 기반 폴백 시스템을 사용합니다.")
        except Exception as e:
            self._clf = None
            self._use_transformers = False
            print(f"⚠️ [SENTIMENT] AI 모델 로딩 실패 ({e}). 키워드 기반 폴백 시스템으로 전환합니다.")
            print("💡 TIP: 'pip install transformers torch'가 설치되어 있는지 확인해 주세요.")

    def _len_factor(self, n: int) -> float:
        """텍스트 길이에 따른 신뢰도 보정(짧으면 보수적으로).
        0.85(아주 짧음) ~ 1.0(충분히 김)
        """
        if n <= 40:
            return 0.85
        if n <= 120:
            return 0.92
        return 1.0

    def predict(self, text: str) -> Tuple[str, float]:
        """
        반환: (label, score)
        label: "positive" | "negative" | "neutral"
        score: 0.0 ~ 1.0 (신뢰도 추정)
        """
        if not text:
            return "neutral", 0.0

        t = (text or "").strip()
        # 간단한 HTML 엔티티 제거 (&quot; 등)
        t = t.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

        # 1) AI 모델 결과 가져오기
        ai_label, ai_score = None, 0.0
        if self._use_transformers and self._clf is not None:
            try:
                res = self._clf(t[:2000], truncation=True)
                if isinstance(res, list) and res:
                    out = res[0]
                    label_raw = str(out.get("label", "")).lower()
                    score = float(out.get("score", 0.0))

                    if any(x in label_raw for x in ["positive", "pos", "label_1"]) or label_raw in {"pos"}:
                        ai_label = "positive"
                    elif any(x in label_raw for x in ["negative", "neg", "label_0"]) or label_raw in {"neg"}:
                        ai_label = "negative"
                    else:
                        ai_label = "neutral"
                    
                    ai_score = score
            except Exception:
                pass

        # 2) 키워드 점수 계산 (가중치 적용)
        p_score = sum(weight for kw, weight in self._pos_weights.items() if kw in t)
        n_score = sum(weight for kw, weight in self._neg_weights.items() if kw in t)
        kw_delta = (p_score - n_score) * self._kw_weight
        
        # evidence: 양수=긍정, 음수=부정
        evidence = 0.0

        # 3) 결정 로직 (AI와 키워드 결합 → 하이브리드 가중치 방식)
        if ai_label:
            # AI를 신호(+/-)로 투영
            sign = 1.0 if ai_label == "positive" else -1.0
            if ai_label == "neutral": sign = 0.0

            # 시너지 및 충돌 로직 (Momentum 증폭)
            # AI와 키워드가 같은 방향이면 확신도 대폭 증가
            if (sign > 0 and kw_delta > 0) or (sign < 0 and kw_delta < 0):
                # 키워드 점수 비례 보정 (최대 0.15 추가)
                boost = min(0.15, abs(kw_delta) * 0.1)
                ai_score = min(1.0, ai_score + boost)
            
            # AI가 긍정인데 상충하는 부정 키워드가 있을 때 (Veto)
            if ai_label == "positive" and n_score >= 1.5:
                # 부정 키워드가 강하면( Tier 2 이상 조합) 긍정 신호를 중립쪽으로 이동
                ai_score *= 0.5
                kw_delta -= 0.3

            evidence = sign * ai_score + kw_delta

            # 신년사/비전 특수 보정
            if "신년사" in t or "비전" in t or "팀스피릿" in t:
                if ai_label == "negative" and ai_score < 0.8:
                    evidence += 0.4  # 강력 보정
                elif ai_label == "neutral":
                    evidence += 0.2

            # 임계값 미만이거나 증거가 희박하면 중립
            if abs(evidence) < self._neutral_margin:
                conf = max(self._neutral_floor, min(0.55, ai_score))
                return "neutral", round(conf * self._len_factor(len(t)), 3)

            # 최종 판정
            label = "positive" if evidence > 0 else "negative"
            # 점수 정규화 (최소 0.55 ~ 최대 1.0)
            final_conf = max(self._min_conf, min(1.0, abs(evidence)))
            return label, round(final_conf * self._len_factor(len(t)), 3)

        # AI 결과가 없는 경우 (폴백)
        if p_score == 0 and n_score == 0:
            return "neutral", 0.5
        
        if abs(kw_delta) < (self._neutral_margin / 2):
            return "neutral", 0.52
            
        label = "positive" if kw_delta > 0 else "negative"
        conf = max(self._min_conf, min(1.0, 0.6 + abs(kw_delta)))
        return label, round(conf * self._len_factor(len(t)), 3)


# 전역 싱글턴
service = SentimentService()
