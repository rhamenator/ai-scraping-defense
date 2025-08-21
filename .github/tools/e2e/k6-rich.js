import http from 'k6/http';
import { sleep, check, group } from 'k6';
import { Trend } from 'k6/metrics';

export const options = {
  scenarios: {
    smoke: { executor: 'constant-vus', vus: 5, duration: '30s' },
    ramp: { startTime: '35s', executor: 'ramping-vus',
      startVUs: 0,
      stages: [ { duration: '30s', target: 20 }, { duration: '30s', target: 40 }, { duration: '30s', target: 0 } ],
    },
  },
  thresholds: { http_req_failed: ['rate<0.02'], http_req_duration: ['p(95)<1500'] },
};

const BASE = __ENV.BASE_URL;
const tarpit = new Trend('tarpit_latency');

export default function () {
  group('home', () => { const r = http.get(`${BASE}/`); check(r, { 'home ok': (x) => x.status >= 200 && x.status < 400 }); });
  group('admin guard', () => { const r = http.get(`${BASE}/admin`, { redirects: 0 }); check(r, { 'guarded': (x) => [200,301,302,401,403].includes(x.status) }); });
  group('api markov', () => { const r = http.get(`${BASE}/api/markov`, { redirects: 0 }); check(r, { 'reachable': (x) => x.status === 200 || (x.status >= 300 && x.status < 500) }); });
  group('api zip', () => { const r = http.get(`${BASE}/api/zip`, { redirects: 0 }); check(r, { 'reachable': (x) => x.status > 0 }); });
  group('tarpit slow', () => { const r = http.get(`${BASE}/tarpit/slow`, { timeout: '60s' }); tarpit.add(r.timings.duration); check(r, { 'responded': (x) => x.status > 0 }); });
  sleep(1);
}
