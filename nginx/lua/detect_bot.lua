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

local crawler_identity = require "crawler_identity"
local blocklist = require "blocklist"

-- Path to the robots.txt file mounted in the Docker container
-- (as per docker-compose.yml: ./config/robots.txt:/etc/nginx/robots.txt:ro)
local robots_txt_path = "/etc/nginx/robots.txt"
local robots_policy = require "robots_policy"
local robots_groups = {}

-- Read the mounted policy; unreadable policy must not invent violations.
local function load_robots_rules()
    local file = io.open(robots_txt_path, "r")
    if not file then
        ngx.log(ngx.ERR, "detect_bot: Could not open robots.txt at ", robots_txt_path)
        return
    end
    robots_groups = robots_policy.parse(file:read("*a"))
    file:close()
end
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
math.randomseed(ngx.now() * 1000)
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

-- 0. A blocklisted address is refused first. `location /` has its own access handler, which replaces
-- the server-level check_blocklist.lua, so the check must run here as well.
blocklist.check()

-- 1. Enforce robots.txt for every client before UA exemptions or heuristics.
if robots_policy.is_disallowed(robots_groups, request_uri, user_agent) then
  ngx.log(
    ngx.WARN,
    "[TAR PIT TRIGGER] Client accessed disallowed path: ",
    sanitize_for_log(request_uri),
    " IP: ",
    sanitize_for_log(remote_addr)
  )
  return ngx.exec("/api/tarpit")
end

-- 2. Check if it's a known benign bot on a permitted path.
local is_bad_ua, bad_ua_pattern = contains_string(user_agent, bad_bots)
local is_benign = crawler_identity.is_verified(remote_addr, user_agent)
if is_benign and not is_bad_ua then
  ngx.log(
    ngx.INFO,
    "[BENIGN BOT ALLOWED] IP: ",
    remote_addr,
    ", UA: ",
    user_agent,
    " (DNS verified)"
  )
  local chosen = pick_backend()
  if chosen then
    ngx.var.lua_proxy_pass_upstream = chosen
    return ngx.OK -- Signal to Nginx to use this upstream
  end
  return -- Allow request (ngx.OK is implicit if no upstream set by Lua)
end

-- 3. If not benign, apply heuristic checks for suspicious activity
local suspicion_score = 0
local reasons = {}

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
  -- The tarpit records the request and forwards it to the escalation engine.
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
