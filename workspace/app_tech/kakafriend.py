import os
import json
import requests
from datetime import datetime, timedelta, timezone

# ================== 설정 영역 ==================

# API 호출 정보
URL = "http://www.realmyprofile.com/web_api/service_aes.php"

HEADERS = {
    'Host': 'www.realmyprofile.com',
    'Content-Type': 'application/json',
    'Connection': 'keep-alive',
    'Accept': '*/*',
    'User-Agent': 'happyquiz/1.0.1 (com.leehr.happyquiz; build:1.0.1.0; iOS 17.0.0) Alamofire/5.9.1',
    'Accept-Language': 'en-US;q=1.0, ko-US;q=0.9',
    'Accept-Encoding': 'br;q=1.0, gzip;q=0.9, deflate;q=0.8',
}

PAYLOAD = {
    "command": "quiz_list_ios",
    "userlevel": "M"
}

# 🔐 카카오 Access Token (friends + talk_message 범위가 포함된 토큰 사용)
KAKAO_ACCESS_TOKEN = ""

# 📤 이 봇이 알림을 보내 줄 대상(친구) uuid 목록
#   → get_friends() 함수로 한 번 찍어보고 원하는 사람 uuid 를 복사해서 여기에 넣어줘
TARGET_FRIEND_UUIDS = [
    # "uoO7g7CAuYmwnK6dpZ....",  # 예시: 홍길동
    # "abCDefghijklmnopq....",  # 예시: 김개발
]

# 상태 저장 파일
STATE_FILE = "quiz_state.json"

# ================== 공통 유틸 함수 ==================


def fetch_quiz_data():
    """
    서버에서 퀴즈 데이터를 조회
    """
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 데이터 조회 시도...")
    try:
        response = requests.post(
            URL,
            headers=HEADERS,
            json=PAYLOAD,
            timeout=10
        )

        response.raise_for_status()
        data = response.json()

        # result 안에 실제 리스트가 "문자열"로 들어있는 케이스 처리
        if "result" in data:
            result_data = data["result"]

            if isinstance(result_data, str):
                try:
                    result_data = json.loads(result_data)
                except json.JSONDecodeError:
                    print("❌ data['result'] 가 JSON 문자열이지만 파싱에 실패했습니다.")
                    print("내용 일부:", result_data[:200])
                    return None

            print("✅ 데이터 조회 성공 및 파싱 완료")
            return result_data

        # 혹시 구조가 다르면 전체 data 반환
        print("⚠ data['result'] 키가 없어 전체 data 반환")
        return data

    except requests.exceptions.RequestException as e:
        print(f"❌ HTTP 요청 중 오류: {e}")
        return None
    except json.JSONDecodeError:
        print("❌ 응답 JSON 파싱 실패 (JSON 형식이 아닐 수 있음)")
        print(f"응답 텍스트: {response.text}")
        return None


def normalize_to_list(raw):
    """
    API 응답(raw)이 dict든 list든 상관없이
    실제 퀴즈 리스트(list[dict])만 뽑아낸다.
    """
    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        # 1) result 키 우선
        if "result" in raw:
            val = raw["result"]
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                for v in val.values():
                    if isinstance(v, list):
                        return v

        # 2) 그 외의 키들 탐색
        for v in raw.values():
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                for vv in v.values():
                    if isinstance(vv, list):
                        return vv

    print(f"⚠ 퀴즈 리스트를 찾지 못했습니다. 타입: {type(raw)}")
    return []


def filter_today_kst_sorted(quiz_list):
    """
    KST 기준 오늘 날짜 데이터만 필터링 후,
    CreateDate 기준 최신순 정렬
    """
    if not isinstance(quiz_list, list):
        print(f"⚠ quiz_list가 리스트가 아닙니다. 타입: {type(quiz_list)}")
        return []

    now_kst = datetime.now(timezone.utc) + timedelta(hours=9)
    today_str = now_kst.strftime("%Y-%m-%d")  # 예) "2025-12-08"

    today_items = []
    for item in quiz_list:
        if not isinstance(item, dict):
            continue
        create_date = str(item.get("CreateDate", ""))
        if create_date.startswith(today_str):
            today_items.append(item)

    today_items_sorted = sorted(
        today_items,
        key=lambda x: x.get("CreateDate", ""),
        reverse=True
    )
    return today_items_sorted


