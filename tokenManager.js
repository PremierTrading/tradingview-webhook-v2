import fetch from "node-fetch";

let token     = null;
let expiresAt = 0;  // timestamp in ms

async function fetchNewToken() {
  const res = await fetch(
    "https://live.tradovateapi.com/auth/accessTokenRequest",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name:       process.env.TRADOVATE_USER,
        password:   process.env.TRADOVATE_API_PASSWORD,
        appId:      "1",
        appVersion: "1.0",
        cid:        process.env.TRADOVATE_CID,
        sec:        process.env.TRADOVATE_SECRET
      })
    }
  );
  const data = await res.json();
  token     = data.access_token;
  // schedule expiry 5 minutes 🕔 before actual expiration
  expiresAt = Date.now() + (data.expires_in * 1000) - (5 * 60 * 1000);
}

async function renewToken() {
  const res = await fetch(
    "https://live.tradovateapi.com/auth/renewAccessToken",
    {
      method: "POST",
      headers: {
        "Content-Type":  "application/json",
        "Authorization": `Bearer ${token}`
      }
    }
  );
  const data = await res.json();
  token     = data.access_token;
  expiresAt = Date.now() + (data.expires_in * 1000) - (5 * 60 * 1000);
}

export async function initTokenAutoRefresh() {
  // 1) Fetch initial token
  await fetchNewToken();
  // 2) Set up the interval to renew every hour (expires_in ≈ 3600s)
  const intervalMs = (60 * 60 - 5 * 60) * 1000; // 55 minutes
  setInterval(renewToken, intervalMs);
}

export function getToken() {
  // If somehow it’s past our “renew” threshold, refresh on-demand
  if (Date.now() >= expiresAt) {
    // don’t block, but kick off a renew
    renewToken().catch(console.error);
  }
  return token;
}
