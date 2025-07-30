using System;
using System.Configuration;
using System.Diagnostics;
using System.Runtime.Caching;
using System.Threading.Tasks;
using System.Web;
using StackExchange.Redis;

namespace AntiScrape.IIS
{
    public class DefenseModule : IHttpModule
    {
        private static ConnectionMultiplexer _redis;
        private static readonly MemoryCache BlockCache = MemoryCache.Default;
        private static readonly TraceSource Logger = new TraceSource("DefenseModule");

        public void Init(HttpApplication context)
        {
            context.BeginRequest += CheckRequestAsync;
        }

        private void EnsureRedis()
        {
            if (_redis != null) return;
            var host = ConfigurationManager.AppSettings["REDIS_HOST"] ?? "localhost";
            var port = ConfigurationManager.AppSettings["REDIS_PORT"] ?? "6379";
            _redis = ConnectionMultiplexer.Connect($"{host}:{port}");
        }

        private async void CheckRequestAsync(object sender, EventArgs e)
        {
            var app = (HttpApplication)sender;
            var ctx = app.Context;
            EnsureRedis();

            var ip = ctx.Request.UserHostAddress;
            var dbIndex = int.Parse(ConfigurationManager.AppSettings["REDIS_DB_BLOCKLIST"] ?? "2");
            var tenant = ConfigurationManager.AppSettings["TENANT_ID"] ?? "default";
            var db = _redis.GetDatabase(dbIndex);

            var cacheKey = $"block:{ip}";
            var cached = BlockCache.Get(cacheKey) as bool?;
            bool isBlocked;
            if (cached.HasValue)
            {
                isBlocked = cached.Value;
            }
            else
            {
                isBlocked = await db.KeyExistsAsync($"{tenant}:blocklist:ip:{ip}");
                BlockCache.Set(cacheKey, isBlocked, DateTimeOffset.UtcNow.AddMinutes(1));
            }

            if (isBlocked)
            {
                ctx.Response.StatusCode = 403;
                ctx.CompleteRequest();
                return;
            }

            if (await IsRateLimitedAsync(db, tenant, ip))
            {
                ctx.Response.StatusCode = 429;
                ctx.CompleteRequest();
                return;
            }

            if (string.IsNullOrEmpty(ctx.Request.UserAgent))
            {
                await EscalateAsync(ip, "MissingUA");
            }
            else if (ctx.Request.UserAgent.Contains("curl") || ctx.Request.UserAgent.Contains("wget"))
            {
                await EscalateAsync(ip, "BadUA");
                ctx.Response.StatusCode = 403;
                ctx.CompleteRequest();
                return;
            }

            if (string.IsNullOrEmpty(ctx.Request.Headers["Accept-Language"]))
            {
                await EscalateAsync(ip, "MissingAcceptLanguage");
            }
        }

        private async Task<bool> IsRateLimitedAsync(IDatabase db, string tenant, string ip)
        {
            var limitStr = ConfigurationManager.AppSettings["RATE_LIMIT_PER_MINUTE"] ?? "0";
            if (!int.TryParse(limitStr, out var limit) || limit <= 0)
            {
                return false;
            }

            var key = $"{tenant}:ratelimit:{ip}";
            var count = await db.StringIncrementAsync(key);
            if (count == 1)
            {
                await db.KeyExpireAsync(key, TimeSpan.FromMinutes(1));
            }
            if (count > limit)
            {
                await EscalateAsync(ip, "RateLimit");
                return true;
            }
            return false;
        }

        private async Task EscalateAsync(string ip, string reason)
        {
            var endpoint = ConfigurationManager.AppSettings["ESCALATION_ENDPOINT"];
            if (string.IsNullOrEmpty(endpoint)) return;
            using (var client = new System.Net.Http.HttpClient())
            {
                try
                {
                    await client.PostAsJsonAsync(endpoint, new { ip, reason });
                    Logger.TraceEvent(TraceEventType.Information, 0, $"Escalated {ip} for {reason}");
                }
                catch
                {
                    // fail open
                }
            }
        }

        public void Dispose() { }
    }
}
