-- luacheck: ignore 212/self
-- No live DNS: run the production verifier with a controlled resolver/timer/cache.
local function new_cache(state)
    local values, expires, cache = {}, {}, {}
    function cache:get(key)
        if expires[key] and expires[key] <= state.now then values[key] = nil end
        return values[key]
    end
    function cache:set(key, value, ttl)
        values[key], expires[key] = value, state.now + ttl
        return true
    end
    function cache:add(key, value, ttl)
        if self:get(key) ~= nil then return nil end
        return self:set(key, value, ttl)
    end
    function cache:delete(key) values[key] = nil end
    return cache
end

local function new_resolver(options, state)
    local resolver = {TYPE_A = 1, TYPE_AAAA = 28}
    function resolver:new(settings)
        assert(settings.timeout == 1000 and settings.retrans == 1)
        if options.new_failure then return nil end
        return self
    end
    function resolver:set_timeout(ms) assert(ms > 0 and ms <= 1000) end
    function resolver:reverse_query()
        state.reverse_calls = state.reverse_calls + 1
        if options.exception then error("resolver failure") end
        if options.reverse_failure then return nil, "timeout" end
        if options.deadline then state.now = state.now + 2 end
        return {{ptrdname = options.hostname or "crawl.example.googlebot.com"}}
    end
    function resolver:query(_, settings)
        state.forward_calls = state.forward_calls + 1
        if options.forward_failure then return nil, "timeout" end
        return {{type = settings.qtype, address = options.address or "192.0.2.10"}}
    end
    function resolver.expand_ipv6_addr(ip)
        if ip == "2001:db8::1" or ip == "2001:0db8:0:0:0:0:0:1" then
            return "2001:db8:0:0:0:0:0:1"
        end
        return ip
    end
    return resolver
end

local function new_env(options, state, cache, resolver)
    local env = setmetatable({
        os = {getenv = function(name)
            if name == "VERIFIED_CRAWLERS" then return options.enabled end
        end},
        ngx = {
            now = function() return state.now end,
            shared = {crawler_verification_cache = cache},
            timer = {at = function(_, callback, ...)
                if options.timer_failure then return nil, "too many pending timers" end
                state.queue[#state.queue + 1] = {callback, ...}
                return true
            end},
        },
        require = function(name)
            assert(name == "resty.dns.resolver")
            return resolver
        end,
    }, {__index = _G})
    if options.no_cache then env.ngx.shared = {} end
    return env
end

local function load_module(env)
    if setfenv then
        local script = assert(loadfile("nginx/lua/crawler_identity.lua"))
        setfenv(script, env)
        return script()
    end
    return assert(loadfile("nginx/lua/crawler_identity.lua", "t", env))()
end

local function scenario(options)
    options = options or {}
    local state = {now = 0, queue = {}, reverse_calls = 0, forward_calls = 0}
    local env = new_env(options, state, new_cache(state), new_resolver(options, state))
    local verifier = load_module(env)
    local function drain()
        local unpack_args = table.unpack or unpack
        for _, job in ipairs(state.queue) do job[1](false, unpack_args(job, 2)) end
        state.queue = {}
    end
    return verifier, drain, function() return state.reverse_calls, state.forward_calls, #state.queue end,
        function() state.now = state.now + 7201 end
end

local ip, ua = "192.0.2.10", "Googlebot/2.1"
local verifier, drain, counts, expire = scenario()
assert(not verifier.is_verified(ip, ua))
assert(not verifier.is_verified(ip, ua))
local reverse, forward, timers = counts()
assert(reverse == 0 and forward == 0 and timers == 1, "DNS must stay off hot path; deduplicate")
drain()
assert(verifier.is_verified(ip, ua), "forward-confirmed Googlebot must be verified")
assert(not verifier.is_verified("192.0.2.11", ua), "never reuse identity across IPs")
assert(not verifier.is_verified(ip, "Bingbot"), "never reuse identity across providers")
expire()
assert(not verifier.is_verified(ip, ua), "expired identities must be reverified")

local failures = {
    {hostname = "evilgooglebot.com"},
    {hostname = "crawl.googlebot.com.evil.test"},
    {hostname = "unrelated.example.test"},
    {address = "192.0.2.11"},
    {reverse_failure = true},
    {forward_failure = true},
    {new_failure = true},
    {exception = true},
    {deadline = true},
    {timer_failure = true},
    {no_cache = true},
    {enabled = ""},
    {enabled = "bingbot"},
}
for _, options in ipairs(failures) do
    local check, run, call_counts = scenario(options)
    assert(not check.is_verified(ip, ua))
    run()
    assert(not check.is_verified(ip, ua), "failed verification must never grant trust")
    local lookups = call_counts()
    assert(lookups <= 1, "cache negative results")
end
for _, test in ipairs({
    {"Googlebot/2.1", "CRAWL.Example.Googlebot.COM.", ip, ip},
    {"Googlebot/2.1", "crawl.example.google.com", ip, ip},
    {"Bingbot/2.0", "msnbot.search.msn.com", ip, ip},
    {ua, "crawl.example.googlebot.com", "2001:db8::1", "2001:0db8:0:0:0:0:0:1"},
}) do
    local check, run = scenario({hostname = test[2], address = test[4]})
    assert(not check.is_verified(test[3], test[1]))
    run()
    assert(check.is_verified(test[3], test[1]))
end
for _, token in ipairs({"EvilGooglebot", "GooglebotFake", "NotBingbot", "Firefox"}) do
    local check, _, call_counts = scenario()
    assert(not check.is_verified(ip, token))
    local _, _, pending = call_counts()
    assert(pending == 0, "unrecognized tokens must not schedule DNS")
end
print("crawler identity: async DNS, FCrDNS, spoofing, failure, timeout, cache, config and IPv6 checks passed")