def filter_target_services(quiz_list):
    """
    캐시워크, 토스, 캐시닥, 리브메이트 관련 퀴즈만 필터링
    (title 에 해당 키워드가 포함된 항목만)
    """
    target_keywords = ("캐시워크 퀴즈", "토스 행운퀴즈", "캐시닥 퀴즈", "리브메이트 퀴즈")
    filtered = []

    for item in quiz_list:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", ""))
        if any(kw in title for kw in target_keywords):
            filtered.append(item)

    return filtered


def parse_title_platform_subject(title: str):
    """
    제목에서 퀴즈 매체(platform)와 주체(subject)를 분리
    예)
      '토스 행운퀴즈] 직방  - 문제는 랜덤입니다. ...'
        -> ('토스 행운퀴즈', '직방')
    """
    if not title:
        return "", ""

    platform = ""
    rest = title

    # 1) ']' 기준으로 앞/뒤 나누기
    if ']' in title:
        left, right = title.split(']', 1)
        platform = left.strip()
        rest = right.strip()
    else:
        # ']' 없으면 전체를 플랫폼으로 보고 subject는 빈 값
        return title.strip(), ""

    # 2) 뒤쪽(rest)에서 설명 꼬리 자르기
    suffix_markers = [
        "- 문제는 랜덤입니다.",
        "– 문제는 랜덤입니다.",
    ]
    cut_pos = len(rest)
    for marker in suffix_markers:
        idx = rest.find(marker)
        if idx != -1 and idx < cut_pos:
            cut_pos = idx

    subject = rest[:cut_pos].strip(" -\u00a0")
    return platform, subject


# ================== 상태 관리 & 비교 ==================


