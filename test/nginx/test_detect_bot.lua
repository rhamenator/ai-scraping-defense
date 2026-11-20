-- Execute the production access script with NGINX APIs stubbed out.
-- Run from the repository root: lua test/nginx/test_detect_bot.lua
local failures = 0
local cases = {
    {"Firefox", "/admin/", "TARPIT"},
    {"Firefox", "/wp-admin/", "TARPIT"},
    {"UnknownCrawler/1.0", "/secrets/", "TARPIT"},
    {"Googlebot", "/admin/", "TARPIT"},
    {"Bingbot", "/wp-admin/", "TARPIT"},
    {"sqlmap", "/admin/", "TARPIT"},
    {"Firefox", "/pricing", "ALLOWED"},
    {"UnknownCrawler/1.0", "/pricing", "ALLOWED"},
    {"Googlebot", "/pricing", "ALLOWED"},
    {"Bingbot", "/pricing", "ALLOWED"},
    {"sqlmap", "/pricing", "TARPIT"},
    {"sqlmap/1.7 (compatible; Googlebot/2.1)", "/pricing", "TARPIT"},
    {"nikto (Bingbot/2.0)", "/pricing", "TARPIT"},
    {"sqlmap Googlebot/2.1", "/pricing", "TARPIT", true},
    {"Googlebot/2.1", "/admin/", "TARPIT", true},
    {"Googlebot/2.1", "/pricing", "ALLOWED", true, true},
    {"Googlebot/2.1", "/pricing", "TARPIT", false, true},
}

for _, case in ipairs(cases) do
    local user_agent, uri, expected = case[1], case[2], case[3]
    local result = "ALLOWED"
    local logs = {}
    local function open_robots(path, mode)
        if path == "/etc/nginx/robots.txt" then
            return io.open("config/robots.txt", mode)
        end
        return io.open(path, mode)
    end
    local ngx_stub = {
        ERR = "ERR", INFO = "INFO", WARN = "WARN", DEBUG = "DEBUG", OK = 0,
        var = {remote_addr = "192.0.2.10", request_uri = uri},
        req = {
            get_headers = function()
                if case[5] then return {["User-Agent"] = user_agent, ["Accept"] = "*/*"} end
                return {
                    ["User-Agent"] = user_agent,
                    ["Accept"] = "text/html",
                    ["Accept-Language"] = "en-US",
                    ["Sec-Fetch-Site"] = "same-origin",
                    ["Referer"] = "https://example.test/",
                }
            end,
            get_method = function() return case[5] and "TRACE" or "GET" end,
        },
        now = function() return 1 end,
        log = function(_, ...)
            logs[#logs + 1] = table.concat({...})
        end,
        exec = function(path)
            assert(path == "/api/tarpit", "unexpected internal redirect")
            result = "TARPIT"
        end,
    }
    local env = setmetatable({
        ngx = ngx_stub, io = {open = open_robots},
        require = function(name)
            assert(name == "crawler_identity")
            return {is_verified = function() return case[4] == true end}
        end,
    }, {__index = _G})
    local script
    if setfenv then -- Lua 5.1 / LuaJIT (OpenResty)
        script = assert(loadfile("nginx/lua/detect_bot.lua"))
        setfenv(script, env)
    else -- Lua 5.2+
        script = assert(loadfile("nginx/lua/detect_bot.lua", "t", env))
    end
    script()
    local method = case[5] and " TRACE " or " GET "
    print(user_agent .. method .. uri .. " -> " .. result .. " (expected " .. expected .. ")")
    if result ~= expected then
        failures = failures + 1
    end
    if uri == "/admin/" or uri == "/wp-admin/" or uri == "/secrets/" then
        -- Robots enforcement must happen before the UA heuristics/exemptions.
        if not string.find(table.concat(logs), "accessed disallowed path", 1, true) then
            failures = failures + 1
        end
    end
end
assert(failures == 0, failures .. " robots enforcement checks failed")
