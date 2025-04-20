-- nginx/lua/detect_bot.lua
-- Basic bot detection script for NGINX - Enhanced Heuristics

-- List of known bad User-Agent substrings (add more as needed)
local bad_bots = {
  "GPTBot",
  "CCBot",
  "ClaudeBot",
  "Google-Extended",
  "Bytespider",
  "PetalBot",
  "Scrapy",
  "python-requests",
  "curl",
  "wget",
  "AhrefsBot",
  "SemrushBot",
  "MJ12bot",
  "DotBot",
  "masscan", -- Network scanners
  "zgrab",
  "nmap",
  "sqlmap", -- Common attack tools
  "nikto"
}

-- List of known benign crawlers (to avoid accidentally blocking/tarpitting)
local benign_bots = {
  "googlebot",
  "adsbot-google",
  "apis-google",
  "mediapartners-google",
  "googlebot-image",
  "googlebot-news",
  "googlebot-video",
  "bingbot",
  "adidxbot",
  "bingpreview",
  "msnbot",
  "duckduckbot",
  "baiduspider",
  "yandexbot",
  "yandeximages",
  "slurp", -- Yahoo
  "facebookexternalhit",
  "facebot",
  "linkedinbot",
  "twitterbot",
  "applebot"
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

-- Get request headers and variables
local headers = ngx.req.get_headers()
local user_agent = headers["User-Agent"]
local remote_addr = ngx.var.remote_addr
local request_method = ngx.req.get_method()
local request_uri = ngx.var.request_uri

--[[
Early Exit for Benign Bots:
Check against the benign list first. If it matches, allow the request
unless they are accessing sensitive paths (which they shouldn't according to robots.txt).
Note: Blocklist check in check_blocklist.lua runs *before* this script.
--]]
local is_benign, benign_pattern = contains_string(user_agent, benign_bots)
if is_benign then
  -- Optional: Add checks here if benign bots access disallowed paths frequently,
  -- but primarily rely on robots.txt and backend logic for this.
  ngx.log(ngx.INFO, "[BENIGN BOT ALLOWED] IP: ", remote_addr, ", UA: ", user_agent, " (Matched: ", benign_pattern, ")")
  return -- ngx.OK is implicit if nothing else happens
end

--[[
Detection Logic: Apply checks sequentially or combine scores
--]]
local suspicion_score = 0
local reasons = {}

-- 1. Check User-Agent against the bad bot list
local is_bad_ua, bad_pattern = contains_string(user_agent, bad_bots)
if is_bad_ua then
  suspicion_score = suspicion_score + 0.8 -- High score for known bad UAs
  table.insert(reasons, "KnownBadUA("..bad_pattern..")")
end

-- 2. Check for missing or suspicious headers
local accept_lang = headers["Accept-Language"]
local sec_fetch_site = headers["Sec-Fetch-Site"] -- Modern browsers usually send this
local sec_fetch_user = headers["Sec-Fetch-User"]
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

if not sec_fetch_site and not is_bad_ua then -- Don't penalize twice if already known bad
  suspicion_score = suspicion_score + 0.15
  table.insert(reasons, "MissingSecFetchSite")
end

if accept_header == "*/*" then
  suspicion_score = suspicion_score + 0.1
  table.insert(reasons, "AcceptWildcard")
end

-- Heuristic: Missing referer on non-root paths (less reliable, lower score)
if not referer_header and request_uri ~= "/" and not string.match(request_uri, "%.(css|js|png|jpg|jpeg|gif|woff|woff2|ico)$") then
    suspicion_score = suspicion_score + 0.05
    table.insert(reasons, "MissingRefererNonAsset")
end

-- Heuristic: Unusual request methods (less common for normal browsing)
if request_method ~= "GET" and request_method ~= "POST" and request_method ~= "HEAD" and request_method ~= "OPTIONS" then
    suspicion_score = suspicion_score + 0.2
    table.insert(reasons, "UncommonMethod("..request_method..")")
end

-- 3. Add more checks here if needed
-- Example: Check for specific patterns in query parameters, paths etc.
-- if string.find(request_uri, "some_exploit_pattern", 1, true) then
--   suspicion_score = suspicion_score + 0.9
--   table.insert(reasons, "ExploitPatternURI")
-- end

-- Decision based on score
if suspicion_score >= 0.7 then -- Adjust threshold as needed
  local reason_str = table.concat(reasons, ",")
  ngx.log(ngx.WARN, "[BOT DETECTED: High Heuristic Score] Score: ", suspicion_score, ", IP: ", remote_addr, ", UA: ", user_agent, ", Reasons: ", reason_str)
  -- Redirect to the tarpit API endpoint (configured in nginx.conf)
  return ngx.exec("/api/tarpit")
end

-- If suspicion score is low, allow the request to proceed normally
ngx.log(ngx.DEBUG, "[BOT CHECK PASSED] Score: ", suspicion_score, ", IP: ", remote_addr, ", UA: ", user_agent) -- Use DEBUG level
return -- ngx.OK is implicit if nothing else happens