def load_last_state(path=STATE_FILE):
    """이전에 본 퀴즈 상태를 파일에서 읽어옴"""
    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_current_state(current_list, path=STATE_FILE):
    """현재 퀴즈 리스트를 상태 파일로 저장"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current_list, f, ensure_ascii=False, indent=2)


def diff_new_items(current_list, last_list):
    """
    이전 리스트와 비교해서 '새로 등장한 퀴즈'만 반환
    기준: (platform, subject, ans)
    """
    last_keys = {
        (item.get("platform"), item.get("subject"), item.get("ans"))
        for item in last_list
        if isinstance(item, dict)
    }

    new_items = []
    for item in current_list:
        if not isinstance(item, dict):
            continue
        key = (item.get("platform"), item.get("subject"), item.get("ans"))
        if key not in last_keys:
            new_items.append(item)

    return new_items


# ================== 카카오톡 관련 함수 ==================


def get_friends(access_token: str):
    """
    (옵션) 카카오톡 친구 목록 가져오기
    - friends / talk_message 권한이 포함된 토큰이어야 함
    - uuid / 닉네임을 콘솔에 출력해서 TARGET_FRIEND_UUIDS 설정에 활용
    """
    url = "https://kapi.kakao.com/v1/api/talk/friends"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    params = {
        "limit": 100
    }

    resp = requests.get(url, headers=headers, params=params, timeout=10)
    try:
        resp.raise_for_status()
    except Exception as e:
        print("❌ 친구 목록 조회 실패:", e)
        print("응답 내용:", resp.text)
        return []

    data = resp.json()
    friends = data.get("elements", [])
    print(f"👥 친구 목록 {len(friends)}명")
    for f in friends:
        print(
            f"- 닉네임: {f.get('profile_nickname')}, "
            f"uuid: {f.get('uuid')}, "
            f"allowed_msg: {f.get('allowed_msg')}"
        )
    return friends

print(get_friends(KAKAO_ACCESS_TOKEN))

def send_kakao_to_me(access_token: str, text: str):
    """
    카카오톡 '나에게 보내기' 텍스트 메시지 전송
    """
    if not access_token:
        print("⚠ KAKAO_ACCESS_TOKEN 이 설정되어 있지 않습니다.")
        return

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
    }

    if len(text) > 950:
        text = text[:947] + "..."

    template = {
        "object_type": "text",
        "text": text,
        "link": {
            "web_url": "https://developers.kakao.com",
            "mobile_web_url": "https://developers.kakao.com",
        },
        "button_title": "바로가기",
    }

    data = {
        "template_object": json.dumps(template, ensure_ascii=False)
    }

    try:
        resp = requests.post(url, headers=headers, data=data, timeout=10)
        resp.raise_for_status()
        print("✅ 카카오톡(나에게) 알림 전송 완료")
    except Exception as e:
        print("❌ 카카오톡(나에게) 알림 전송 실패:", e)
        try:
            print("응답 내용:", resp.text)
        except Exception:
            pass


def send_kakao_to_friends(access_token: str, uuids: list, text: str):
    """
    카카오톡 친구에게 기본 텍스트 메시지 전송
    - uuids: 친구 uuid 문자열 리스트 (한 번에 최대 5개 권장)
    """
    if not access_token:
        print("⚠ KAKAO_ACCESS_TOKEN 이 설정되어 있지 않습니다.")
        return
    if not uuids:
        print("⚠ 보낼 친구 uuid 목록이 비어 있습니다.")
        return

    url = "https://kapi.kakao.com/v1/api/talk/friends/message/default/send"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
    }

    if len(text) > 950:
        text = text[:947] + "..."

    template = {
        "object_type": "text",
        "text": text,
        "link": {
            "web_url": "https://developers.kakao.com",
            "mobile_web_url": "https://developers.kakao.com",
        },
        "button_title": "자세히 보기",
    }

    data = {
        "receiver_uuids": json.dumps(uuids),
        "template_object": json.dumps(template, ensure_ascii=False),
    }

    try:
        resp = requests.post(url, headers=headers, data=data, timeout=10)
        resp.raise_for_status()
        print(f"✅ 친구 {len(uuids)}명에게 카카오톡 전송 완료")
    except Exception as e:
        print("❌ 친구 메시지 전송 실패:", e)
        try:
            print("응답 내용:", resp.text)
        except Exception:
            pass


# ================== 메인 실행 부분 ==================


def main():
    quiz_data = fetch_quiz_data()

    if not quiz_data:
        print("❌ 최종 데이터 획득 실패.")
        return

    # 1) dict든 뭐든 리스트로 정규화
    quiz_list = normalize_to_list(quiz_data)

    # 2) 오늘(KST) 데이터만 가져오기
    today_quiz = filter_today_kst_sorted(quiz_list)

    # 3) 캐시워크 / 토스 / 캐시닥 / 리브메이트만 필터링
    target_quiz = filter_target_services(today_quiz)

    # 4) 제목 파싱해서 platform/subject 추출 + 필요한 정보만 정리
    simplified = []
    for item in target_quiz:
        title = str(item.get("title", ""))
        platform, subject = parse_title_platform_subject(title)
        simplified.append({
            "platform": platform,
            "subject": subject,
            "ans": item.get("ans", ""),
            "linkaddr": item.get("linkaddr", ""),
            "CreateDate": item.get("CreateDate", "")
        })

    print("-" * 40)
    print(f"📅 오늘 대상 퀴즈(캐시워크/토스/캐시닥/리브메이트): {len(simplified)}개")

    # 5) 이전 상태 불러오기
    last_state = load_last_state()

    # 6) 새로 등장한 퀴즈만 추출
    new_items = diff_new_items(simplified, last_state)
    print(f"✨ 새로 발견된 퀴즈: {len(new_items)}개")

    # 7) 새 퀴즈가 있으면 카카오톡으로 알림
    if new_items:
        lines = ["[새 퀴즈 업데이트 알림]"]
        for item in new_items:
            lines.append(
                f"- [{item.get('platform')}] {item.get('subject')} / 정답: {item.get('ans')}"
            )
        msg = "\n".join(lines)

        # (1) 나에게도 보내기
        send_kakao_to_me(KAKAO_ACCESS_TOKEN, msg)

        # (2) 친구들에게도 보내기 (5명 단위로 끊어서 전송)
        chunk_size = 5
        for i in range(0, len(TARGET_FRIEND_UUIDS), chunk_size):
            chunk = TARGET_FRIEND_UUIDS[i:i + chunk_size]
            send_kakao_to_friends(KAKAO_ACCESS_TOKEN, chunk, msg)

    # 8) 현재 상태 저장
    save_current_state(simplified)


if __name__ == "__main__":
    main()
