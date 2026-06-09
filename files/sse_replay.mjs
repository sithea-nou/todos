// Mirror the index.html SSE consumer against the real running server.
// Goal: see exactly what raw bytes the browser receives and how the
// consumer parses them.

const res = await fetch("http://127.0.0.1:8765/api/chat/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: "Say hi in one short sentence" }),
});

const reader = res.body.getReader();
const dec = new TextDecoder();
let buf = "";
let raw = "";
let frameCount = 0;
let lastFrame = null;

const events = [];
let current = null;

while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  raw += dec.decode(value, { stream: true });
  buf += dec.decode(value, { stream: true });
  let nl;
  while ((nl = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, nl);
    buf = buf.slice(nl + 1);
    if (line === "") {
      if (current) {
        events.push(current);
        current = null;
      }
      continue;
    }
    if (line.startsWith("event:")) {
      current = { event: line.slice(6).trim(), data: "" };
    } else if (line.startsWith("data:")) {
      if (!current) current = { event: null, data: "" };
      current.data += line.slice(5).trim();
    } else if (line.startsWith(":")) {
      // comment, ignore
    }
  }
}
if (current) events.push(current);

console.log("RAW BYTES LEN:", raw.length);
console.log("RAW (repr):", JSON.stringify(raw));
console.log("EVENT COUNT:", events.length);
for (const [i, e] of events.entries()) {
  let parsed = null;
  try { parsed = JSON.parse(e.data); } catch {}
  console.log(`#${i} event=${e.event} data=${e.data.slice(0, 200)} parsed=${JSON.stringify(parsed)}`);
}
