-- RFC 9309 rule parsing/matching. UA group selection is policy, not identity trust.
local M = {}

local function normalize(value, pattern)
    local result, i = {}, 1
    while i <= #value do
        local ch = value:sub(i, i)
        local hex = value:sub(i + 1, i + 2)
        if ch == "%" and #hex == 2 and hex:match("^%x%x$") then
            local byte = tonumber(hex, 16)
            local decoded = string.char(byte)
            if decoded:match("^[A-Za-z0-9._~%-]$") then
                result[#result + 1] = decoded
            else
                result[#result + 1] = "%" .. hex:upper()
            end
            i = i + 3
        else
            local byte = ch:byte()
            if byte > 127 or byte <= 32 or ch == "$" or (ch == "*" and not pattern) then
                result[#result + 1] = string.format("%%%02X", byte)
            else
                result[#result + 1] = ch
            end
            i = i + 1
        end
    end
    return table.concat(result)
end

local function build_rule(key, value)
    if value == "" or (value:sub(1, 1) ~= "/" and value:sub(1, 1) ~= "*") then return nil end
    local anchored = value:sub(-1) == "$"
    if anchored then value = value:sub(1, -2) end
    value = normalize(value, true)
    local octets = value:gsub("%%(%x%x)", "X"):gsub("%*", "")
    return {
        -- RFC 9309: the longest pattern is the most specific. The "$" is part
        -- of the pattern, so an anchored rule outranks the same text without it.
        pattern = value, anchored = anchored, length = #octets + (anchored and 1 or 0),
        allow = key == "allow",
    }
end

local function start_group(groups, current, value)
    value = value:lower()
    if value ~= "*" and not value:match("^[a-z_%-]+$") then return current end
    if not current or current.has_rules then
        current = {agents = {}, rules = {}}
        groups[#groups + 1] = current
    end
    current.agents[#current.agents + 1] = value
    return current
end

function M.parse(text)
    local groups, current = {}, nil
    -- A UTF-8 BOM is not part of the first directive.
    text = text:gsub("^\239\187\191", "")
    for line in (text .. "\n"):gmatch("([^\r\n]*)[\r\n]") do
        line = line:gsub("#.*$", "")
        local key, value = line:match("^%s*([%a%-]+)%s*:%s*(.-)%s*$")
        key = key and key:lower()
        if key == "user-agent" then
            current = start_group(groups, current, value)
        elseif current and (key == "allow" or key == "disallow") then
            current.has_rules = true
            local rule = build_rule(key, value)
            if rule then current.rules[#current.rules + 1] = rule end
        end
    end
    return groups
end

-- Greedy wildcard matching avoids recursive pattern backtracking.
local function matches(path, rule)
    local pattern = rule.pattern .. (rule.anchored and "" or "*")
    local i, j, star, resume = 1, 1, nil, nil
    while i <= #path do
        local ch = pattern:sub(j, j)
        if ch == "*" then
            star, resume, j = j, i, j + 1
        elseif ch ~= "" and ch == path:sub(i, i) then
            i, j = i + 1, j + 1
        elseif star then
            resume = resume + 1
            i, j = resume, star + 1
        else
            return false
        end
    end
    while pattern:sub(j, j) == "*" do j = j + 1 end
    return j > #pattern
end

local function agent_selected(ua, agent)
    return ua:find("%f[%a_%-]" .. agent:gsub("%-", "%%-") .. "%f[^%a_%-]") ~= nil
end

-- Groups naming the client win; otherwise the "*" groups apply.
local function select_groups(groups, ua)
    local specific, wildcard = {}, {}
    for _, group in ipairs(groups) do
        local selected, fallback = false, false
        for _, agent in ipairs(group.agents) do
            if agent == "*" then
                fallback = true
            elseif agent_selected(ua, agent) then
                selected = true
            end
        end
        if selected then specific[#specific + 1] = group end
        if fallback then wildcard[#wildcard + 1] = group end
    end
    return #specific > 0 and specific or wildcard
end

local function verdict_allows(groups, path)
    local best, allowed = -1, true
    for _, group in ipairs(groups) do
        for _, rule in ipairs(group.rules) do
            if rule.length >= best and matches(path, rule) then
                if rule.length > best then allowed = rule.allow else allowed = allowed or rule.allow end
                best = rule.length
            end
        end
    end
    return allowed
end

function M.is_disallowed(groups, path, ua)
    if not path then return false end
    path = normalize(path, false)
    if path == "/robots.txt" or path:sub(1, 12) == "/robots.txt?" then return false end
    return not verdict_allows(select_groups(groups, (ua or ""):lower()), path)
end

return M
