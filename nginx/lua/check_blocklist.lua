-- nginx/lua/check_blocklist.lua
-- Checks the connecting IP against a Redis blocklist set.

-- Redis connection details (Read from nginx.conf ideally, or hardcode carefully)
-- Note: Using environment variables directly in Lua requires ngx_http_lua_module built with specific options or helper modules.
-- It's often simpler to pass them via nginx.conf variables if needed, or configure here.
local redis_host = os.getenv("REDIS_HOST") or "redis"
local redis_port = tonumber(os.getenv("REDIS_PORT")) or 6379
local redis_db_blocklist = tonumber(os.getenv("REDIS_DB_BLOCKLIST")) or 2
local redis_blocklist_key = "blocklist:ip"
local redis_timeout_ms = 200 -- Connection/read timeout in milliseconds

-- Get the remote IP address
local remote_addr = ngx.var.remote_addr
if not remote_addr then
  ngx.log(ngx.WARN, "check_blocklist: Could not get remote_addr")
  return -- Allow request if IP cannot be determined
end

-- Load the Redis library
local redis = require "resty.redis"
local red = redis:new()

-- Set connection timeout
red:set_timeout(redis_timeout_ms)

-- Connect to Redis
local ok, err = red:connect(redis_host, redis_port)
if not ok then
  ngx.log(ngx.ERR, "check_blocklist: Failed to connect to Redis at ", redis_host, ":", redis_port, ": ", err)
  -- Fail open (allow request) if Redis connection fails
  return
end

-- Optional: Authenticate if Redis requires a password
-- local redis_password = os.getenv("REDIS_PASSWORD")
-- if redis_password then
--   local auth_ok, auth_err = red:auth(redis_password)
--   if not auth_ok then
--     ngx.log(ngx.ERR, "check_blocklist: Redis authentication failed: ", auth_err)
--     red:close()
--     return -- Fail open
--   end
-- end

-- Select the correct database
local select_ok, select_err = red:select(redis_db_blocklist)
if not select_ok then
    ngx.log(ngx.ERR, "check_blocklist: Failed to select Redis DB ", redis_db_blocklist, ": ", select_err)
    red:close()
    return -- Fail open
end

-- Check if the IP exists in the blocklist set (SISMEMBER command)
local is_member, err = red:sismember(redis_blocklist_key, remote_addr)
if err then
  ngx.log(ngx.ERR, "check_blocklist: Failed to query Redis (SISMEMBER ", redis_blocklist_key, ") for IP ", remote_addr, ": ", err)
  -- Fail open on Redis query error
  red:close()
  return
end

-- IMPORTANT: Close the Redis connection to return it to the pool
local close_ok, close_err = red:set_keepalive(0, 100) -- 0 timeout, 100 pool size
if not close_ok then
    ngx.log(ngx.WARN,"check_blocklist: Failed to set Redis keepalive: ", close_err)
    -- Attempt to close explicitly if keepalive fails
    red:close()
end

-- If IP is a member of the blocklist set (is_member == 1)
if is_member == 1 then
  ngx.log(ngx.WARN, "check_blocklist: Blocking IP ", remote_addr, " found in Redis set '", redis_blocklist_key, "'")
  -- Block the request
  return ngx.exit(ngx.HTTP_FORBIDDEN) -- 403 Forbidden
end

-- If IP is not in the blocklist (is_member == 0 or nil), allow the request to proceed
-- ngx.log(ngx.INFO, "check_blocklist: IP ", remote_addr, " not found in blocklist.") -- Debug log
return