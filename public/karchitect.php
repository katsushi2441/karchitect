<?php
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/auth_common.php';
require_once __DIR__ . '/karchitect_config.php';
require_once __DIR__ . '/karchitect_billing.php';
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
// 管理者は利用者を選んで代理操作できる（テスターが詰まったときの手当て用）。
$KAR_ADMIN_USERS = array('xb_bittensor');
$is_admin = ($session_user !== '' && in_array($session_user, $KAR_ADMIN_USERS, true));
$act_as = '';
if ($is_admin && isset($_GET['as'])) {
    $candidate = trim((string)$_GET['as']);
    // 管理者以外は $act_as を空のままにする。ヘッダはバックエンドでも検証される。
    if ($candidate !== '' && preg_match('/^[A-Za-z0-9_]{1,200}$/', $candidate)) {
        $act_as = $candidate;
    }
}
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
    if ($path === '/billing/status' && $method === 'GET') {
        return true;
    }
    if (in_array($path, array('/billing/paypal', '/billing/urlai',
                              '/billing/export/paypal', '/billing/export/urlai'), true) && $method === 'POST') {
        return true;
    }
    if ($path === '/api/projects' && in_array($method, array('GET', 'POST'), true)) {
        return true;
    }
    if ($path === '/api/admin/users' && $method === 'GET') {
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

function kar_backend_get($path, $user) {
    // 課金ゲート用の内部GET(既存プロジェクト数の確認)。kar_proxyと違いechoせず返す。
    $ch = curl_init(rtrim(KARCHITECT_API_BASE, '/') . $path);
    curl_setopt_array($ch, array(
        CURLOPT_RETURNTRANSFER => true, CURLOPT_CONNECTTIMEOUT => 8, CURLOPT_TIMEOUT => 30,
        CURLOPT_HTTPHEADER => array('Accept: application/json',
            'X-KArchitect-Token: ' . KARCHITECT_API_TOKEN,
            'X-KArchitect-User: ' . $user)));
    $body = curl_exec($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    return array($status, json_decode((string)$body, true));
}

function kar_proxy($method, $path, $user, $consume_credit_user = null) {
    $headers = array(
        'Accept: */*',
        'Content-Type: application/json',
        'X-KArchitect-Token: ' . KARCHITECT_API_TOKEN,
        'X-KArchitect-User: ' . $user,
    );
    if (isset($GLOBALS['act_as']) && $GLOBALS['act_as'] !== '') {
        $headers[] = 'X-KArchitect-Act-As: ' . $GLOBALS['act_as'];
    }
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
    // 有料操作が成功したときだけ消費(失敗時は減らさない)。
    // $consume_credit_user: 文字列=プロジェクト作成のクレジット消費(後方互換)、
    // array('user'=>..,'export'=>'free'|'credit')=設計書出力のコミット。
    if ($consume_credit_user !== null && $status >= 200 && $status < 300) {
        if (is_array($consume_credit_user)) {
            kar_bill_export_commit($consume_credit_user['user'], $consume_credit_user['export']);
        } else {
            kar_bill_consume($consume_credit_user);
        }
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

    // ---- 課金(1個目無料・2個目以降 500円 or 50,000 URLAI = クレジット1) ----
    if ($path === '/billing/status') {
        list($st, $projects) = kar_backend_get('/api/projects', $session_user);
        $count = ($st === 200 && is_array($projects)) ? count($projects) : null;
        $ex = kar_bill_export_state($session_user);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: no-store, max-age=0');
        echo json_encode(array(
            'projects' => $count,
            'first_free' => ($count === 0),
            'credits' => kar_bill_credits($session_user),
            'price_jpy' => KAR_PRICE_JPY,
            'price_urlai' => KAR_PRICE_URLAI,
            'export_used' => $ex['export_used'],
            'export_credits' => $ex['export_credits'],
            'export_price_jpy' => KAR_EXPORT_PRICE_JPY,
            'export_price_urlai' => KAR_EXPORT_PRICE_URLAI,
            'urlai_receiver' => KAR_URLAI_RECEIVER,
            'paypal_client_id' => KAR_PAYPAL_CLIENT_ID,
        ), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        exit;
    }
    if (in_array($path, array('/billing/paypal', '/billing/urlai',
                              '/billing/export/paypal', '/billing/export/urlai'), true)) {
        $in = json_decode((string)file_get_contents('php://input'), true);
        if (!is_array($in)) {
            kar_error(400, 'JSONを確認してください');
        }
        $is_export = strpos($path, '/export/') !== false;
        $field = $is_export ? 'export_credits' : 'credits';
        if (substr($path, -7) === '/paypal') {
            list($ok, $msg) = kar_bill_grant_paypal($session_user, isset($in['order_id']) ? $in['order_id'] : '',
                $is_export ? KAR_EXPORT_PRICE_JPY : KAR_PRICE_JPY, $field);
        } else {
            list($ok, $msg) = kar_bill_grant_urlai($session_user, isset($in['wallet']) ? $in['wallet'] : '',
                $is_export ? KAR_EXPORT_PRICE_URLAI : KAR_PRICE_URLAI, $field);
        }
        $ex = kar_bill_export_state($session_user);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: no-store, max-age=0');
        echo json_encode(array('ok' => $ok, 'message' => $msg,
            'credits' => kar_bill_credits($session_user),
            'export_credits' => $ex['export_credits']), JSON_UNESCAPED_UNICODE);
        exit;
    }
    // 設計書出力(ダウンロード)のゲート: 1回目無料、2回目からエクスポートクレジット必須。
    // 画面内プレビュー(document.html)は無料のまま(アプリ表示に必須のため対象外)。
    if (preg_match('#^/api/projects/[a-f0-9]{12}/(document\.(md|pdf)|requirements\.json|mermaid/(architecture|class|sequence))$#', $path)
            && $method === 'GET') {
        $gate = kar_bill_export_gate($session_user);
        if ($gate === 'need_payment') {
            kar_error(402, 'EXPORT_PAYMENT_REQUIRED');
        }
        kar_proxy($method, $path, $session_user, array('user' => $session_user, 'export' => $gate));
    }
    if ($path === '/api/projects' && $method === 'POST') {
        list($st, $projects) = kar_backend_get('/api/projects', $session_user);
        if ($st !== 200 || !is_array($projects)) {
            kar_error(502, 'Kurage Architect APIへ接続できません');
        }
        $needs_credit = count($projects) >= 1;  // 1個目は無料
        if ($needs_credit && kar_bill_credits($session_user) < 1) {
            kar_error(402, 'PAYMENT_REQUIRED');
        }
        kar_proxy($method, $path, $session_user, $needs_credit ? $session_user : null);
    }

    kar_proxy($method, $path, $session_user);
}

if (!$logged_in):
?><!doctype html>
<html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kurage Architect | AIと対話して作るシステム設計書（1個目無料・要件定義/Mermaid構成図/PDF出力）</title>
<meta name="description" content="曖昧なアイデアを、AIと相談しながら要件・未決事項・構成図つきのシステム設計書へ。ローカルLLM(Gemma 4)で動くオープンソースの設計スタジオ。1個目のプロジェクトは無料、Markdown・Mermaid・PDF出力対応。">
<meta name="robots" content="index, follow">
<link rel="canonical" href="https://kurage.exbridge.jp/karchitect.php">
<!-- OGP / Twitter Card -->
<meta property="og:type" content="website">
<meta property="og:site_name" content="Kurageプロジェクト">
<meta property="og:title" content="Kurage Architect — 対話から、実装できる設計書へ。">
<meta property="og:description" content="曖昧なアイデアを、AIと相談しながら要件・構成図つきのシステム設計書に。ローカルLLMで動くオープンソース。1個目のプロジェクトは無料。">
<meta property="og:url" content="https://kurage.exbridge.jp/karchitect.php">
<meta property="og:image" content="https://kurage.exbridge.jp/images/karchitect-ogp.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Kurage Architect — 対話から、実装できる設計書へ。">
<meta name="twitter:description" content="AIと相談しながら要件・構成図つきのシステム設計書に。1個目無料・ローカルLLM・オープンソース。">
<meta name="twitter:image" content="https://kurage.exbridge.jp/images/karchitect-ogp.png">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "WebApplication",
  "name": "Kurage Architect",
  "url": "https://kurage.exbridge.jp/karchitect.php",
  "description": "AIと対話しながら要件を整理し、Mermaid構成図・Markdown・PDFのシステム設計書を作成するオープンソースの設計スタジオ。",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Web",
  "inLanguage": "ja",
  "image": "https://kurage.exbridge.jp/images/karchitect-ogp.png",
  "offers": [
    {"@type": "Offer", "price": "0", "priceCurrency": "JPY", "description": "1個目の設計プロジェクトは無料"},
    {"@type": "Offer", "price": "500", "priceCurrency": "JPY", "description": "2個目以降のプロジェクト(1個・買い切り)"},
    {"@type": "Offer", "price": "100", "priceCurrency": "JPY", "description": "設計書の出力(2回目以降・都度)"}
  ],
  "publisher": {"@type": "Organization", "name": "Kurageプロジェクト", "url": "https://kurage.exbridge.jp/"}
}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@700;900&family=Noto+Sans+JP:wght@400;600;800&display=swap" rel="stylesheet">
<style>
/* LP: kfreqaiと同一トークンの白ベース版(2026-07-29 ユーザー指定「白ベースの背景」) */
:root{--indigo:#2f6bd8;--cyan:#0b91a7;--ink:#17324d;--muted:#64788a;--border:#dbe6ee;--coin:#b98422}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);background:#ffffff;
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;line-height:1.8}
.disp{font-family:"Zen Maru Gothic","Noto Sans JP",sans-serif}
main{max-width:960px;margin:0 auto;padding:0 20px 60px}
.hero{padding:64px 0 44px;text-align:center}
.mark{width:96px;height:96px;border-radius:50%;border:3px solid var(--cyan);object-fit:cover;
  box-shadow:0 10px 26px rgba(11,145,167,.22)}
h1{margin:18px 0 6px;font-size:clamp(30px,5vw,44px);font-weight:900;letter-spacing:.01em}
h1 em{font-style:normal;color:var(--indigo)}
.tagline{display:block;margin:0 0 18px;color:var(--cyan);font-size:14px;font-weight:800;letter-spacing:.12em}
.lead{max-width:640px;margin:0 auto 28px;color:var(--muted);font-size:15px}
.cta{display:inline-block;padding:15px 36px;border-radius:999px;color:#fff;text-decoration:none;font-weight:900;font-size:16px;
  background:linear-gradient(90deg,#0b91a7,#2f6bd8);box-shadow:0 10px 26px rgba(11,145,167,.30);transition:transform .15s}
.cta:hover{transform:translateY(-2px)}
.cta-note{display:block;margin-top:12px;color:var(--muted);font-size:12px}
h2.sec{margin:56px 0 8px;font-size:14px;color:var(--cyan);text-transform:uppercase;letter-spacing:.1em;font-weight:800}
h3.sec-title{margin:0 0 18px;font-size:24px;font-weight:900}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:760px){.grid3{grid-template-columns:1fr}}
.card{padding:20px;border:1px solid var(--border);border-radius:16px;background:#fff;box-shadow:0 10px 26px rgba(25,72,78,.06)}
.card .ic{font-size:24px}
.card b{display:block;margin:8px 0 4px;font-size:15px}
.card p{margin:0;color:var(--muted);font-size:12.5px}
.steps{counter-reset:st;display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:760px){.steps{grid-template-columns:1fr}}
.step{position:relative;padding:20px 20px 20px 58px;border:1px solid var(--border);border-radius:16px;background:#fff}
.step::before{counter-increment:st;content:counter(st);position:absolute;left:16px;top:18px;width:30px;height:30px;
  display:grid;place-items:center;border-radius:50%;color:#fff;font-weight:900;
  background:linear-gradient(135deg,#0b91a7,#2f6bd8);font-family:"Zen Maru Gothic",sans-serif}
.step b{display:block;font-size:14px}
.step p{margin:4px 0 0;color:var(--muted);font-size:12px}
.pricing{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:stretch}
@media(max-width:760px){.pricing{grid-template-columns:1fr}}
.price-card{padding:26px;border:1px solid var(--border);border-radius:18px;background:#fff;text-align:center;box-shadow:0 10px 26px rgba(25,72,78,.06)}
.price-card.free{border-color:#bfe0d5;background:#f6fcf9}
.price-card.paid{border-color:#c8d9f4;background:#f8fafd}
.price-card .plan{font-size:12px;font-weight:800;letter-spacing:.1em;color:var(--muted)}
.price-card .price{margin:8px 0 2px;font-size:34px;font-weight:900}
.price-card.free .price{color:#16805f}
.price-card.paid .price{color:var(--indigo)}
.price-card .per{color:var(--muted);font-size:12px}
.price-card ul{margin:14px 0 0;padding:0;list-style:none;color:var(--muted);font-size:12.5px;text-align:left}
.price-card li{padding:5px 0;border-top:1px dashed var(--border)}
.price-card li:first-child{border-top:0}
.paybadges{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:12px}
.paybadge{padding:5px 12px;border:1px solid var(--border);border-radius:999px;font-size:11px;font-weight:700;background:#fff}
.note-card{margin-top:14px;padding:16px 18px;border:1px solid var(--border);border-radius:14px;background:#fbfdfe;color:var(--muted);font-size:12.5px}
.note-card a{color:var(--indigo)}
footer{padding:28px 20px 40px;border-top:1px solid var(--border);color:var(--muted);text-align:center;font-size:12px}
footer a{color:var(--indigo)}
</style>
<!-- Google tag (gtag.js) --><script async src="https://www.googletagmanager.com/gtag/js?id=G-BP0650KDFR"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}gtag('js',new Date());gtag('config','G-BP0650KDFR');</script>
<script>(function(){var s=document.createElement('script');s.src='https://kurage.exbridge.jp/simpletrack.php?url='+encodeURIComponent(location.href)+'&ref='+encodeURIComponent(document.referrer);document.head.appendChild(s)})();</script>
</head><body>
<main>
  <section class="hero">
    <img class="mark" src="images/kurage_avatar_face.webp" alt="Kurage">
    <h1 class="disp">Kurage <em>Architect</em></h1>
    <span class="tagline disp">対話から、実装できる設計書へ。</span>
    <p class="lead">「作りたいものはあるけど、要件がまとまらない」——そんな曖昧なアイデアを、Kurageさんと相談しながら<b>実装にそのまま使えるシステム設計書</b>へ育てる、AI設計スタジオです。ローカルAI（Gemma 4）で動くオープンソースです。</p>
    <a class="cta disp" href="?login=1">🪼 Xでログインして無料で始める</a>
    <span class="cta-note">1個目の設計プロジェクトは無料。登録はXログインだけです。</span>
  </section>

  <h2 class="sec disp">FEATURES</h2>
  <h3 class="sec-title disp">できること</h3>
  <div class="grid3">
    <div class="card"><span class="ic">💬</span><b>AIが要件を聞き出す</b><p>不足情報を1〜3問ずつ確認しながら、確定事項・提案・仮定・未決事項を分けて整理します。</p></div>
    <div class="card"><span class="ic">🗺️</span><b>構成図まで自動生成</b><p>アーキテクチャ図・クラス図・シーケンス図をMermaidで生成。設計書に組み込まれます。</p></div>
    <div class="card"><span class="ic">📄</span><b>そのまま渡せる出力</b><p>Markdown・要件JSON・HTML・PDFで出力。AIコーディング(バイブコーディング)の入力にも最適です。</p></div>
    <div class="card"><span class="ic">🔒</span><b>ローカルLLMで完結</b><p>頭脳はローカルのGemma 4。アイデアが外部のAI事業者に送られることはありません。</p></div>
    <div class="card"><span class="ic">🧭</span><b>仕様駆動フロー</b><p>discover → clarify → specify → plan → design → review → ready の7段階で設計が育ちます。</p></div>
    <div class="card"><span class="ic">🛟</span><b>回答を失わない</b><p>LLM障害時もあなたの回答は保存。復旧後に続きから設計を進められます。</p></div>
  </div>

  <h2 class="sec disp">HOW IT WORKS</h2>
  <h3 class="sec-title disp">使い方は3ステップ</h3>
  <div class="steps">
    <div class="step"><b>Xでログイン</b><p>登録不要。設計プロジェクトはXアカウントごとに分離されます。</p></div>
    <div class="step"><b>作りたいものを話す</b><p>短い説明でOK。Kurageさんが必要なことを質問しながら要件を固めます。</p></div>
    <div class="step"><b>設計書を受け取る</b><p>Markdown / JSON / Mermaid / PDFでダウンロード。実装へ直行できます。</p></div>
  </div>

  <h2 class="sec disp">PRICING</h2>
  <h3 class="sec-title disp">料金 — 1個目は無料</h3>
  <div class="pricing">
    <div class="price-card free">
      <div class="plan disp">はじめての設計</div>
      <div class="price disp">無料</div>
      <div class="per">1個目のプロジェクト</div>
      <ul>
        <li>✅ 全機能そのまま使えます（対話・構成図・出力）</li>
        <li>✅ 設計書の出力（MD/PDF/JSON/Mermaid）も1回無料</li>
        <li>✅ クレジットカード登録も不要</li>
        <li>✅ Xログインだけで今すぐ開始</li>
      </ul>
    </div>
    <div class="price-card paid">
      <div class="plan disp">2個目からのプロジェクト</div>
      <div class="price disp">500円<span style="font-size:15px;color:var(--muted)"> / 個</span></div>
      <div class="per">または <b style="color:var(--coin)">50,000 URLAI</b>（買い切り）</div>
      <ul>
        <li>💳 PayPal決済 — 完了と同時に自動でプロジェクト枠を追加</li>
        <li>🪙 URLAIトークン(Base) — 送金をオンチェーンで自動確認</li>
        <li>📄 設計書の出力は2回目から都度 <b>100円</b> or <b>10,000 URLAI</b></li>
        <li>♻️ 使い切り型。月額・サブスクではありません</li>
      </ul>
      <div class="paybadges"><span class="paybadge">PayPal</span><span class="paybadge">🪙 URLAI</span></div>
    </div>
  </div>
  <div class="note-card">
    決済は<a href="https://kurage.exbridge.jp/blog/" target="_blank" rel="noopener">Kurageブログの有料記事</a>と同じ仕組み（PayPalはサーバー側で注文照合、URLAIはBaseチェーンのオンチェーン検証）です。URLAIは<a href="https://katsushi2441.github.io/vwork/blog/2026-07-29-urlai-where-to-use.html" target="_blank" rel="noopener">対応サイトを拡大中のプロジェクトトークン</a>で、<a href="https://kurl2earn.exbridge.jp/" target="_blank" rel="noopener">kurl2earn</a>で無料で受け取ることもできます。
  </div>

  <section class="hero" style="padding:48px 0 8px">
    <a class="cta disp" href="?login=1">🪼 Xでログインして無料で始める</a>
    <span class="cta-note">誰でも利用できます。1個目のプロジェクトは無料です。</span>
  </section>
</main>
<footer>Kurage Architect — <a href="https://kurage.exbridge.jp/">Kurageプロジェクト</a> ・ <a href="https://github.com/katsushi2441/karchitect" target="_blank" rel="noopener">オープンソース(GitHub)</a> ・ <a href="https://kurage.exbridge.jp/vibe-prototype.html">設計書からプロトタイプを作る（バイブプロトタイプ制作）</a> ・ <a href="https://kurage.exbridge.jp/tokusho.php">特定商取引法に基づく表記</a><br>設計内容はローカルLLMで処理され、外部AI事業者へは送信されません。<br>生成した設計書は<b>オープンソースと同じ扱い</b>です（改変・再配布・商用利用可。当社も自由に利用・公開します）。<b>公開されては困る情報は入力しないでください。</b>秘密保持が必要な場合は<a href="https://kurage.exbridge.jp/terms.html#nda">秘密保持オプション（有償）</a>で承ります。詳細は<a href="https://kurage.exbridge.jp/terms.html">利用規約</a>をご覧ください。</footer>
</body></html>
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
    . 'window.KARCHITECT_IS_ADMIN=' . ($is_admin ? 'true' : 'false') . ';window.KARCHITECT_ACT_AS=' . json_encode($act_as) . ';window.KARCHITECT_CSRF=' . json_encode($csrf, JSON_UNESCAPED_SLASHES) . ';'
    . 'window.addEventListener("DOMContentLoaded",function(){'
    . 'var u=document.getElementById("authenticatedUser");if(u){u.textContent="@"+'
    . json_encode($session_user, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)
    . ';u.classList.remove("hidden")}var l=document.getElementById("logoutLink");if(l){l.href="?logout=1";l.classList.remove("hidden")}});'
    . '</script>'
    . '<script async src="https://www.googletagmanager.com/gtag/js?id=G-BP0650KDFR"></script>'
    . '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}gtag("js",new Date());gtag("config","G-BP0650KDFR");</script>'
    . '<script>(function(){var s=document.createElement("script");s.src="https://kurage.exbridge.jp/simpletrack.php?url="+encodeURIComponent(location.href)+"&ref="+encodeURIComponent(document.referrer);document.head.appendChild(s)})();</script>';
$html = str_replace('</head>', $runtime . '</head>', $html);
header('Content-Type: text/html; charset=utf-8');
header('Cache-Control: no-store, max-age=0');
echo $html;
