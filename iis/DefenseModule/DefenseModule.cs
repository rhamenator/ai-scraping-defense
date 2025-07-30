using System;
using System.Configuration;
using System.Threading.Tasks;
using System.Web;
using StackExchange.Redis;

namespace AntiScrape.IIS
{
    public class DefenseModule : IHttpModule
    {
        private static ConnectionMultiplexer _redis;

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
            var key = $"{tenant}:blocklist:ip:{ip}";
            if (await db.KeyExistsAsync(key))
            {
                ctx.Response.StatusCode = 403;
                ctx.CompleteRequest();
                return;
            }

            if (string.IsNullOrEmpty(ctx.Request.UserAgent))
            {
                await EscalateAsync(ip, "MissingUA");
            }
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
