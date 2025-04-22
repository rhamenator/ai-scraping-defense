-- anti_scrape/nginx/lua/detect_bot.lua
-- Bot detection script for NGINX, checks for bad bots and robots.txt violations.

-- List of known bad User-Agent substrings (case-insensitive)
local bad_bots = {
  "GPTBot", "CCBot", "ClaudeBot", "Google-Extended", "Bytespider",
  "PetalBot", "Scrapy", "python-requests", "curl", "wget", "AhrefsBot",
  "SemrushBot", "MJ12bot", "DotBot", "masscan", "zgrab", "nmap",
  "sqlmap", "nikto"
}

-- List of known benign crawlers (case-insensitive)
local benign_bots = {
  "googlebot", "adsbot-google", "apis-google", "mediapartners-google",
  "googlebot-image", "googlebot-news", "googlebot-video", "bingbot",
  "adidxbot", "bingpreview", "msnbot", "duckduckbot", "baiduspider",
  "yandexbot", "yandeximages", "slurp", "facebookexternalhit", "facebot",
  "linkedinbot", "twitterbot", "applebot"
}

-- Simple list of disallowed paths for *all* bots (load from config/file ideally)
-- For demonstration, hardcoding a few common sensitive paths.
-- IMPORTANT: This is a simplified approach. Full robots.txt parsing is complex in Lua.
local disallowed_paths = {
  "/admin/",
  "/api/",      -- If your real API shouldn't be crawled
  "/config/",
  "/models/",
  "/secrets/",
  "/data/",
  "/cgi-bin/",
  "/wp-admin/",
  "/xmlrpc.php"
  -- Add other critical paths that NO bot should access
}

-- Function to check if a string contains any substring from a list (case-insensitive)
local function contains_string(str, list)
  if not str then return false end
  local str_lower = string.lower(str)
  for _, pattern in ipairs(list) do
    if string.find(str_lower, string.lower(pattern), 1, true) then
      return true, pattern -- Return true and the matched pattern
    end
  end
  return false
end

-- Function to check if a path starts with any disallowed prefix
local function is_path_disallowed(path, rules)
  if not path or not rules then return false end
  for _, disallowed in ipairs(rules) do
    -- Check if the path starts with the disallowed prefix
    if string.sub(path, 1, string.len(disallowed)) == disallowed then
      return true
    end
  end
  return false
end

-- Get request details
local headers = ngx.req.get_headers()
local user_agent = headers["User-Agent"]
local remote_addr = ngx.var.remote_addr
local request_method = ngx.req.get_method()
local request_uri = ngx.var.request_uri or "/" -- Ensure URI is never nil

ngx.log(ngx.DEBUG, "[BOT CHECK] IP: ", remote_addr, ", UA: ", user_agent, ", URI: ", request_uri)

-- 1. Check if it's a known benign bot
local is_benign, benign_pattern = contains_string(user_agent, benign_bots)

if is_benign then
  -- 2. If benign, check if it's accessing a disallowed path
  if is_path_disallowed(request_uri, disallowed_paths) then
    ngx.log(ngx.WARN, "[TAR PIT TRIGGER] Benign bot (", benign_pattern, ") accessed disallowed path: ", request_uri, " IP: ", remote_addr)
    return ngx.exec("/api/tarpit") -- Send rule-violating benign bots to tarpit
  else
    ngx.log(ngx.INFO, "[BENIGN BOT ALLOWED] IP: ", remote_addr, ", UA: ", user_agent, " (Matched: ", benign_pattern, ")")
    return -- Allow request (ngx.OK is implicit)
  end
end

-- 3. If not benign, apply heuristic checks for suspicious activity
local suspicion_score = 0
local reasons = {}

local is_bad_ua, bad_pattern = contains_string(user_agent, bad_bots)
if is_bad_ua then
  suspicion_score = suspicion_score + 0.8
  table.insert(reasons, "KnownBadUA("..bad_pattern..")")
end

local accept_lang = headers["Accept-Language"]
local sec_fetch_site = headers["Sec-Fetch-Site"]
local accept_header = headers["Accept"]
local referer_header = headers["Referer"]

if not user_agent or user_agent == "" then
  suspicion_score = suspicion_score + 0.4
  table.insert(reasons, "MissingUA")
end

if not accept_lang then
  suspicion_score = suspicion_score + 0.2
  table.insert(reasons, "MissingAcceptLang")
end

if not sec_fetch_site then -- Don't check if known bad UA already penalized
  suspicion_score = suspicion_score + 0.15
  table.insert(reasons, "MissingSecFetchSite")
end

if accept_header == "*/*" then
  suspicion_score = suspicion_score + 0.1
  table.insert(reasons, "AcceptWildcard")
end

if not referer_header and request_uri ~= "/" and not string.match(request_uri, "%.(css|js|png|jpg|jpeg|gif|woff|woff2|ico)$") then
    suspicion_score = suspicion_score + 0.05
    table.insert(reasons, "MissingRefererNonAsset")
end

if request_method ~= "GET" and request_method ~= "POST" and request_method ~= "HEAD" and request_method ~= "OPTIONS" then
    suspicion_score = suspicion_score + 0.2
    table.insert(reasons, "UncommonMethod("..request_method..")")
end

-- 4. Decision for non-benign bots
if suspicion_score >= 0.7 then -- Adjust threshold as needed
  local reason_str = table.concat(reasons, ",")
  ngx.log(ngx.WARN, "[TAR PIT TRIGGER: High Heuristic Score] Score: ", suspicion_score, ", IP: ", remote_addr, ", UA: ", user_agent, ", Reasons: ", reason_str)
  return ngx.exec("/api/tarpit")
else
  -- Request passed bot checks or low suspicion score
  ngx.log(ngx.DEBUG, "[REQUEST ALLOWED] Score: ", string.format("%.2f", suspicion_score), ", IP: ", remote_addr, ", UA: ", user_agent)
  return -- Allow request
end