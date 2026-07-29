<?php
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/auth_common.php';
require_once __DIR__ . '/karchitect_config.php';
date_default_timezone_set('Asia/Tokyo');

$THIS_FILE = 'karchitect.php';
if (isset($_GET['login'])) {
    header('Location: ' . url2ai_auth_login_url('/' . $THIS_FILE));
    exit;
}
if (isset($_GET['logout'])) {
    header('Location: ' . url2ai_auth_logout_url('/' . $THIS_FILE));
    exit;
}

$auth = url2ai_auth_bootstrap();
$logged_in = !empty($auth['logged_in']);
$session_user = $logged_in ? trim((string)$auth['session_user']) : '';
if (empty($_SESSION['karchitect_csrf'])) {
    $_SESSION['karchitect_csrf'] = bin2hex(random_bytes(24));
}
$csrf = (string)$_SESSION['karchitect_csrf'];

function kar_h($value) {
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

function kar_error($status, $detail) {
    http_response_code((int)$status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, max-age=0');
    echo json_encode(array('detail' => $detail), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function kar_route($path, $method) {
    if ($path === '/health' && $method === 'GET') {
        return true;
    }
    if ($path === '/api/projects' && in_array($method, array('GET', 'POST'), true)) {
        return true;
    }
    if (preg_match('#^/api/projects/[a-f0-9]{12}$#', $path)) {
        return in_array($method, array('GET'), true);
    }
    if (preg_match('#^/api/projects/[a-f0-9]{12}/messages$#', $path)) {
        return $method === 'POST';
    }
    if (preg_match('#^/api/projects/[a-f0-9]{12}/regenerate$#', $path)) {
        return $method === 'POST';
    }
    if (preg_match('#^/api/projects/[a-f0-9]{12}/requirements$#', $path)) {
        return $method === 'PUT';
    }
    if (preg_match('#^/api/projects/[a-f0-9]{12}/(document\.(md|html|pdf)|requirements\.json)$#', $path)) {
        return $method === 'GET';
    }
    if (preg_match('#^/api/projects/[a-f0-9]{12}/mermaid/(architecture|class|sequence)$#', $path)) {
        return $method === 'GET';
    }
    return false;
}

function kar_proxy($method, $path, $user) {
    $headers = array(
        'Accept: */*',
        'Content-Type: application/json',
        'X-KArchitect-Token: ' . KARCHITECT_API_TOKEN,
        'X-KArchitect-User: ' . $user,
    );
    $ch = curl_init(rtrim(KARCHITECT_API_BASE, '/') . $path);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 8);
    curl_setopt($ch, CURLOPT_TIMEOUT, 240);
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    curl_setopt($ch, CURLOPT_HEADER, true);
    if (in_array($method, array('POST', 'PUT'), true)) {
        $raw = file_get_contents('php://input');
        if (strlen($raw) > 100000) {
            kar_error(413, '入力が大きすぎます');
        }
        if ($raw !== '') {
            json_decode($raw);
            if (json_last_error() !== JSON_ERROR_NONE) {
                kar_error(400, 'JSONを確認してください');
            }
            curl_setopt($ch, CURLOPT_POSTFIELDS, $raw);
        }
    }
    $raw_response = curl_exec($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $header_size = (int)curl_getinfo($ch, CURLINFO_HEADER_SIZE);
    $curl_error = curl_error($ch);
    curl_close($ch);
    if ($raw_response === false || $curl_error !== '') {
        kar_error(502, 'Kurage Architect APIへ接続できません');
    }
    $response_headers = substr($raw_response, 0, $header_size);
    $body = substr($raw_response, $header_size);
    $content_type = 'application/json; charset=utf-8';
    $content_disposition = '';
    foreach (preg_split('/\r\n|\r|\n/', $response_headers) as $line) {
        if (stripos($line, 'Content-Type:') === 0) {
            $content_type = trim(substr($line, 13));
        } elseif (stripos($line, 'Content-Disposition:') === 0) {
            $content_disposition = trim(substr($line, 20));
        }
    }
    if (str_ends_with($path, '/document.html')) {
        $body = str_replace('/static/vendor/mermaid.min.js', 'assets/karchitect-mermaid.min.js', $body);
    }
    http_response_code($status ?: 502);
    header('Content-Type: ' . $content_type);
    header('Cache-Control: no-store, max-age=0');
    if ($content_disposition !== '') {
        header('Content-Disposition: ' . $content_disposition);
    }
    echo $body;
    exit;
}

if (isset($_GET['api'])) {
    if (!$logged_in || $session_user === '') {
        kar_error(401, 'Xでログインしてください');
    }
    if (strlen($session_user) > 200 || preg_match('/[\x00-\x1F\x7F]/', $session_user)) {
        kar_error(401, 'ログイン情報を確認できません');
    }
    $method = strtoupper((string)($_SERVER['REQUEST_METHOD'] ?? 'GET'));
    $path = (string)$_GET['api'];
    if (!kar_route($path, $method)) {
        kar_error(404, '未対応のAPIです');
    }
    if (in_array($method, array('POST', 'PUT', 'DELETE'), true)) {
        $sent_csrf = isset($_SERVER['HTTP_X_CSRF_TOKEN']) ? (string)$_SERVER['HTTP_X_CSRF_TOKEN'] : '';
        if ($sent_csrf === '' || !hash_equals($csrf, $sent_csrf)) {
            kar_error(403, 'CSRF検証に失敗しました');
        }
    }
    kar_proxy($method, $path, $session_user);
}

if (!$logged_in):
?><!doctype html>
<html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kurage Architect | AIシステム設計スタジオ</title>
<meta name="description" content="Gemmaと対話しながら要件を整理し、Markdown・Mermaid・PDFのシステム設計書を作成します。">
<link rel="canonical" href="https://kurage.exbridge.jp/karchitect.php">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@700;900&family=Noto+Sans+JP:wght@400;600;800&display=swap" rel="stylesheet">
<style>
/* kfreqai/kfreqaihl/kfxaiと同一のデザイントークン(2026-07-29統一) */
:root{--indigo:#2f6bd8;--cyan:#0b91a7;--ink:#17324d;--muted:#64788a;--border:#dbe6ee}
*{box-sizing:border-box}
body{min-height:100vh;margin:0;display:grid;place-items:center;padding:24px;color:var(--ink);
  background:radial-gradient(1000px 600px at 85% -5%,rgba(11,145,167,.10),transparent 60%),
    radial-gradient(800px 700px at -5% 45%,rgba(47,107,216,.07),transparent 55%),
    linear-gradient(170deg,#ffffff 0%,#f2f8fa 45%,#eaf5f4 100%);
  background-attachment:fixed;font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.card{width:min(620px,100%);padding:48px;border:1px solid var(--border);border-radius:24px;background:#fff;
  box-shadow:0 10px 26px rgba(25,72,78,.06),0 22px 60px rgba(37,88,105,.10);text-align:center}
.mark{width:84px;height:84px;margin:0 auto 20px;border-radius:50%;border:3px solid var(--cyan);object-fit:cover;
  box-shadow:0 10px 26px rgba(11,145,167,.24)}
h1{margin:0 0 4px;font-size:30px;font-weight:900;font-family:"Zen Maru Gothic","Noto Sans JP",sans-serif}
h1 em{font-style:normal;color:var(--indigo)}
.tagline{display:block;margin:0 0 16px;color:var(--cyan);font-size:12px;font-weight:800;letter-spacing:.1em}
p{margin:0 auto 26px;max-width:460px;color:var(--muted);line-height:1.9;font-size:14px}
.feats{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin:0 0 26px;padding:0;list-style:none}
.feats li{padding:6px 12px;border:1px solid var(--border);border-radius:999px;color:var(--ink);background:#f5fafb;font-size:11.5px;font-weight:700}
.login{display:inline-block;padding:14px 32px;border-radius:999px;color:#fff;text-decoration:none;font-weight:900;
  font-family:"Zen Maru Gothic","Noto Sans JP",sans-serif;font-size:15px;
  background:linear-gradient(90deg,#0b91a7,#2f6bd8);box-shadow:0 10px 26px rgba(11,145,167,.32);transition:transform .15s}
.login:hover{transform:translateY(-2px)}
.note{display:block;margin-top:18px;color:var(--muted);font-size:11px}
.note a{color:var(--indigo)}
</style>
<!-- Google tag (gtag.js) --><script async src="https://www.googletagmanager.com/gtag/js?id=G-BP0650KDFR"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}gtag('js',new Date());gtag('config','G-BP0650KDFR');</script>
<script>(function(){var s=document.createElement('script');s.src='https://aiknowledgecms.exbridge.jp/simpletrack.php?url='+encodeURIComponent(location.href)+'&ref='+encodeURIComponent(document.referrer);document.head.appendChild(s)})();</script>
</head><body><main class="card">
<img class="mark" src="images/kurage_avatar_face.webp" alt="Kurage">
<h1>Kurage <em>Architect</em></h1>
<span class="tagline">対話から、実装できる設計書へ。</span>
<p>作りたいシステムをKurageさんと相談すると、要件・未決事項・構成図を整理し、<b>実装にそのまま使える設計書</b>へ育てます。ローカルAI（Gemma 4）で動くオープンソースの設計スタジオです。</p>
<ul class="feats">
  <li>📝 要件JSON</li>
  <li>🗺️ Mermaid構成図</li>
  <li>📄 Markdown / PDF出力</li>
  <li>🔒 ローカルLLMで完結</li>
</ul>
<a class="login" href="?login=1">🪼 Xでログインして使う</a>
<span class="note">誰でも利用できます。設計プロジェクトはXアカウントごとに分離されます。</span>
</main></body></html>
<?php
    exit;
endif;

$app_file = __DIR__ . '/karchitect_app.html';
if (!is_file($app_file)) {
    http_response_code(503);
    echo 'Kurage Architect UI is not deployed.';
    exit;
}
$html = file_get_contents($app_file);
$html = str_replace('/static/styles.css', 'assets/karchitect.css', $html);
$html = str_replace('/static/app.js', 'assets/karchitect.js', $html);
$runtime = '<script>'
    . 'window.KARCHITECT_GATEWAY=' . json_encode($THIS_FILE, JSON_UNESCAPED_SLASHES) . ';'
    . 'window.KARCHITECT_CSRF=' . json_encode($csrf, JSON_UNESCAPED_SLASHES) . ';'
    . 'window.addEventListener("DOMContentLoaded",function(){'
    . 'var u=document.getElementById("authenticatedUser");if(u){u.textContent="@"+'
    . json_encode($session_user, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)
    . ';u.classList.remove("hidden")}var l=document.getElementById("logoutLink");if(l){l.href="?logout=1";l.classList.remove("hidden")}});'
    . '</script>'
    . '<script async src="https://www.googletagmanager.com/gtag/js?id=G-BP0650KDFR"></script>'
    . '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}gtag("js",new Date());gtag("config","G-BP0650KDFR");</script>'
    . '<script>(function(){var s=document.createElement("script");s.src="https://aiknowledgecms.exbridge.jp/simpletrack.php?url="+encodeURIComponent(location.href)+"&ref="+encodeURIComponent(document.referrer);document.head.appendChild(s)})();</script>';
$html = str_replace('</head>', $runtime . '</head>', $html);
header('Content-Type: text/html; charset=utf-8');
header('Cache-Control: no-store, max-age=0');
echo $html;
