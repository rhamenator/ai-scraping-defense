-- nginx/lua/detect_bot.lua
-- Basic bot detection script for NGINX

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
    "DotBot"
  }
  
  -- Function to check if a string contains any substring from a list
  local function contains_bad_bot(str, list)
    if not str then return false end
    local ua_lower = string.lower(str)
    for _, pattern in ipairs(list) do
      if string.find(ua_lower, string.lower(pattern), 1, true) then
        return true
      end
    end
    return false
  end
  
  -- Get request headers
  local headers = ngx.req.get_headers()
  local user_agent = headers["User-Agent"]
  local remote_addr = ngx.var.remote_addr
  
  -- 1. Check User-Agent against the bad bot list
  if contains_bad_bot(user_agent, bad_bots) then
    ngx.log(ngx.WARN, "[BOT DETECTED: UA Match] IP: ", remote_addr, ", UA: ", user_agent)
    -- Option 1: Block directly
    -- return ngx.exit(ngx.HTTP_FORBIDDEN) -- 403 Forbidden
  
    -- Option 2: Redirect to the tarpit API endpoint (configured in nginx.conf)
    return ngx.exec("/api/tarpit")
  end
  
  -- 2. Check for missing or minimal headers (basic heuristic)
  local accept_lang = headers["Accept-Language"]
  local sec_fetch_site = headers["Sec-Fetch-Site"]
  local accept_header = headers["Accept"]
  
  if not user_agent or user_agent == "" or not accept_lang or not sec_fetch_site or accept_header == "*/*" then
    ngx.log(ngx.WARN, "[BOT HEURISTIC: Missing Headers] IP: ", remote_addr, ", UA: ", user_agent)
    -- Redirect suspicious requests (potentially less aggressive bots) to the tarpit
    return ngx.exec("/api/tarpit")
  end
  
  -- 3. Add more checks here if needed (e.g., checking for specific header anomalies)
  
  -- If no checks trigger, allow the request to proceed normally
  return ngx.OK