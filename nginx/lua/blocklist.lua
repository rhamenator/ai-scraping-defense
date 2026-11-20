-- luacheck: globals ngx
-- nginx/lua/blocklist.lua
-- Checks the connecting IP against a Redis blocklist.
-- IPs are stored as individual keys with a TTL (e.g., "blocklist:ip:1.2.3.4").
--
-- Moved into a module so detect_bot.lua can run the same check: a location with its own
-- access_by_lua_file (location /) replaces the server-level access_by_lua_file, so without
-- this call a blocklisted address was never refused on the main content location.

local M = {}

local redis_timeout_ms = 200 -- Connection/read timeout in milliseconds
local password_file = "/run/secrets/redis_password.txt"

local function settings()
    local tenant_id = os.getenv("TENANT_ID") or "default"
    return {
        host = os.getenv("REDIS_HOST") or "redis",
        port = tonumber(os.getenv("REDIS_PORT")) or 6379,
        db = tonumber(os.getenv("REDIS_DB_BLOCKLIST")) or 2,
        key_prefix = tenant_id .. ":blocklist:ip:", -- prefix for individual IP keys
    }
end

-- Connect, authenticate and select the blocklist database. Returns nil on any failure (callers fail open).
local function authenticate(red)
    local file = io.open(password_file, "r")
    if not file then return true end
    local password = file:read("*all")
    file:close()
    if not password then return true end
    password = string.gsub(password, "^%s*(.-)%s*$", "%1") -- trim whitespace
    local ok, err = red:auth(password)
    if not ok then ngx.log(ngx.ERR, "check_blocklist: Redis authentication failed: ", err) end
    return ok
end

local function open(cfg)
    local red = require("resty.redis"):new()
    red:set_timeout(redis_timeout_ms)
    local ok, err = red:connect(cfg.host, cfg.port)
    if not ok then
        ngx.log(ngx.ERR, "check_blocklist: Failed to connect to Redis at ", cfg.host, ":", cfg.port, ": ", err)
        return nil
    end
    if not authenticate(red) then
        red:close()
        return nil
    end
    local select_ok, select_err = red:select(cfg.db)
    if not select_ok then
        ngx.log(ngx.ERR, "check_blocklist: Failed to select Redis DB ", cfg.db, ": ", select_err)
        red:close()
        return nil
    end
    return red
end

-- True when the key exists; nil on a query error (fail open).
local function exists(red, key, remote_addr)
    local found, err = red:exists(key)
    if err then
        ngx.log(ngx.ERR, "check_blocklist: Failed to query Redis (EXISTS ", key, ") for IP ", remote_addr, ": ", err)
        red:close()
        return nil
    end
    local keepalive_ok, keepalive_err = red:set_keepalive(0, 100) -- 0 timeout, 100 pool size
    if not keepalive_ok then
        ngx.log(ngx.WARN, "check_blocklist: Failed to set Redis keepalive: ", keepalive_err)
        red:close()
    end
    return found == 1
end

function M.check()
    local remote_addr = ngx.var.remote_addr
    if not remote_addr then
        ngx.log(ngx.WARN, "check_blocklist: Could not get remote_addr")
        return -- Allow request if IP cannot be determined
    end
    local cfg = settings()
    local red = open(cfg)
    if not red then return end -- Fail open
    local key = cfg.key_prefix .. remote_addr
    if exists(red, key, remote_addr) then
        ngx.log(ngx.WARN, "check_blocklist: Blocking IP ", remote_addr, " found in Redis (Key: '", key, "')")
        return ngx.exit(ngx.HTTP_FORBIDDEN) -- 403 Forbidden
    end
end

return M
