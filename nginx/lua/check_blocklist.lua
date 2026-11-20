-- luacheck: globals ngx
-- nginx/lua/check_blocklist.lua
-- Checks the connecting IP against a Redis blocklist.
-- IPs are stored as individual keys with a TTL (e.g., "blocklist:ip:1.2.3.4").
--
-- Thin wrapper: the check itself lives in blocklist.lua so that detect_bot.lua can run it too.
require("blocklist").check()
