import com.microsoft.playwright.*;
import com.microsoft.playwright.ElementHandle;
import com.microsoft.playwright.options.*;

import java.nio.file.*;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.regex.*;
import java.io.*;
import java.net.*;

public class Capture {
    static final int PAGE_LOAD_TIMEOUT_DEFAULT = 45;
    static final DateTimeFormatter TS = DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss");

    static class DeviceProfile {
        int width, height;
        String userAgent, locale;
        double deviceScaleFactor;
        boolean isMobile, hasTouch;
        DeviceProfile(int w, int h, String ua, String locale, double dpr, boolean m, boolean t) {
            this.width=w; this.height=h; this.userAgent=ua; this.locale=locale;
            this.deviceScaleFactor=dpr; this.isMobile=m; this.hasTouch=t;
        }
    }
    static final Map<String, DeviceProfile> DEVICES = new HashMap<>();
    static {
        DEVICES.put("galaxy_s20_ultra", new DeviceProfile(
                412, 915,
                "Mozilla/5.0 (Linux; Android 13; SM-G988N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36",
                "ko-KR",
                3.5, true, true
        ));
    }

    static final String[] AD_SELECTORS = new String[] {
            "iframe[id^='google_ads_iframe']",
            "iframe[src*='googlesyndication.com']",
            "ins.adsbygoogle",
            "div[id^='div-gpt-ad']",
            "iframe[src*='adop.cc']",
            "iframe[src*='adnxs.com']",
            "iframe[src*='adshub.kr']",
            "img[src*='ad']"
    };

    static final Pattern AD_HOST_HINT = Pattern.compile(
            "(adshub|adnxs|doubleclick|googlesyndication|googletagservices|adop|criteo)", Pattern.CASE_INSENSITIVE
    );

    static String ts() { return LocalDateTime.now().format(TS); }
    static String host(String url) {
        try {
            String h = new URI(url).getHost();
            return (h == null ? "page" : h.replace(":", "_"));
        } catch (Exception e) {
            return "page";
        }
    }
    static void ensureDir(String dir) throws IOException {
        Files.createDirectories(Paths.get(dir));
    }

    static List<String> loadUrlsFromFile(String path) {
        List<String> out = new ArrayList<>();
        try {
            String raw = Files.readString(Paths.get(path));
            StringBuilder sb = new StringBuilder();
            for (String line : raw.split("\\R")) {
                String t = line.trim();
                if (t.isEmpty() || t.startsWith("#")) continue;
                sb.append(t).append(" ");
            }
            for (String token : sb.toString().split("[,\\s;]+")) {
                if (token.startsWith("http://") || token.startsWith("https://")) {
                    if (!out.contains(token)) out.add(token);
                }
            }
        } catch (IOException e) {
            System.out.println("⚠️ 파일을 읽을 수 없음: " + path + " (" + e.getMessage() + ")");
        }
        return out;
    }

    static boolean waitAdsVisible(Page page, int timeoutSec, double minH, double minW) {
        long deadline = System.currentTimeMillis() + timeoutSec * 1000L;
        while (System.currentTimeMillis() < deadline) {
            try {
                for (String css : AD_SELECTORS) {
                    Locator loc = page.locator(css);
                    int count = (int) loc.count();
                    for (int i = 0; i < count; i++) {
                        BoundingBox box = loc.nth(i).boundingBox();  // 탑레벨 BoundingBox
                        if (box != null && box.width >= minW && box.height >= minH) {
                            return true;
                        }
                    }
                }
            } catch (PlaywrightException ignored) {}
            try { Thread.sleep(500); } catch (InterruptedException ie) { Thread.currentThread().interrupt(); }
        }
        return false;
    }


    static void dumpAdNetworkLogs(List<Response> responses) {
        int hits = 0;
        for (Response r : responses) {
            try {
                String url = r.url();
                if (AD_HOST_HINT.matcher(url).find()) {
                    System.out.println("AD-RESP " + r.status() + " -> " + (url.length()>200?url.substring(0,200):url));
                    hits++;
                }
            } catch (Exception ignored) {}
        }
        if (hits == 0) System.out.println("AD-RESP (none)");
    }

