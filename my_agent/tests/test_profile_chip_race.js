"use strict";
/**
 * Regression test for the profile-chip UI race condition described in
 * PROJECT_LOG.md section 13.
 *
 * On page load, campus_map_prototype.html fires two async calls at once:
 * a fast GET /api/categories (~9ms in practice) and a slow POST /api/rerank
 * (~6s, real Bedrock latency) that restores the student's saved profile.
 * The buggy version of renderInterestChips() preferred whatever was already
 * lit up in the DOM, so the fast categories call's render (still showing
 * the hardcoded default interests, since the slow rerank call hadn't
 * resolved yet) got "preserved" even after the slow call later restored the
 * real saved profile -- the interest chips stayed on the wrong selection
 * while the profile banner above them correctly showed the right one.
 *
 * The fix (userEditedInterests flag) makes chip rendering only trust DOM
 * state once the student has actually clicked a chip themselves; otherwise
 * it always derives from the live STUDENT_PROFILE object. This test
 * reproduces the exact race (fast /api/categories resolving before slow
 * /api/rerank) and asserts the chips end up matching the *real* saved
 * profile, not the default.
 *
 * Run:
 *   npm install
 *   node test_profile_chip_race.js
 * Exits 0 and prints "PASS" on success, exits 1 and prints "FAIL" + a diff
 * otherwise -- suitable for CI or a pre-push sanity check.
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML_PATH = path.join(__dirname, "..", "campus_map_prototype.html");

// Deliberately different from the hardcoded default STUDENT_PROFILE
// (sophomore / Computer Science / career+academic) so a test failure is
// unambiguous: if the chips show career/academic, the race condition is
// back.
const SAVED_PROFILE = { year: "junior", major: "Biology", interests: ["transfer", "sports"] };

// Delays are milliseconds, not the real ~9ms / ~6s -- just need categories
// to resolve meaningfully before rerank to reproduce the ordering that
// triggers the bug.
const CATEGORIES_DELAY_MS = 5;
const RERANK_DELAY_MS = 80;
const SETTLE_BUFFER_MS = 150; // extra margin after RERANK_DELAY_MS before we inspect the DOM

function makeFakeLeaflet() {
  // campus_map_prototype.html loads real Leaflet from a CDN <script src>,
  // which we strip out below (this test runs with no network access), so
  // initMap() needs a stand-in for the global `L` it calls into. None of
  // the map-rendering behavior is under test here -- only the profile/chip
  // logic -- so every method just returns a chainable no-op.
  function makeMarker() {
    const marker = {
      addTo: () => marker,
      bindPopup: () => marker,
      openPopup: () => marker,
    };
    return marker;
  }
  const chainable = () => api;
  const api = {
    map: () => api,
    setView: chainable,
    control: { zoom: () => ({ addTo: chainable }) },
    tileLayer: () => ({ addTo: chainable }),
    marker: () => makeMarker(),
    divIcon: () => ({}),
    removeLayer: () => {},
    flyTo: () => {},
  };
  return api;
}

function stripExternalResources(html) {
  // Remove CDN <link>/<script src> tags (Leaflet, Google Fonts) so JSDOM
  // never attempts a network request. The app's own inline <script> block
  // (no src attribute) is left untouched -- that's what we're testing.
  return html
    .replace(/<link[^>]+href="https?:\/\/[^"]+"[^>]*>/g, "")
    .replace(/<script[^>]+src="https?:\/\/[^"]+"[^>]*><\/script>/g, "");
}

async function run() {
  const originalHtml = fs.readFileSync(HTML_PATH, "utf8");
  const html = stripExternalResources(originalHtml);

  let fetchCalls = { categories: 0, rerank: 0 };

  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    url: "http://localhost/campus_map_prototype.html",
    beforeParse(window) {
      window.L = makeFakeLeaflet();

      window.fetch = (url) => {
        if (String(url).includes("/api/categories")) {
          fetchCalls.categories++;
          return new Promise((resolve) =>
            setTimeout(
              () => resolve({ ok: true, json: async () => ({ categories: ["financial-aid", "workshops"] }) }),
              CATEGORIES_DELAY_MS
            )
          );
        }
        if (String(url).includes("/api/rerank")) {
          fetchCalls.rerank++;
          return new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  ok: true,
                  json: async () => ({
                    generated_at: "2026-08-24T00:00:00",
                    student_profile: SAVED_PROFILE,
                    events: [],
                  }),
                }),
              RERANK_DELAY_MS
            )
          );
        }
        return Promise.reject(new Error(`test stub: unexpected fetch url ${url}`));
      };

      // Simulates a returning student: this browser already has a saved
      // profile in localStorage, so tryAutoPersonalize() should kick in on
      // load (see the bottom of the app's inline script).
      window.localStorage.setItem("campusCompassProfile", JSON.stringify(SAVED_PROFILE));
    },
  });

  const { window } = dom;

  // Wait for the initial parse+script pass, then long enough for both the
  // fast (/api/categories) and slow (/api/rerank) mocked fetches to
  // resolve and their .then chains (renderInterestChips, etc.) to run.
  await new Promise((resolve) => {
    if (window.document.readyState === "complete") resolve();
    else window.addEventListener("load", resolve);
  });
  await new Promise((resolve) => setTimeout(resolve, RERANK_DELAY_MS + SETTLE_BUFFER_MS));

  if (fetchCalls.categories === 0 || fetchCalls.rerank === 0) {
    throw new Error(
      `test setup problem: expected both /api/categories and /api/rerank to be called at least once ` +
        `(got categories=${fetchCalls.categories}, rerank=${fetchCalls.rerank}) -- the page's load-time calls may have changed`
    );
  }

  const activeChips = Array.from(window.document.querySelectorAll("#interestChips .chip.active")).map(
    (el) => el.textContent
  );
  const activeSet = new Set(activeChips);
  const expectedSet = new Set(SAVED_PROFILE.interests);
  const defaultInterests = ["career", "academic"]; // the hardcoded STUDENT_PROFILE default in the page

  const matchesSaved = activeSet.size === expectedSet.size && [...expectedSet].every((tag) => activeSet.has(tag));
  const stuckOnDefault = defaultInterests.every((tag) => activeSet.has(tag)) && !expectedSet.has("career");

  window.close();

  if (!matchesSaved) {
    console.error("FAIL: interest chips do not match the restored saved profile after both fetches resolved.");
    console.error(`  expected active chips: ${[...expectedSet].sort().join(", ")}`);
    console.error(`  actual active chips:   ${[...activeSet].sort().join(", ")}`);
    if (stuckOnDefault) {
      console.error(
        "  chips are stuck on the hardcoded default (career/academic) -- this is exactly the race " +
          "condition from PROJECT_LOG.md section 13: the fast /api/categories render is winning over " +
          "the slower /api/rerank profile restore."
      );
    }
    process.exitCode = 1;
    return;
  }

  console.log("PASS: interest chips correctly reflect the saved profile restored by the slower /api/rerank call.");
  console.log(`  active chips: ${[...activeSet].sort().join(", ")}`);
}

run().catch((err) => {
  console.error("FAIL:", err);
  process.exitCode = 1;
});
