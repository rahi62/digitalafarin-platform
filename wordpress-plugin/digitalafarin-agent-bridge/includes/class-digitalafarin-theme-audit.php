<?php

declare(strict_types=1);

final class DigitalAfarin_Theme_Audit {
    public const OPTION = 'digitalafarin_agent_theme_audit_log';
    private const MAX_EVENTS = 200;
    private const BLOCKED_KEYS = [
        'content', 'replacementcontent', 'originalcontent', 'backupcontent',
        'apppassword', 'password', 'secret', 'token', 'authorization',
    ];

    public static function boot(): void {
        add_action('digitalafarin_agent_theme_audit', [self::class, 'record'], 10, 2);
    }

    public static function record(string $action, $details = []): void {
        if (!function_exists('get_option') || !function_exists('update_option')) return;
        $events = get_option(self::OPTION, []);
        if (!is_array($events)) $events = [];

        array_unshift($events, [
            'id' => function_exists('wp_generate_uuid4') ? wp_generate_uuid4() : self::uuid(),
            'action' => substr(trim($action), 0, 100),
            'details' => self::redact(is_array($details) ? $details : []),
            'userId' => function_exists('get_current_user_id') ? (int) get_current_user_id() : 0,
            'createdAt' => gmdate('c'),
        ]);

        $events = array_slice($events, 0, self::MAX_EVENTS);
        update_option(self::OPTION, $events, false);
    }

    public static function recent(int $limit = 50): array {
        if (!function_exists('get_option')) return [];
        $events = get_option(self::OPTION, []);
        if (!is_array($events)) return [];
        return array_values(array_slice($events, 0, max(1, min(100, $limit))));
    }

    public static function redact(array $details): array {
        $result = [];
        foreach ($details as $key => $value) {
            $keyString = (string) $key;
            if (in_array(strtolower($keyString), self::BLOCKED_KEYS, true)) continue;
            if (is_array($value)) {
                $result[$keyString] = self::redact($value);
            } elseif (is_bool($value) || is_int($value) || is_float($value) || $value === null) {
                $result[$keyString] = $value;
            } elseif (is_string($value)) {
                $result[$keyString] = substr($value, 0, 1000);
            }
        }
        return $result;
    }

    private static function uuid(): string {
        $data = random_bytes(16);
        $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
        $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
        return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
    }
}
