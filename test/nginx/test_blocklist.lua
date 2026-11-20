-- Run from the repository root: lua test/nginx/test_blocklist.lua
-- 1. blocklist.lua refuses a listed address, allows an unlisted one, and fails open on a Redis error.
-- 2. detect_bot.lua runs the blocklist check first, so `location /` (which has its own access
--    handler and therefore replaces the server-level check_blocklist.lua) still refuses a blocked address.
local failures = 0
local function check(name, ok)
    print((ok and "ok   " or "FAIL ") .. name)
    if not ok then failures = failures + 1 end
end

local function run_blocklist(exists, connect_ok)
    local exited
    local ngx_stub = {
        ERR = "ERR", WARN = "WARN", HTTP_FORBIDDEN = 403, var = {remote_addr = "192.0.2.10"},
        log = function() end, exit = function(code) exited = code; return code end,
    }
    local redis = {
        new = function()
            return {
                set_timeout = function() end,
                connect = function() if connect_ok then return true end return nil, "refused" end,
                select = function() return true end,
                exists = function() return exists end,
                set_keepalive = function() return true end,
                close = function() end,
                auth = function() return true end,
            }
        end,
    }
    local env = setmetatable({
        ngx = ngx_stub, io = {open = function() return nil end},
        require = function(name) assert(name == "resty.redis", name); return redis end,
    }, {__index = _G})
    local chunk
    if setfenv then chunk = assert(loadfile("nginx/lua/blocklist.lua")); setfenv(chunk, env)
    else chunk = assert(loadfile("nginx/lua/blocklist.lua", "t", env)) end
    chunk().check()
    return exited
end

check("a listed address is refused with 403", run_blocklist(1, true) == 403)
check("an unlisted address is allowed", run_blocklist(0, true) == nil)
check("a Redis connection failure fails open", run_blocklist(1, false) == nil)

-- detect_bot.lua must call the blocklist check before anything else.
local order = {}
local ngx_stub = {
    ERR = "ERR", INFO = "INFO", WARN = "WARN", DEBUG = "DEBUG", OK = 0,
    var = {remote_addr = "192.0.2.10", request_uri = "/pricing"},
    req = {get_headers = function() return {["User-Agent"] = "Firefox", ["Accept-Language"] = "en", ["Sec-Fetch-Site"] = "same-origin", ["Referer"] = "https://example.test/"} end,
           get_method = function() return "GET" end},
    now = function() return 1 end, log = function() end, exec = function() order[#order + 1] = "exec" end,
}
local env = setmetatable({
    ngx = ngx_stub, io = {open = function(path, mode) return io.open("config/robots.txt", mode) end},
    require = function(name)
        if name == "robots_policy" then return dofile("nginx/lua/robots_policy.lua") end
        if name == "blocklist" then return {check = function() order[#order + 1] = "blocklist" end} end
        return {is_verified = function() return false end}
    end,
}, {__index = _G})
local script
if setfenv then script = assert(loadfile("nginx/lua/detect_bot.lua")); setfenv(script, env)
else script = assert(loadfile("nginx/lua/detect_bot.lua", "t", env)) end
script()
check("detect_bot.lua runs the blocklist check", order[1] == "blocklist")
assert(failures == 0, failures .. " blocklist checks failed")
