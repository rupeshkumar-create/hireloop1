const assert = require("node:assert/strict");
const path = require("node:path");
const jiti = require("jiti")(__filename, {
  alias: {
    "@": path.join(__dirname, "../src"),
  },
});

const matches = jiti("../src/lib/api/matches.ts");

assert.equal(typeof matches.fetchMatchFeed, "function");
assert.equal(typeof matches.getCachedMatchFeed, "function");
assert.equal(typeof matches.invalidateMatchFeedCache, "function");
