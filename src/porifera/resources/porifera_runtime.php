<?php
function {{PROBE_FUNC_NAME}}($key, $value) {
    $data_file = {{OUTPUT_DIR}} . '/.porifera_data_{{TIMESTAMP}}.jsonl';
    $entry = json_encode(['key' => $key, 'value' => $value, 'value_type' => gettype($value), 'ts' => microtime(true)]);
    $fp = @fopen($data_file, 'a');
    if ($fp) {
        if (flock($fp, LOCK_EX)) {
            fwrite($fp, $entry . "\n");
            flock($fp, LOCK_UN);
        }
        fclose($fp);
    }
    return $value;
}
