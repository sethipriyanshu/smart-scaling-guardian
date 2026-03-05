import http from 'k6/http';
import { check, sleep } from 'k6';

// Phase 5: simple load test to exercise /health and /orders and observe HPA behaviour.
// Run with:
//   k6 run -e BASE_URL=http://<LB_HOSTNAME> load-test/k6_script.js

export const options = {
  stages: [
    { duration: '30s', target: 5 },   // ramp up a few users
    { duration: '2m', target: 20 },   // sustain moderate load
    { duration: '30s', target: 0 },   // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<800'], // 95% of requests under 800ms
    http_req_failed: ['rate<0.02'],   // <2% failures
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';

function randomOrder() {
  const sku = `SKU-${Math.floor(Math.random() * 1000)}`;
  return {
    customer_id: `cust-${__VU}`,
    items: [
      {
        sku,
        quantity: Math.floor(Math.random() * 3) + 1,
        price: Math.round((Math.random() * 50 + 10) * 100) / 100,
      },
    ],
    delivery_address: '123 Test St, Test City',
    priority: 'standard',
  };
}

export default function () {
  // Always hit /health so we see basic availability.
  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, {
    'health is 200': (r) => r.status === 200,
  });

  // On some iterations, create an order to generate real load.
  if (__ITER % 2 === 0) {
    const payload = JSON.stringify(randomOrder());
    const headers = { 'Content-Type': 'application/json' };
    const res = http.post(`${BASE_URL}/orders`, payload, { headers });
    check(res, {
      'order accepted': (r) => r.status === 200,
    });
  }

  sleep(1);
}

