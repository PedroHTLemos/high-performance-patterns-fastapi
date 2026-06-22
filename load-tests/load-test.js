import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Counter } from "k6/metrics";
import exec from "k6/execution";

// Métricas customizadas, separadas por status de cache
const cacheHitLatency = new Trend("cache_hit_latency_ms");
const cacheHitAfterLockWaitLatency = new Trend("cache_hit_after_lock_wait_latency_ms");
const cacheMissLatency = new Trend("cache_miss_latency_ms");
const rateLimitedCount = new Counter("rate_limited_429s");

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

// Username fixo: garante que warm-up e leitura subsequente caiam na mesma chave de cache
const CACHE_USER = "octocat";

// Lista de usuários reais do GitHub para gerar MISS sem reciclar o mesmo cache
const SAMPLE_USERS = [
  "torvalds", "gaearon", "sindresorhus", "yyx990803", "tj",
  "addyosmani", "kentcdodds", "wesbos", "getify", "substack",
];

// Usuários exclusivos do cenário isolado de MISS (não compartilhados com
// os outros cenários, pra evitar qualquer cache aquecido por outro teste).
const MISS_TEST_USERS = [
  "mojombo", "defunkt", "pjhyett", "wycats", "ezmobius",
  "ivey", "evanphx", "vanpelt", "wayneeseguin", "brynary",
];

export const options = {
  scenarios: {
    // Cenário 0: mede MISS puro, sequencial (1 VU), sem concorrência,
    // pra não disparar o lock-wait/stampede. Cada iteração usa um
    // username único e recém-purgado em setup().
    cache_miss_isolated: {
      executor: "shared-iterations",
      vus: 1,
      iterations: MISS_TEST_USERS.length,
      exec: "missOnly",
      startTime: "0s",
      maxDuration: "30s",
    },
    // Cenário 1: mede latência de cache HIT em alta concorrência,
    // após warm-up manual (ver instruções de execução).
    cache_hit_benchmark: {
      executor: "constant-vus",
      vus: 20,
      duration: "20s",
      exec: "hitCache",
      startTime: "10s",
    },
    // Cenário 2: força MISS constante usando usernames distintos por
    // iteração, e mede a latência de origin + comportamento de rate limit.
    cache_miss_and_rate_limit: {
      executor: "constant-vus",
      vus: 10,
      duration: "20s",
      exec: "missCacheAndRateLimit",
      startTime: "35s",
    },
  },
  thresholds: {
    "cache_hit_latency_ms": ["p(95)<50"], // HIT imediato apenas
    "checks": ["rate>0.95"],
  },
};

// Trata 200, 404 e 429 como "esperados" para as métricas HTTP nativas do k6
// (caso contrário, todo 429 aparece como http_req_failed, o que é ruído aqui).
http.setResponseCallback(http.expectedStatuses(200, 404, 429));

// Roda uma vez antes do teste: purga o cache de todos os usuários envolvidos,
// garantindo que as primeiras leituras de cada um sejam MISS reais (origin),
// e não restos de uma execução anterior do teste.
export function setup() {
  const usersToReset = [CACHE_USER, ...SAMPLE_USERS, ...MISS_TEST_USERS];
  for (const user of usersToReset) {
    http.del(`${BASE_URL}/github/users/${user}/cache`, null, {
      headers: { "X-API-Key": __ENV.API_KEY || "" },
    });
  }
}

// MISS puro: 1 VU, sequencial, sem concorrência. Cada username já foi
// purgado em setup() e nenhum outro cenário toca nesses usernames, então
// toda leitura aqui é garantidamente uma chamada real à origin.
export function missOnly() {
  const user = MISS_TEST_USERS[(exec.scenario.iterationInTest) % MISS_TEST_USERS.length];
  const res = http.get(`${BASE_URL}/github/users/${user}`, {
    headers: { "X-API-Key": __ENV.API_KEY || "" },
  });
  const cacheStatus = res.headers["X-Cache"];

  check(res, { "status is 200": (r) => r.status === 200 });

  if (res.status === 200 && cacheStatus === "MISS") {
    cacheMissLatency.add(res.timings.duration);
  }
}

export function hitCache() {
  const res = http.get(`${BASE_URL}/github/users/${CACHE_USER}`, {
    headers: { "X-API-Key": __ENV.API_KEY || "" },
  });
  const cacheStatus = res.headers["X-Cache"];

  check(res, {
    "status is 200 or 429": (r) => r.status === 200 || r.status === 429,
  });

  if (res.status === 200 && cacheStatus === "HIT") {
    let waitedForLock = false;
    try {
      waitedForLock = JSON.parse(res.body).waited_for_lock === true;
    } catch (e) {
      // ignore parse errors, treat as immediate hit
    }
    if (waitedForLock) {
      cacheHitAfterLockWaitLatency.add(res.timings.duration);
    } else {
      cacheHitLatency.add(res.timings.duration);
    }
  }
  if (res.status === 429) {
    rateLimitedCount.add(1);
  }

  sleep(0.1);
}

export function missCacheAndRateLimit() {
  const user = SAMPLE_USERS[Math.floor(Math.random() * SAMPLE_USERS.length)];
  const res = http.get(`${BASE_URL}/github/users/${user}`, {
    headers: { "X-API-Key": __ENV.API_KEY || "" },
  });
  const cacheStatus = res.headers["X-Cache"];

  check(res, {
    "status is 200 or 429": (r) => r.status === 200 || r.status === 429,
  });

  if (res.status === 429) {
    rateLimitedCount.add(1);
    check(res, {
      "429 has Retry-After header": (r) => r.headers["Retry-After"] !== undefined,
    });
  } else if (res.status === 200) {
    if (cacheStatus === "MISS") {
      cacheMissLatency.add(res.timings.duration);
    } else if (cacheStatus === "HIT") {
      let waitedForLock = false;
      try {
        waitedForLock = JSON.parse(res.body).waited_for_lock === true;
      } catch (e) {
        // ignore parse errors, treat as immediate hit
      }
      if (waitedForLock) {
        cacheHitAfterLockWaitLatency.add(res.timings.duration);
      } else {
        cacheHitLatency.add(res.timings.duration);
      }
    }
  }

  sleep(0.05);
}