package kr.newshub.trend.console.main.dto.response.common;

import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;     
import lombok.AllArgsConstructor;   
import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CrawResponse {
    private List<Result> results;
    private List<String> errors;

    @Data
    @Builder
    @NoArgsConstructor    
    @AllArgsConstructor
    public static class Result {
        private String os;
        private String osSource;
        private String profileUrl;
        private String keyword;
        private String naverName;
        private String naverImage;
        private String naverInfo;
    }
}
