-- luacheck: globals ngx
-- anti_scrape/nginx/lua/detect_bot.lua
-- Bot detection script for NGINX, checks for bad bots and robots.txt violations.
-- This version is intended for Docker Compose and reads robots.txt from a mounted file.

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

-- Path to the robots.txt file mounted in the Docker container
-- (as per docker-compose.yml: ./config/robots.txt:/etc/nginx/robots.txt:ro)
local robots_txt_path = "/etc/nginx/robots.txt"
local dynamic_disallowed_paths = {}

-- Function to load and parse robots.txt for 'User-agent: *' disallow rules
local function load_robots_rules()
    local file = io.open(robots_txt_path, "r")
    if not file then
        ngx.log(ngx.ERR, "detect_bot: Could not open robots.txt at ", robots_txt_path)
        return
    end

    local current_ua_is_star = false
    for line in file:lines() do
        line = string.lower(string.gsub(line, "^%s*(.-)%s*$", "%1")) -- Trim and lowercase

        if string.match(line, "^user%-agent:%s*%*") then
            current_ua_is_star = true
        elseif string.match(line, "^user%-agent:") then
            -- A new user-agent directive that is not '*' resets the star flag
            current_ua_is_star = false
        end

        if current_ua_is_star then
            local disallow_match = string.match(line, "^disallow:%s*(.+)")
            -- Add rule if it's not empty and not just "/" (which means disallow nothing specific under '*')
            if disallow_match and disallow_match ~= "" and disallow_match ~= "/" then
                table.insert(dynamic_disallowed_paths, disallow_match)
            end
        end
    end
    file:close()

    if #dynamic_disallowed_paths > 0 then
        ngx.log(
            ngx.INFO,
            "detect_bot: Loaded ",
            #dynamic_disallowed_paths,
            " disallow rules for * from ",
            robots_txt_path
        )
    else
        ngx.log(
            ngx.WARN,
            "detect_bot: No disallow rules for * found or loaded from ",
            robots_txt_path
        )
    end
end

-- Load rules when Lua module is initialized (Nginx worker starts)
load_robots_rules()

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
local function is_path_disallowed(path_to_check, rules)
  if not path_to_check or not rules or #rules == 0 then return false end
  for _, disallowed_rule in ipairs(rules) do
    -- Ensure the disallowed_rule is not empty before checking
    if disallowed_rule ~= "" and string.sub(path_to_check, 1, string.len(disallowed_rule)) == disallowed_rule then
      return true
    end
  end
  return false
end

-- Sanitize strings before logging to mitigate log injection
local function sanitize_for_log(value)
  if not value then return "-" end
  value = tostring(value)
  value = string.gsub(value, "[\r\n]", "")
  return value
end

-- Get request details
local headers = ngx.req.get_headers()
local user_agent = headers["User-Agent"]
local remote_addr = ngx.var.remote_addr
local request_method = ngx.req.get_method()
local request_uri = ngx.var.request_uri or "/" -- Ensure URI is never nil
local fingerprint_id = ngx.var.cookie_fp_id
local ai_service_host = os.getenv("AI_SERVICE_HOST") or "ai_service"
local ai_service_port = os.getenv("AI_SERVICE_PORT") or "8000"
local ai_service_scheme = os.getenv("AI_SERVICE_SCHEME") or "http"
local ai_service_url = ai_service_scheme .. "://" .. ai_service_host .. ":" .. ai_service_port .. "/webhook"
local http = require "resty.http"
local cjson = require "cjson.safe"
math.randomseed(ngx.now() * 1000)

local function forward_metadata(reason)
  local payload = {
    event_type = "suspicious_request",
    reason = reason,
    timestamp_utc = ngx.utctime(),
    details = {
      ip = remote_addr,
      user_agent = user_agent,
      path = request_uri,
      method = request_method,
      fingerprint_id = fingerprint_id,
      headers = headers,
    }
  }
  local httpc = http.new()
  httpc:set_timeout(1000)
  local res, err = httpc:request_uri(ai_service_url, {
    method = "POST",
    body = cjson.encode(payload),
    headers = { ["Content-Type"] = "application/json" },
  })
  if not res then
    ngx.log(ngx.ERR, "detect_bot: failed to forward metadata: ", err)
  end
