package kr.newshub.trend.console.main.service.common;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import kr.newshub.trend.console.main.dto.response.common.CrawResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class NaverCrawService {

    private final ObjectMapper objectMapper;

    // -----------------------------
    // 설정
    // -----------------------------
    private static final Pattern OS_PATTERN = Pattern.compile("[?&]os=(\\d+)");
    private static final int REQUEST_TIMEOUT = 10_000; // ms
    private static final int MAX_RETRIES = 3;

    private static final String DEFAULT_USER_AGENT =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
            "AppleWebKit/537.36 (KHTML, like Gecko) " +
            "Chrome/124.0.0.0 Safari/537.36";

    public CrawResponse runNaver(String url) {
        log.info("네이버 크롤링 시작 - url: {}", url);

        try {
            HttpClient client = createHttpClient();

            List<CrawResponse.Result> results = new ArrayList<>();
            List<String> errors = new ArrayList<>();

            processUrl(client, url == null ? "" : url.strip(), results, errors);

            return CrawResponse.builder()
                    .results(results)
                    .errors(errors)
                    .build();

        } catch (Exception e) {
            log.error("네이버 크롤링 오류", e);
            return CrawResponse.builder()
                    .results(new ArrayList<>())
                    .errors(Collections.singletonList("unhandled: " + e.getMessage()))
                    .build();
        }
    }

    private HttpClient createHttpClient() {
        return HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NORMAL)
                .connectTimeout(Duration.ofMillis(REQUEST_TIMEOUT))
                .build();
    }

    private void processUrl(HttpClient client,
                            String url,
                            List<CrawResponse.Result> results,
                            List<String> errors) {
        if (url.isEmpty()) return;

        try {
            String osValue = extractOsFromUrl(url);

           if (osValue != null) {
                CrawResponse.Result first = tryParseDirect(client, url, osValue);
                if (isResultFilled(first)) {
                    results.add(first);
                } else {
                    // 기존 앵커 추적
                    CrawResponse.Result deep = tryParseViaAnchors(client, url);
                    if (isResultFilled(deep)) {
                        results.add(deep);
                    } else {
                        // ✅ 재검색 폴백 (프로필/인물정보)
                        CrawResponse.Result requery = tryRequeryWithKeyword(client, url);
                        if (isResultFilled(requery)) {
                            results.add(requery);
                        } else {
                            // ✅ People 검색 폴백
                            CrawResponse.Result people = tryPeopleSearch(client, url);
                            if (isResultFilled(people)) {
                                results.add(people);
                            } else if (first != null) {
                                results.add(first); // 최소한의 결과라도 반환
                            } else {
                                errors.add("URL: " + url + ", Error: 파싱 실패");
                            }
                        }
                    }
                }
            } else {
                // URL 자체에 os가 없을 때
                CrawResponse.Result deep = tryParseViaAnchors(client, url);
                if (isResultFilled(deep)) {
                    results.add(deep);
                } else {
                    CrawResponse.Result requery = tryRequeryWithKeyword(client, url);
                    if (isResultFilled(requery)) {
                        results.add(requery);
                    } else {
                        CrawResponse.Result people = tryPeopleSearch(client, url);
                        if (isResultFilled(people)) {
                            results.add(people);
                        } else {
                            errors.add("URL: " + url + ", Error: os 추출 실패");
                        }
                    }
                }
            }


            // 살짝 웨이트
            try {
                Thread.sleep((long) (200 + Math.random() * 300));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }

        } catch (Exception e) {
            errors.add("URL: " + url + ", Error: " + e.getMessage());
        }
    }

    private boolean isResultFilled(CrawResponse.Result r) {
        if (r == null) return false;
        boolean hasName = r.getNaverName() != null && !r.getNaverName().isBlank();
        boolean hasImg  = r.getNaverImage() != null && !r.getNaverImage().isBlank();
        boolean hasInfo = r.getNaverInfo() != null && !r.getNaverInfo().equals("{}");
        return hasName || hasImg || hasInfo;
    }

    private CrawResponse.Result tryParseDirect(HttpClient client, String url, String osValue) {
        try {
            String html = fetchHtmlWithRetry(client, url, null);
            Map<String, Object> profileData = parseProfilePage(html);
            return createResult(osValue, url, profileData);
        } catch (Exception e) {
            log.debug("직접 파싱 실패: {}", e.toString());
            return null;
        }
    }

    private CrawResponse.Result tryParseViaAnchors(HttpClient client, String startUrl)
            throws IOException, InterruptedException {

        String html = fetchHtmlWithRetry(client, startUrl, null);
        Document doc = Jsoup.parse(html);

        // 1) 프로필/인물정보 앵커
        Element anchor = findProfileAnchor(doc);
        if (anchor != null) {
            CrawResponse.Result r = tryParseFromAnchor(client, startUrl, anchor);
            if (isResultFilled(r)) return r;
        }

        // 2) 더보기 앵커
        Element more = findAnswerMoreAnchor(doc);
        if (more != null) {
            CrawResponse.Result r = tryParseFromAnchor(client, startUrl, more);
            if (isResultFilled(r)) return r;
        }

        return null;
    }

    private CrawResponse.Result tryParseFromAnchor(HttpClient client, String startUrl, Element anchor)
            throws IOException, InterruptedException {

        String href = anchor.attr("href");
        if (href == null || href.isEmpty()) return null;

        String newUrl = URI.create(startUrl).resolve(href).toString();
        String newHtml = fetchHtmlWithRetry(client, newUrl, startUrl);

        String osValue = extractOsFromUrl(newUrl);
        if (osValue == null) {
            Matcher m2 = OS_PATTERN.matcher(newHtml);
            if (m2.find()) osValue = m2.group(1);
        }
        if (osValue == null) return null;

        Map<String, Object> data = parseProfilePage(newHtml);
        return createResult(osValue, newUrl, data);
    }

    private String extractOsFromUrl(String url) {
        Matcher matcher = OS_PATTERN.matcher(url);
        return matcher.find() ? matcher.group(1) : null;
    }

    // -----------------------------
    // HTTP
    // -----------------------------
    private String fetchHtmlWithRetry(HttpClient client, String url, String referer)
            throws IOException, InterruptedException {
        Exception last = null;
        for (int i = 0; i < MAX_RETRIES; i++) {
            try {
                return fetchHtml(client, url, referer);
            } catch (Exception e) {
                last = e;
                if (i < MAX_RETRIES - 1) {
                    Thread.sleep((long) (600 * Math.pow(2, i)));
                }
            }
        }
        if (last instanceof IOException) throw (IOException) last;
        if (last instanceof InterruptedException) throw (InterruptedException) last;
        throw new IOException("fetch failed: " + last);
    }

    private String fetchHtml(HttpClient client, String url, String referer)
            throws IOException, InterruptedException {

        HttpRequest.Builder rb = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofMillis(REQUEST_TIMEOUT))
                .GET()
                .header("User-Agent", DEFAULT_USER_AGENT)
                .header("Accept-Language", "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7")
                .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                .header("Cache-Control", "no-cache")
                .header("Pragma", "no-cache");

        if (referer != null && !referer.isBlank()) {
            rb.header("Referer", referer);
        }

        HttpRequest req = rb.build();
        HttpResponse<byte[]> res = client.send(req, HttpResponse.BodyHandlers.ofByteArray());

        if (res.statusCode() != 200) {
            throw new IOException("HTTP " + res.statusCode());
        }

        // 인코딩 추정: meta charset이 euc-kr일 수도 있으니 문자열로 곧장 해석하지 않고 Jsoup에 맡김
        // 여기서는 바이트 -> UTF-8 로 일단 변환(대부분 UTF-8)하되, 파서는 Document.parse에서 텍스트만 쓸 것임.
        return new String(res.body(), StandardCharsets.UTF_8);
    }

    // -----------------------------
    // 파싱
    // -----------------------------
    private Map<String, Object> parseProfilePage(String html) {
        Map<String, Object> data = new LinkedHashMap<>();
        Document doc = Jsoup.parse(html);

        // 0) JSON-LD (Person) 우선 시도
        try {
            for (Element s : doc.select("script[type=application/ld+json]")) {
                String json = s.data();
                if (json == null || json.isBlank()) continue;
                if (!json.contains("\"@type\"")) continue;

                // 간단 파싱(배열/객체 둘 다 허용)
                List<Map<String,Object>> candidates = new ArrayList<>();
                Object any = objectMapper.readValue(json, Object.class);
                if (any instanceof Map) {
                    candidates.add((Map<String, Object>) any);
                } else if (any instanceof List) {
                    for (Object o : (List<?>) any) {
                        if (o instanceof Map) candidates.add((Map<String, Object>) o);
                    }
                }

                for (Map<String,Object> o : candidates) {
                    Object t = o.get("@type");
                    if (t == null) continue;
                    String ts = String.valueOf(t);
                    if (!ts.equalsIgnoreCase("Person")) continue;

                    // name / image / sameAs
                    String name = String.valueOf(o.getOrDefault("name", "")).trim();
                    if (!name.isEmpty()) data.putIfAbsent("naver_name", name);

                    Object image = o.get("image");
                    if (image instanceof String) {
                        String img = ((String) image).trim();
                        if (!img.isEmpty()) data.putIfAbsent("naver_image", img);
                    }

                    Object sameAs = o.get("sameAs");
                    if (sameAs instanceof List) {
                        for (Object link : (List<?>) sameAs) {
                            String href = String.valueOf(link);
                            if (href.toLowerCase().contains("instagram"))
                                data.putIfAbsent("인스타그램", href);
                            if (href.toLowerCase().contains("twitter") || href.toLowerCase().contains("x.com"))
                                data.putIfAbsent("X(트위터)", href);
                        }
                    }
                }
            }
        } catch (Exception ignore) {}

        // 1) 이름(여러 폴백)
        if (blank(data.get("naver_name"))) {
            Element nameTag = firstNonNull(
                    doc.selectFirst("span.area_text_title strong._text"),
                    doc.selectFirst("div.cm_top_wrap .title"),
                    doc.selectFirst("div.cm_top_wrap .cm_title .title"),
                    doc.selectFirst("div.cm_top_wrap .title_area .title"),
                    doc.selectFirst("h2.title"),
                    doc.selectFirst("div.profile_title h2"),
                    doc.selectFirst("strong.name"),
                    doc.selectFirst(".cm_title span.tit")
            );
            data.put("naver_name", norm(text(nameTag)));
        }

        // 2) 상세 정보: 모든 dl에서 dt→dd 페어 수집
        for (Element dl : doc.select("div.detail_info dl, .cm_list_info dl, dl")) {
            // 그룹 단위
            for (Element group : dl.select("div.info_group, dl")) {
                for (Element dt : group.select("> dt")) {
                    String label = norm(dt.text());
                    if (label.isEmpty()) continue;
                    Element dd = dt.nextElementSibling();
                    if (dd == null || !"dd".equalsIgnoreCase(dd.tagName())) {
                        dd = group.selectFirst("> dd");
                    }
                    String value = norm(dd != null ? dd.text() : "");
                    if (!label.isEmpty() && !value.isEmpty()) data.put(label, value);
                }
            }
            // 최상위 dl 바로 밑 dt→dd
            for (Element dt : dl.select("> dt")) {
                String label = norm(dt.text());
                Element dd = dt.nextElementSibling();
                if (dd != null && "dd".equalsIgnoreCase(dd.tagName())) {
                    String value = norm(dd.text());
                    if (!label.isEmpty() && !value.isEmpty()) data.put(label, value);
                }
            }
        }

        // 3) 이미지
        if (blank(data.get("naver_image"))) {
            Element imageTag = firstNonNull(
                    doc.selectFirst("img.profile_img"),
                    doc.selectFirst("a.thumb._item img._img"),
                    doc.selectFirst("div.img_scroll ul.img_list li._item:first-child img"),
                    doc.selectFirst("a.thumb img._img"),
                    doc.selectFirst("img._img"),
                    doc.selectFirst("img.cm_thumb_img")
            );
            String imageSrc = getImgSrc(imageTag);
            if (imageSrc == null || imageSrc.isBlank()) {
                // og:image 폴백
                Element og = doc.selectFirst("meta[property=og:image]");
                if (og != null) {
                    String ogSrc = norm(og.attr("content"));
                    if (!ogSrc.isEmpty()) imageSrc = ogSrc;
                }
            }
            data.put("naver_image", imageSrc == null ? "" : imageSrc);
        }

        // 4) 사이트/공식링크 수집
        for (Element dt : doc.select("div.detail_info dt, .cm_list_info dt, dl dt")) {
            String key = norm(dt.text());
            if ("사이트".equals(key) || "공식사이트".equals(key)) {
                Element dd = dt.nextElementSibling();
                if (dd != null) {
                    for (Element a : dd.select("a[href]")) {
                        String text = norm(a.text());
                        String href = norm(a.attr("href"));
                        if (!text.isEmpty() && !href.isEmpty()) {
                            data.put(text, href);
                        }
                    }
                }
            }
        }
        // 전역 링크 스캔(인스타/트위터/X)
        for (Element a : doc.select("a[href]")) {
            String t = norm(a.text());
            String href = norm(a.attr("href"));
            String lower = t.toLowerCase(Locale.ROOT);
            if (!href.isEmpty() && (
                    lower.contains("인스타그램") || lower.contains("instagram") ||
                    lower.contains("트위터") || lower.contains("x(트위터)") || href.contains("x.com")
            )) {
                data.putIfAbsent(t.isEmpty() ? "인스타그램" : t, href);
            }
        }

        // 빈 키 정리
        data.entrySet().removeIf(e -> e.getValue() == null || String.valueOf(e.getValue()).isBlank());

        return data;
    }

    private Element findProfileAnchor(Document doc) {
        Element root = Optional.ofNullable(doc.selectFirst("#main_pack")).orElse(doc);
        for (Element el : root.select("a,button,span,div,li")) {
            String t1 = norm(el.ownText());
            String t2 = norm(el.text());
            boolean hit = "프로필".equals(t1) || "프로필".equals(t2)
                       || "인물정보".equals(t1) || "인물정보".equals(t2);
            if (hit) {
                if ("a".equalsIgnoreCase(el.tagName()) && el.hasAttr("href")) return el;
                // 상위 a 승격
                Element p = el.parent();
                while (p != null) {
                    if ("a".equalsIgnoreCase(p.tagName()) && p.hasAttr("href")) return p;
                    p = p.parent();
                }
            }
        }
        return null;
    }

    private Element findAnswerMoreAnchor(Document doc) {
        Element el = doc.selectFirst("div.answer_more > a");
        if (el != null && el.hasAttr("href")) return el;

        for (Element a : doc.select("a[href]")) {
            String t1 = norm(a.ownText());
            String t2 = norm(a.text());
            if ((t1.contains("더보기") || t2.contains("더보기")) && a.hasAttr("href")) return a;
        }

        el = doc.selectFirst(".answer_more a");
        if (el != null && el.hasAttr("href")) return el;
        return null;
    }

    // -----------------------------
    // 유틸
    // -----------------------------
    private String norm(String s) {
        if (s == null || s.isEmpty()) return "";
        return s.replaceAll("\\s+", " ").strip();
    }

    private boolean blank(Object o) {
        return o == null || String.valueOf(o).isBlank();
    }

    private String text(Element e) {
        return e == null ? "" : e.text();
    }

    private String getImgSrc(Element img) {
        if (img == null) return null;
        for (String attr : new String[]{"src", "data-src", "data-lazy-src"}) {
            String v = norm(img.attr(attr));
            if (!v.isEmpty()) return v;
        }
        String srcset = norm(img.attr("srcset"));
        if (!srcset.isEmpty()) {
            try {
                String[] parts = srcset.split(",");
                if (parts.length > 0) {
                    String[] urlParts = parts[0].trim().split("\\s+");
                    if (urlParts.length > 0 && !urlParts[0].isEmpty()) return urlParts[0];
                }
            } catch (Exception ignore) {}
        }
        return null;
    }

    // 1) URL의 query= 값을 UTF-8로 디코드해서 꺼내기
    private String getQueryParam(String url, String key) {
        try {
            var uri = URI.create(url);
            String q = uri.getRawQuery();
            if (q == null) return null;
            for (String pair : q.split("&")) {
                int idx = pair.indexOf('=');
                String k = idx >= 0 ? pair.substring(0, idx) : pair;
                String v = idx >= 0 ? pair.substring(idx + 1) : "";
                if (k.equals(key)) {
                    return java.net.URLDecoder.decode(v, java.nio.charset.StandardCharsets.UTF_8);
                }
            }
        } catch (Exception ignore) {}
        return null;
    }

    // 2) "원 검색어 + 프로필/인물정보"로 재검색해서 os/앵커를 회수하는 폴백
    private CrawResponse.Result tryRequeryWithKeyword(HttpClient client, String originalUrl)
            throws IOException, InterruptedException {
        String q = getQueryParam(originalUrl, "query");
        if (q == null || q.isBlank()) return null;

        String[] suffixes = new String[]{" 프로필", " 인물정보"};
        for (String sfx : suffixes) {
            String newQ = q + sfx;
            String reUrl = "https://search.naver.com/search.naver?where=nexearch&sm=tab_etc&query="
                    + java.net.URLEncoder.encode(newQ, java.nio.charset.StandardCharsets.UTF_8);
            CrawResponse.Result via = tryParseViaAnchors(client, reUrl);
            if (isResultFilled(via)) return via;
        }
        return null;
    }

    // 3) People 검색(인물 전용 검색)로 한 번 더 시도
    private CrawResponse.Result tryPeopleSearch(HttpClient client, String originalUrl)
            throws IOException, InterruptedException {
        String q = getQueryParam(originalUrl, "query");
        if (q == null || q.isBlank()) return null;

        String peopleUrl = "https://people.search.naver.com/search.naver?query="
                + java.net.URLEncoder.encode(q, java.nio.charset.StandardCharsets.UTF_8);
        // People 페이지에도 프로필 카드/링크가 있고, 그 링크를 타면 대개 os가 붙은 인물 프로필로 이동함
        CrawResponse.Result via = tryParseViaAnchors(client, peopleUrl);
        if (isResultFilled(via)) return via;

        // "배우" 등 직업 힌트까지 붙여서 한 번 더
        String peopleUrl2 = "https://people.search.naver.com/search.naver?query="
                + java.net.URLEncoder.encode(q + " 배우", java.nio.charset.StandardCharsets.UTF_8);
        via = tryParseViaAnchors(client, peopleUrl2);
        if (isResultFilled(via)) return via;

        return null;
    }



    @SafeVarargs
    private final <T> T firstNonNull(T... candidates) {
        for (T c : candidates) if (c != null) return c;
        return null;
    }

    private CrawResponse.Result createResult(String osValue, String url, Map<String, Object> profileData)
            throws JsonProcessingException {

        String name   = String.valueOf(profileData.getOrDefault("naver_name", ""));
        String img    = String.valueOf(profileData.getOrDefault("naver_image", ""));

        Map<String, String> naverInfo = profileData.entrySet().stream()
                .filter(e -> !Objects.equals(e.getKey(), "naver_name"))
                .filter(e -> !Objects.equals(e.getKey(), "naver_image"))
                .collect(Collectors.toMap(
                        e -> String.valueOf(e.getKey()),
                        e -> String.valueOf(e.getValue()),
                        (a, b) -> a,
                        LinkedHashMap::new
                ));

        CrawResponse.Result result = new CrawResponse.Result();
        result.setOs(osValue);
        result.setProfileUrl(url);
        result.setOsSource("NAVER");
        // 파이썬과 동일: keyword=이름
        result.setKeyword(name);
        result.setNaverName(name);
        result.setNaverImage(img);
        result.setNaverInfo(objectMapper.writeValueAsString(naverInfo));
        return result;
    }
}
