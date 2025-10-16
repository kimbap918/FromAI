package kr.newshub.trend.console.main;

import com.fasterxml.jackson.databind.ObjectMapper;
import kr.newshub.trend.console.main.dto.response.common.CrawResponse;
import kr.newshub.trend.console.main.service.common.NaverCrawService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class TrendApplication {
    public static void main(String[] args) throws Exception {
        // Spring Boot ApplicationContext 실행
        ConfigurableApplicationContext context = SpringApplication.run(TrendApplication.class, args);

        // URL 인자가 있는 경우 실행
        if (args.length > 0) {
            String url = args[0];

            // 서비스 가져오기
            NaverCrawService service = context.getBean(NaverCrawService.class);

            // 크롤 실행
            CrawResponse response = service.runNaver(url);

            // JSON 변환 후 출력
            ObjectMapper mapper = new ObjectMapper();
            String json = mapper.writerWithDefaultPrettyPrinter().writeValueAsString(response);
            System.out.println(json);

            // 실행 후 종료
            SpringApplication.exit(context);
        }
    }
}