end
local backend_hosts_env = os.getenv("REAL_BACKEND_HOSTS")
local real_backend_host = os.getenv("REAL_BACKEND_HOST")
local backend_hosts = {}
if backend_hosts_env and backend_hosts_env ~= "" then
  for host in string.gmatch(backend_hosts_env, "[^,]+") do
    table.insert(backend_hosts, host)
  end
elseif real_backend_host and real_backend_host ~= "" then
  table.insert(backend_hosts, real_backend_host)
end

local function pick_backend()
  if #backend_hosts == 0 then
    return nil
  end
  local idx = math.random(#backend_hosts)
  return backend_hosts[idx]
end

ngx.log(
  ngx.DEBUG,
  "[BOT CHECK] IP: ",
  sanitize_for_log(remote_addr),
  ", UA: ",
  sanitize_for_log(user_agent),
  ", URI: ",
  sanitize_for_log(request_uri)
)

-- 1. Check if it's a known benign bot
local is_benign, benign_pattern = contains_string(user_agent, benign_bots)

if is_benign then
  -- 2. If benign, check if it's accessing a disallowed path from loaded robots.txt
  if is_path_disallowed(request_uri, dynamic_disallowed_paths) then
    ngx.log(
      ngx.WARN,
      "[TAR PIT TRIGGER] Benign bot (",
      benign_pattern,
      ") accessed disallowed path: ",
      request_uri,
      " IP: ",
      remote_addr
    )
    return ngx.exec("/api/tarpit") -- Send rule-violating benign bots to tarpit
  else
    ngx.log(
      ngx.INFO,
      "[BENIGN BOT ALLOWED] IP: ",
      remote_addr,
      ", UA: ",
      user_agent,
      " (Matched: ",
      benign_pattern,
      ")"
    )
    local chosen = pick_backend()
    if chosen then
        ngx.var.lua_proxy_pass_upstream = chosen
        return ngx.OK -- Signal to Nginx to use this upstream
    end
    return -- Allow request (ngx.OK is implicit if no upstream set by Lua)
  end
end

-- 3. If not benign, apply heuristic checks for suspicious activity
local suspicion_score = 0
local reasons = {}

local is_bad_ua, bad_ua_pattern = contains_string(user_agent, bad_bots)
if is_bad_ua then
  suspicion_score = suspicion_score + 0.8
  table.insert(reasons, "KnownBadUA("..bad_ua_pattern..")")
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

if not sec_fetch_site and not is_bad_ua then -- Don't penalize if already known bad UA
  suspicion_score = suspicion_score + 0.15
  table.insert(reasons, "MissingSecFetchSite")
end

if accept_header and string.lower(accept_header) == "*/*" then -- Check if accept_header exists
  suspicion_score = suspicion_score + 0.1
  table.insert(reasons, "AcceptWildcard")
end

if not referer_header
  and request_uri ~= "/"
  and not string.match(request_uri, "%.(css|js|png|jpg|jpeg|gif|woff|woff2|ico)$")
then
  suspicion_score = suspicion_score + 0.05
  table.insert(reasons, "MissingRefererNonAsset")
end

if request_method ~= "GET"
  and request_method ~= "POST"
  and request_method ~= "HEAD"
  and request_method ~= "OPTIONS"
then
  suspicion_score = suspicion_score + 0.2
  table.insert(reasons, "UncommonMethod(" .. request_method .. ")")
end

-- 4. Decision for non-benign bots
if suspicion_score >= 0.7 then -- Adjust threshold as needed
  local reason_str = table.concat(reasons, ",")
  ngx.log(
    ngx.WARN,
    "[TAR PIT TRIGGER: High Heuristic Score] Score: ",
    string.format("%.2f", suspicion_score),
    ", IP: ",
    remote_addr,
    ", UA: ",
    user_agent,
    ", Reasons: ",
    reason_str
  )
  forward_metadata(reason_str)
  return ngx.exec("/api/tarpit")
else
  -- Request passed bot checks or low suspicion score
  ngx.log(
    ngx.DEBUG,
    "[REQUEST ALLOWED] Score: ",
    string.format("%.2f", suspicion_score),
    ", IP: ",
    remote_addr,
    ", UA: ",
    user_agent
  )
  local chosen = pick_backend()
  if chosen then
    ngx.var.lua_proxy_pass_upstream = chosen
    return ngx.OK -- Signal to Nginx to use this upstream
  end
  return -- Allow request
end
