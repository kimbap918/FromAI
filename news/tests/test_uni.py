import subprocess

def main():
    while True:
        print("\n📢 자동화 실행 메뉴")
        print("1. 주식 이미지 캡처")
        print("2. 환율 이미지 캡처")
        print("3. 뉴스 기사 추출")
        print("0. 종료")

        choice = input("번호를 입력하세요: ").strip()

        if choice == "1":
            subprocess.run(["python", "stock.py"])
        elif choice == "2":
            subprocess.run(["python", "hwan.py"])
        elif choice == "3":
            subprocess.run(["python", "news.py"])
        elif choice == "0":
            print("👋 종료합니다.")
            break
        else:
            print("❌ 올바른 번호를 입력하세요.")

if __name__ == "__main__":
    main()
