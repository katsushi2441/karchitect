<?php
/**
 * Kurage Architect 課金 (2026-07-29 ユーザー確定仕様):
 *   アカウントごとに1個目のプロジェクトは無料。2個目以降は1個 = 500円 または 50,000 URLAI。
 *   決済はKurageブログのペイウォールと同じ方式:
 *     - PayPal: Smart Buttons(Live) + サーバー側で注文API照合(COMPLETED・金額・注文ID使い回し禁止)
 *     - URLAI: Baseの受け取りウォレットへ送金 → eth_getLogs でオンチェーン検証(tx単位で消費管理)
 *   支払い1回 = プロジェクト作成クレジット1(URLAIはまとめ送金で複数クレジット化)。
 *   台帳は karchitect_data/credits.json (.htaccessで外部読み取り拒否・flock保護)。
 */

define('KAR_PRICE_JPY', 500);
define('KAR_PRICE_URLAI', 50000);
// 無料利用ユーザー(運営・協力テスター): プロジェクト作成/設計書出力の課金ゲートを通らない。
// AIはもともと全ユーザー共通でローカルOllama(gemma4)なので、この免除は支払いのみに効く。
define('KAR_FREE_USERS', 'xb_bittensor,uchinai_offcial');
function kar_bill_is_free_user($user) {
    foreach (explode(',', KAR_FREE_USERS) as $u) {
        $u = trim($u);
        if ($u !== '' && strcasecmp($u, (string)$user) === 0) { return true; }
    }
    return false;
}
// 設計書出力(ダウンロード): 1回目無料、2回目から都度100円 or 10,000 URLAI(統一レート0.01円/URLAI)
define('KAR_EXPORT_PRICE_JPY', 100);
define('KAR_EXPORT_PRICE_URLAI', 10000);
define('KAR_DATA_DIR', __DIR__ . '/karchitect_data');
define('KAR_LEDGER', KAR_DATA_DIR . '/credits.json');
// PayPalはブログと同じLiveアプリ(Client IDは公開値・Secretはブログの403保護ファイルを同一ホストで共用)
define('KAR_PAYPAL_CLIENT_ID', 'AbbwjyEYdGXqSqptChYFw7vxdOzBSZXiNslHASN1bHfxJZnV_borxUJdMzR1gs8njHQxqn69APqn5-MG');
define('KAR_PAYPAL_SECRET_FILE', __DIR__ . '/blog/paywall/data/paypal_secret.txt');
define('KAR_PAYPAL_API', 'https://api-m.paypal.com');
// URLAI (Base mainnet) — ブログのペイウォールと同じ受け取り先
define('KAR_URLAI_CONTRACT', '0xdaecdda6ad112f0e1e4097fb735dd01d9c33cba3');
define('KAR_URLAI_RECEIVER', '0x444fadbd6e1fed0cfbf7613b6c9f91b9021eecbd');
define('KAR_BASE_RPC', 'https://mainnet.base.org');

function kar_bill_load() {
    if (!file_exists(KAR_LEDGER)) { return array('users' => array(), 'used_orders' => array(), 'used_txs' => array()); }
    $j = json_decode((string)@file_get_contents(KAR_LEDGER), true);
    if (!is_array($j)) { $j = array(); }
    return $j + array('users' => array(), 'used_orders' => array(), 'used_txs' => array());
}

function kar_bill_save($d) {
    if (!is_dir(KAR_DATA_DIR)) { @mkdir(KAR_DATA_DIR, 0705, true); }
    $fp = fopen(KAR_LEDGER, 'c+');
    if (!$fp) { return false; }
    flock($fp, LOCK_EX);
    ftruncate($fp, 0);
    fwrite($fp, json_encode($d, JSON_UNESCAPED_UNICODE));
    fflush($fp);
    flock($fp, LOCK_UN);
    fclose($fp);
    return true;
}

function kar_bill_credits($user) {
    $d = kar_bill_load();
    return isset($d['users'][$user]['credits']) ? (int)$d['users'][$user]['credits'] : 0;
}

/** プロジェクト作成1回分のクレジットを消費(残があればtrue)。 */
function kar_bill_consume($user) {
    $d = kar_bill_load();
    $cur = isset($d['users'][$user]['credits']) ? (int)$d['users'][$user]['credits'] : 0;
    if ($cur < 1) { return false; }
    $d['users'][$user]['credits'] = $cur - 1;
    $d['users'][$user]['consumed_at'][] = time();
    return kar_bill_save($d);
}

function kar_bill_grant($user, $n, $method, $ref, $field = 'credits') {
    $d = kar_bill_load();
    $cur = isset($d['users'][$user][$field]) ? (int)$d['users'][$user][$field] : 0;
    $d['users'][$user][$field] = $cur + (int)$n;
    $d['users'][$user]['purchases'][] = array('method' => $method, 'ref' => $ref, 'n' => (int)$n,
        'field' => $field, 'ts' => time());
    return kar_bill_save($d);
}

