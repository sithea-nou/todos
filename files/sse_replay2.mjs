// Same parser as the rewritten index.html consumeSSE — verify it
// correctly splits the single-newline-terminated stream from the live
// server.

const res = await fetch("http://127.0.0.1:8765/api/chat/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: "Say hi in one short sentence" }),
});

const reader = res.body.getReader();
const dec = new TextDecoder();
let buffer = "";

const events = [];

const dispatch = (raw) => {
  let event = "message";
  const dataLines = [];
  for (const line of raw.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const idx = line.indexOf(":");
    if (idx < 0) continue;
    const field = line.slice(0, idx);
    let value = line.slice(idx + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }
  if (!dataLines.length) return false;
  let parsed;
  try { parsed = JSON.parse(dataLines.join("\n")); } catch { return false; }
  parsed._event = event;
  events.push(parsed);
  return true;
};

while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += dec.decode(value, { stream: true });
  const frames = buffer.split(/\n\n|(?=\nevent:)/);
  buffer = frames.pop() || "";
  for (const ev of frames) {
    if (!ev.trim()) continue;
    dispatch(ev);
  }
}
if (buffer.trim()) dispatch(buffer);

console.log("EVENT COUNT:", events.length);
for (const [i, e] of events.entries()) {
  console.log(`#${i} event=${e._event}`, JSON.stringify(e).slice(0, 200));
}
const finalText = events
  .filter((e) => e._event === "token")
  .map((e) => e.delta)
  .join("");
const doneEv = events.find((e) => e._event === "done");
console.log("ASSEMBLED TEXT LEN:", finalText.length);
console.log("ASSEMBLED TEXT:", JSON.stringify(finalText));
console.log("DONE RESPONSE:", doneEv ? doneEv.response : null);
