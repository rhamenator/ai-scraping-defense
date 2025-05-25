-- nginx/lua/check_blocklist.lua
-- Checks the connecting IP against a Redis blocklist.
-- IPs are stored as individual keys with a TTL (e.g., "blocklist:ip:1.2.3.4").

-- Redis connection details
local redis_host = os.getenv("REDIS_HOST") or "redis"
local redis_port = tonumber(os.getenv("REDIS_PORT")) or 6379
local redis_db_blocklist = tonumber(os.getenv("REDIS_DB_BLOCKLIST")) or 2
local redis_blocklist_key_prefix = "blocklist:ip:" -- Prefix for individual IP keys
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
-- local redis_password = os.getenv("REDIS_PASSWORD") -- Or read from a secret file if possible
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

-- Check if the IP key exists
local blocklist_ip_key = redis_blocklist_key_prefix .. remote_addr -- Construct the specific IP key
local exists, err = red:exists(blocklist_ip_key)

if err then
  ngx.log(ngx.ERR, "check_blocklist: Failed to query Redis (EXISTS ", blocklist_ip_key, ") for IP ", remote_addr, ": ", err)
  -- Fail open on Redis query error
  red:close()
  return
end

-- IMPORTANT: Close the Redis connection to return it to the pool or close it
local close_ok, close_err = red:set_keepalive(0, 100) -- 0 timeout, 100 pool size (for keepalive)
if not close_ok then
    ngx.log(ngx.WARN,"check_blocklist: Failed to set Redis keepalive: ", close_err)
    -- Attempt to close explicitly if keepalive fails
    red:close()
end

-- If IP key exists (exists == 1), deny access
if exists == 1 then
  ngx.log(ngx.WARN, "check_blocklist: Blocking IP ", remote_addr, " found in Redis (Key: '", blocklist_ip_key, "')")
  -- Block the request
  return ngx.exit(ngx.HTTP_FORBIDDEN) -- 403 Forbidden
end

-- If IP key does not exist (exists == 0 or nil), allow the request to proceed
-- ngx.log(ngx.DEBUG, "check_blocklist: IP ", remote_addr, " not found in blocklist (Key: '", blocklist_ip_key, "'). Allowing request.")
return