    static boolean runOnce(String url, String outDir, String mode,
                           String profileKey, boolean headed, int pageTimeoutSec,
                           String userDataDir, boolean logAds,
                           int adWaitSec, double sleepAfterVisibleSec, int retries) {
        int attempt = 0;
        while (attempt < retries) {
            attempt++;
            try (Playwright pw = Playwright.create()) {
                DeviceProfile dp = DEVICES.get(profileKey);
                if (dp == null) throw new RuntimeException("Unknown device: " + profileKey);

                BrowserType.LaunchPersistentContextOptions opt =
                        new BrowserType.LaunchPersistentContextOptions()
                                .setHeadless(!headed)
                                .setViewportSize(dp.width, dp.height)
                                .setUserAgent(dp.userAgent)
                                .setLocale(dp.locale)
                                .setDeviceScaleFactor(dp.deviceScaleFactor)
                                .setIsMobile(dp.isMobile)
                                .setHasTouch(dp.hasTouch);

                String udir = (userDataDir != null && !userDataDir.isBlank()) ? userDataDir : "./pw_profile";
                // ✅ String → Path 로 변경
                BrowserContext ctx = pw.chromium().launchPersistentContext(Paths.get(udir), opt);
                Page page = ctx.newPage();

                List<Response> adResponses = Collections.synchronizedList(new ArrayList<>());
                if (logAds) {
                    page.onResponse(adResponses::add);
                }

                try {
                    page.navigate(url, new Page.NavigateOptions().setTimeout(pageTimeoutSec * 1000.0));
                } catch (PlaywrightException pe) {
                    System.out.println("⚠️ Timeout, stopping load");
                    try { page.evaluate("() => window.stop()"); } catch (PlaywrightException ignored) {}
                }

                boolean visible = waitAdsVisible(page, adWaitSec, 40, 200);
                if (visible) {
                    try { Thread.sleep((long)(sleepAfterVisibleSec * 1000)); } catch (InterruptedException ie) { Thread.currentThread().interrupt(); }
                }

                if (logAds) dumpAdNetworkLogs(adResponses);

                ensureDir(outDir);
                Path path = Paths.get(outDir, host(url) + "_" + ts() + "_" + mode + ".png");
                page.screenshot(new Page.ScreenshotOptions()
                        .setFullPage("full".equalsIgnoreCase(mode))
                        .setPath(path)
                );

                System.out.println("✅ " + path + " (visible_ad=" + (visible ? "Y":"N") + ")");
                ctx.close();
                return true;
            } catch (Exception e) {
                System.out.println("❌ [" + attempt + "] " + url + " :: " + e.getMessage());
            }
        }
        return false;
    }

    public static void main(String[] args) {
        String mode = "viewport";
        boolean headed = false;
        String outdir = "모바일캡처";
        String device = "galaxy_s20_ultra";
        int pagetimeout = PAGE_LOAD_TIMEOUT_DEFAULT;
        String userdatadir = null;
        boolean logads = false;
        int adwait = 15;
        double sleepafter = 3.0;
        int retries = 1;

        List<String> items = new ArrayList<>();
        for (int i = 0; i < args.length; i++) {
            String a = args[i];
            switch (a) {
                case "--mode":        mode = (i+1<args.length)? args[++i] : mode; break;
                case "--headed":      headed = true; break;
                case "--outdir":      outdir = (i+1<args.length)? args[++i] : outdir; break;
                case "--device":      device = (i+1<args.length)? args[++i] : device; break;
                case "--pagetimeout": pagetimeout = (i+1<args.length)? Integer.parseInt(args[++i]) : pagetimeout; break;
                case "--userdatadir": userdatadir = (i+1<args.length)? args[++i] : null; break;
                case "--logads":      logads = true; break;
                case "--adwait":      adwait = (i+1<args.length)? Integer.parseInt(args[++i]) : adwait; break;
                case "--sleepafter":  sleepafter = (i+1<args.length)? Double.parseDouble(args[++i]) : sleepafter; break;
                case "--retries":     retries = (i+1<args.length)? Integer.parseInt(args[++i]) : retries; break;
                default:
                    if (!a.startsWith("--")) items.add(a);
                    else System.out.println("⚠️ 알 수 없는 옵션: " + a);
            }
        }

        List<String> urls = new ArrayList<>();
        for (String it : items) {
            if (it.startsWith("http://") || it.startsWith("https://")) {
                urls.add(it);
            } else {
                Path p = Paths.get(it);
                if (Files.exists(p) && Files.isRegularFile(p)) {
                    urls.addAll(loadUrlsFromFile(it));
                } else {
                    System.out.println("⚠️ 무시: " + it + " (URL도 파일도 아님)");
                }
            }
        }
        if (urls.isEmpty()) {
            urls = List.of("https://www.rnx.kr/news/articleView.html?idxno=744909");
        }

        for (String u : urls) {
            runOnce(u, outdir, mode, device, headed, pagetimeout, userdatadir, logads, adwait, sleepafter, retries);
        }
    }
}
