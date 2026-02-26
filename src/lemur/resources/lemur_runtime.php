<?php
function {{PROBE_FUNC_NAME}}($key, $value) {
    $data_file = __DIR__ . '/.lemur_data.jsonl';
    $entry = json_encode(['key' => $key, 'value' => $value, 'ts' => microtime(true)]);
    @file_put_contents($data_file, $entry . "\n", FILE_APPEND | LOCK_EX);
    return $value;
}
