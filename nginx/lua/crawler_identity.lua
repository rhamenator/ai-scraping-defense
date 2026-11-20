-- luacheck: globals ngx
-- Only cached, forward-confirmed reverse DNS can grant a crawler exemption.
local M = {}
local suffixes = {
    googlebot = {".googlebot.com", ".google.com"},
    bingbot = {".search.msn.com"},
}
local enabled = {}
for token in (os.getenv("VERIFIED_CRAWLERS") or "googlebot,bingbot"):gmatch("[^,%s]+") do
    enabled[token:lower()] = true
end
local nameserver = os.getenv("CRAWLER_DNS_NAMESERVER") or "127.0.0.11"
local ttl = 7200
local budget_ms = 1000

local function claimed_provider(ua)
    ua = (ua or ""):lower()
    for _, provider in ipairs({"googlebot", "bingbot"}) do
        if enabled[provider] and ua:find("%f[%w]" .. provider .. "%f[^%w%-_]") then
            return provider
        end
    end
end

local function hostname_matches(hostname, provider)
    hostname = hostname:lower():gsub("%.$", "")
    for _, suffix in ipairs(suffixes[provider]) do
        if hostname:sub(-#suffix) == suffix then
            return hostname
        end
    end
end

local function verify(ip, provider)
    local resolver = require "resty.dns.resolver"
    local r = resolver:new({nameservers = {nameserver}, retrans = 1, timeout = budget_ms})
    if not r then return false end
    local deadline = ngx.now() + budget_ms / 1000
    local reverse = r:reverse_query(ip)
    if not reverse or reverse.errcode then return false end
    local ipv6 = ip:find(":", 1, true) ~= nil
    local expected = ipv6 and resolver.expand_ipv6_addr(ip):lower() or ip
    for _, ptr in ipairs(reverse) do
        local hostname = ptr.ptrdname and hostname_matches(ptr.ptrdname, provider)
        if hostname then
            local remaining = math.floor((deadline - ngx.now()) * 1000)
            if remaining <= 0 then return false end
            r:set_timeout(remaining)
            local qtype = ipv6 and resolver.TYPE_AAAA or resolver.TYPE_A
            local forward = r:query(hostname, {qtype = qtype})
            if forward and not forward.errcode then
                for _, answer in ipairs(forward) do
                    if answer.type == qtype and answer.address then
                        local address = ipv6 and resolver.expand_ipv6_addr(answer.address):lower() or answer.address
                        if address == expected then return true end
                    end
                end
            end
        end
    end
    return false
end

local function refresh(premature, cache, key, ip, provider)
    if premature then
        cache:delete(key .. ":pending")
        return
    end
    local ok, verified = pcall(verify, ip, provider)
    -- Failure, timeout, or an unexpected resolver exception is unverified.
    cache:set(key, ok and verified == true, ttl)
    cache:delete(key .. ":pending")
end

function M.is_verified(ip, ua)
    local provider = claimed_provider(ua)
    local cache = ngx.shared and ngx.shared.crawler_verification_cache
    if not provider or not ip or not cache then return false end
    local key = provider .. ":" .. ip
    local cached = cache:get(key)
    if cached ~= nil then return cached == true end
    -- Deduplicate work across workers. No DNS queries run in the access handler.
    if cache:add(key .. ":pending", true, 2) then
        local ok = ngx.timer.at(0, refresh, cache, key, ip, provider)
        if not ok then cache:delete(key .. ":pending") end
    end
    -- The first request receives the normal checks while verification runs.
    return false
end

return M