// ---------------------------------------------------------------------------
// 設計書出力の課金(1回目無料・2回目から都度1出力=1エクスポートクレジット)
// ---------------------------------------------------------------------------
function kar_bill_export_state($user) {
    $d = kar_bill_load();
    $u = isset($d['users'][$user]) ? $d['users'][$user] : array();
    return array(
        'export_used' => isset($u['export_used']) ? (int)$u['export_used'] : 0,
        'export_credits' => isset($u['export_credits']) ? (int)$u['export_credits'] : 0,
    );
}

/** 出力可否: 'free'(初回無料枠) / 'credit'(クレジット消費で可) / 'need_payment'。 */
function kar_bill_export_gate($user) {
    $st = kar_bill_export_state($user);
    if ($st['export_used'] < 1) { return 'free'; }
    if ($st['export_credits'] >= 1) { return 'credit'; }
    return 'need_payment';
}

/** 出力成功時のコミット(無料枠はカウントのみ、それ以降はクレジット消費+カウント)。 */
function kar_bill_export_commit($user, $mode) {
    $d = kar_bill_load();
    $u = isset($d['users'][$user]) ? $d['users'][$user] : array();
    $used = isset($u['export_used']) ? (int)$u['export_used'] : 0;
    if ($mode === 'credit') {
        $cr = isset($u['export_credits']) ? (int)$u['export_credits'] : 0;
        if ($cr < 1) { return false; }
        $d['users'][$user]['export_credits'] = $cr - 1;
    }
    $d['users'][$user]['export_used'] = $used + 1;
    return kar_bill_save($d);
}

// ---------------------------------------------------------------------------
// PayPal (ブログ paywall/lib.php と同じ照合方式・500円/1クレジット)
// ---------------------------------------------------------------------------
function kar_http_json($url, $headers, $post_body = null) {
    $ch = curl_init($url);
    $opts = array(CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 25, CURLOPT_HTTPHEADER => $headers);
    if ($post_body !== null) { $opts[CURLOPT_POST] = true; $opts[CURLOPT_POSTFIELDS] = $post_body; }
    curl_setopt_array($ch, $opts);
    $res = curl_exec($ch);
    $code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    return array($code, json_decode((string)$res, true));
}

/** PayPal注文を照合し、正当なら1クレジット付与。返り値 [ok, message]。 */
function kar_bill_grant_paypal($user, $order_id, $price_jpy = KAR_PRICE_JPY, $field = 'credits') {
    $order_id = trim((string)$order_id);
    if (!preg_match('/^[A-Z0-9]{8,32}$/i', $order_id)) { return array(false, '注文IDの形式が不正です'); }
    $d = kar_bill_load();
    if (in_array($order_id, $d['used_orders'], true)) { return array(false, 'この注文IDは既に使用されています'); }
    $secret = file_exists(KAR_PAYPAL_SECRET_FILE) ? trim((string)@file_get_contents(KAR_PAYPAL_SECRET_FILE)) : '';
    if ($secret === '') { return array(false, '決済設定が未完了です(運営にご連絡ください)'); }
    list($code, $tok) = kar_http_json(KAR_PAYPAL_API . '/v1/oauth2/token',
        array('Authorization: Basic ' . base64_encode(KAR_PAYPAL_CLIENT_ID . ':' . $secret),
              'Content-Type: application/x-www-form-urlencoded'),
        'grant_type=client_credentials');
    if ($code !== 200 || empty($tok['access_token'])) { return array(false, 'PayPal認証に失敗しました'); }
    list($code, $order) = kar_http_json(KAR_PAYPAL_API . '/v2/checkout/orders/' . rawurlencode($order_id),
        array('Authorization: Bearer ' . $tok['access_token'], 'Content-Type: application/json'));
    if ($code !== 200 || !is_array($order)) { return array(false, '注文が見つかりません'); }
    if (($order['status'] ?? '') !== 'COMPLETED') { return array(false, '決済が完了していません(status=' . ($order['status'] ?? '?') . ')'); }
    $pu = $order['purchase_units'][0] ?? array();
    $amt = $pu['amount'] ?? ($pu['payments']['captures'][0]['amount'] ?? array());
    if (($amt['currency_code'] ?? '') !== 'JPY' || (float)($amt['value'] ?? 0) < $price_jpy) {
        return array(false, '決済金額が一致しません');
    }
    $d = kar_bill_load();  // 照合中の並行購入に備えて読み直し
    if (in_array($order_id, $d['used_orders'], true)) { return array(false, 'この注文IDは既に使用されています'); }
    $d['used_orders'][] = $order_id;
    kar_bill_save($d);
    kar_bill_grant($user, 1, 'paypal', $order_id, $field);
    return array(true, 'クレジットを1追加しました');
}

// ---------------------------------------------------------------------------
// URLAI オンチェーン検証 (tx単位で消費管理: まとめ送金は floor(合計/50,000) クレジット)
// ---------------------------------------------------------------------------
function kar_rpc($method, $params) {
    $body = json_encode(array('jsonrpc' => '2.0', 'id' => 1, 'method' => $method, 'params' => $params));
    $ch = curl_init(KAR_BASE_RPC);
    curl_setopt_array($ch, array(
        CURLOPT_POST => true, CURLOPT_POSTFIELDS => $body,
        CURLOPT_HTTPHEADER => array('Content-Type: application/json'),
        CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 20,
        // Cloudflare(error 1010)がUA無しを弾くことがあるため明示
        CURLOPT_USERAGENT => 'karchitect/1.0 (+https://karchitect.exbridge.jp/)',
    ));
    $res = curl_exec($ch);
    curl_close($ch);
    $j = json_decode((string)$res, true);
    return isset($j['result']) ? $j['result'] : null;
}

function kar_topic_addr($addr) {
    return '0x' . str_pad(substr(strtolower($addr), 2), 64, '0', STR_PAD_LEFT);
}

function kar_hex_to_tokens($hex) {
    $hex = ltrim(str_replace('0x', '', (string)$hex), '0');
    if ($hex === '') { return 0.0; }
    if (function_exists('bcadd')) {
        $dec = '0';
        foreach (str_split($hex) as $c) { $dec = bcadd(bcmul($dec, '16'), (string)hexdec($c)); }
        return (float)bcdiv($dec, bcpow('10', '18'), 6);
    }
    $val = 0.0;
    foreach (str_split($hex) as $c) { $val = $val * 16 + hexdec($c); }
    return $val / 1e18;
}

/** walletから受け取りへの未使用URLAI送金(直近~9日)を集め、50,000ごとに1クレジット付与。 */
function kar_bill_grant_urlai($user, $wallet, $price_urlai = KAR_PRICE_URLAI, $field = 'credits') {
    $wallet = strtolower(trim((string)$wallet));
    if (!preg_match('/^0x[a-f0-9]{40}$/', $wallet)) { return array(false, 'ウォレットアドレスの形式が不正です'); }
    $latest_hex = kar_rpc('eth_blockNumber', array());
    if (!$latest_hex) { return array(false, 'チェーンに接続できませんでした。少し待って再試行してください'); }
    $latest = hexdec($latest_hex);
    $topic0 = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef';
    $d = kar_bill_load();
    $found = array();  // txkey => amount
    // mainnet.base.org が eth_getLogs を10,000ブロック範囲に制限(2026-08実測。
    // 従来の50,000一括は HTTP 413 で全滅)。1万block×40 ≒ 9日分を新しい順に走査し、
    // 1クレジットぶん見つかったら早期終了(heteml PHPの実行時間対策。古い未使用txは
    // 次のクリックで拾われる)
    $started = time();
    for ($i = 0; $i < 40; $i++) {
        $to = $latest - $i * 10000;
        if ($to < 0) { break; }
        $from = max(0, $to - 9999);
        $logs = kar_rpc('eth_getLogs', array(array(
            'address' => KAR_URLAI_CONTRACT,
            'topics' => array($topic0, kar_topic_addr($wallet), kar_topic_addr(KAR_URLAI_RECEIVER)),
            'fromBlock' => '0x' . dechex($from), 'toBlock' => '0x' . dechex($to),
        )));
        if (is_array($logs)) {
            foreach ($logs as $lg) {
                $key = strtolower(($lg['transactionHash'] ?? '') . ':' . ($lg['logIndex'] ?? ''));
                if ($key === ':' || in_array($key, $d['used_txs'], true)) { continue; }
                $found[$key] = kar_hex_to_tokens($lg['data'] ?? '0x0');
            }
        }
        if (array_sum($found) >= $price_urlai) { break; }
        if (time() - $started > 20) { break; }
    }
    $total = array_sum($found);
    $credits = (int)floor($total / $price_urlai);
    if ($credits < 1) {
        return array(false, sprintf('未使用の受領を確認できませんでした(確認できた未使用額: %s URLAI)。%s URLAIを送金後、数十秒待ってから再試行してください',
            number_format($total), number_format($price_urlai)));
    }
    $d = kar_bill_load();
    foreach (array_keys($found) as $key) {
        if (!in_array($key, $d['used_txs'], true)) { $d['used_txs'][] = $key; }
    }
    kar_bill_save($d);
    kar_bill_grant($user, $credits, 'urlai', $wallet . ':' . implode(',', array_keys($found)), $field);
    return array(true, sprintf('%s URLAIの受領を確認し、クレジットを%d追加しました', number_format($total), $credits));
}
