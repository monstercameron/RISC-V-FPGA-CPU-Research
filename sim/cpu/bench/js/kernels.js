// SPDX-License-Identifier: MIT
// JavaScript kernels of the QuickJS-ng benchmark (run_bench.py --benchmark js; original code).
// Every kernel is deterministic (its own xorshift PRNG reseeded per call, no Date, no Math.random,
// no transcendental Math), returns one checksum and runs twice: mark(0x10 + k) starts the warm
// call, mark(0x20 + k) the timed call and mark(0x30 + k) ends it. The two results must agree.
// SCALE (and ONLY, one kernel) are prepended by gen_src.py.
"use strict";
var S = typeof SCALE === "number" ? SCALE : 1;
var seed = 12345;
// xorshift32: every bit is usable (an LCG's low bits repeat with a short period)
function rnd() { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return seed >>> 1; }

// 1. props: monomorphic and polymorphic property access and method calls (inline caches)
function k_props(n) {
  class V { constructor(x, y, z) { this.x = x; this.y = y; this.z = z; }
    add(o) { return new V(this.x + o.x, this.y + o.y, this.z + o.z); }
    dot(o) { return this.x * o.x + this.y * o.y + this.z * o.z; } }
  class Sq { constructor(s) { this.s = s; } area() { return this.s * this.s; } }
  class Re { constructor(w, h) { this.w = w; this.h = h; } area() { return this.w * this.h; } }
  class Tr { constructor(b, h) { this.b = b; this.h = h; } area() { return (this.b * this.h) >> 1; } }
  class Ci { constructor(r) { this.r = r; } area() { return 3 * this.r * this.r; } }
  var shapes = [];
  for (var i = 0; i < 64; i++) {
    var k = i & 3, a = (rnd() & 15) + 1, b = (rnd() & 15) + 1;
    shapes.push(k == 0 ? new Sq(a) : k == 1 ? new Re(a, b) : k == 2 ? new Tr(a, b) : new Ci(a));
  }
  var acc = new V(0, 0, 0), sum = 0;
  for (var j = 0; j < n; j++) {
    var v = new V(j & 7, j & 3, 1);
    acc = acc.add(v);
    sum = (sum + acc.dot(v) + shapes[j & 63].area()) | 0;
  }
  return sum;
}

// 2. sched: a task scheduler with four task kinds, packet queues and virtual dispatch
function k_sched(n) {
  function Packet(link, id, kind) { this.link = link; this.id = id; this.kind = kind; this.a1 = 0; this.data = [0, 0, 0, 0]; }
  Packet.prototype.append = function (q) { this.link = null; if (q === null) return this; var p = q; while (p.link !== null) p = p.link; p.link = this; return q; };
  function Task(id, pri, q) { this.id = id; this.pri = pri; this.q = q; this.count = 0; }
  Task.prototype.take = function () { var p = this.q; if (p !== null) this.q = p.link; return p; };
  function Idle(id) { Task.call(this, id, 0, null); this.v = 1; }
  Idle.prototype = Object.create(Task.prototype);
  Idle.prototype.run = function (s) { this.count++; this.v = (this.v >> 1) ^ ((this.v & 1) ? 0xd008 : 0); return s.tasks[1 + (this.v & 3)]; };
  function Worker(id, q) { Task.call(this, id, 1, q); this.dest = 2; }
  Worker.prototype = Object.create(Task.prototype);
  Worker.prototype.run = function (s) { var p = this.take(); this.count++; if (p === null) return s.tasks[0];
    this.dest = this.dest == 2 ? 3 : 2; p.id = this.dest; for (var i = 0; i < 4; i++) p.data[i] = (p.data[i] + i + this.count) & 255;
    s.send(p, this.dest); return s.tasks[this.dest]; };
  function Handler(id, q) { Task.call(this, id, 2, q); this.work = null; }
  Handler.prototype = Object.create(Task.prototype);
  Handler.prototype.run = function (s) { var p = this.take(); this.count++; if (p === null) return s.tasks[0];
    p.a1 = (p.a1 + p.data[this.count & 3]) & 0xffff; s.send(p, 4); return s.tasks[4]; };
  function Device(id) { Task.call(this, id, 3, null); this.sum = 0; }
  Device.prototype = Object.create(Task.prototype);
  Device.prototype.run = function (s) { var p = this.take(); this.count++; if (p === null) return s.tasks[0];
    this.sum = (this.sum * 31 + p.a1 + p.data[0]) | 0; s.send(p, 1); return s.tasks[1]; };
  var s = { tasks: [], send: function (p, to) { var t = this.tasks[to]; t.q = p.append(t.q); } };
  var q = null; for (var i = 0; i < 6; i++) q = new Packet(q, 1, i & 1);
  s.tasks = [new Idle(0), new Worker(1, q), new Handler(2, null), new Handler(3, null), new Device(4)];
  var t = s.tasks[1];
  for (var k = 0; k < n; k++) t = t.run(s);
  var c = 0; for (var j = 0; j < 5; j++) c = (c * 7 + s.tasks[j].count) | 0;
  return (c ^ s.tasks[4].sum) | 0;
}

// 3. navier: a 2D diffusion and advection stencil on Float64Array (numeric, typed arrays)
function k_navier(n, steps) {
  var N = n + 2, size = N * N, u = new Float64Array(size), v = new Float64Array(size), d = new Float64Array(size), d0 = new Float64Array(size);
  for (var i = 0; i < size; i++) { u[i] = ((rnd() & 255) - 128) / 512; v[i] = ((rnd() & 255) - 128) / 512; d[i] = (rnd() & 1023) / 1024; }
  for (var s = 0; s < steps; s++) {
    var a = 0.1;
    for (var it = 0; it < 4; it++)
      for (var y = 1; y <= n; y++) for (var x = 1; x <= n; x++) {
        var c = x + y * N;
        d0[c] = (d[c] + a * (d0[c - 1] + d0[c + 1] + d0[c - N] + d0[c + N])) / (1 + 4 * a);
      }
    for (var y2 = 1; y2 <= n; y2++) for (var x2 = 1; x2 <= n; x2++) {
      var c2 = x2 + y2 * N, px = x2 - u[c2] * 2, py = y2 - v[c2] * 2;
      if (px < 0.5) px = 0.5; if (px > n + 0.5) px = n + 0.5; if (py < 0.5) py = 0.5; if (py > n + 0.5) py = n + 0.5;
      var i0 = px | 0, j0 = py | 0, s1 = px - i0, t1 = py - j0;
      d[c2] = (1 - s1) * ((1 - t1) * d0[i0 + j0 * N] + t1 * d0[i0 + (j0 + 1) * N]) + s1 * ((1 - t1) * d0[i0 + 1 + j0 * N] + t1 * d0[i0 + 1 + (j0 + 1) * N]);
    }
  }
  var h = 0; for (var k = 0; k < size; k++) h = (h * 33 + ((d[k] * 1e6) | 0)) | 0;
  return h;
}

// 4. crypto: SHA-256 over a generated message (32-bit integer and bit operations)
function k_sha(nbytes, reps) {
  var K = [];
  // the first 32 bits of the fractional parts of the cube roots of the first 64 primes, computed exactly
  var primes = [], c = 2; while (primes.length < 64) { var ok = true; for (var q = 2; q * q <= c; q++) if (c % q == 0) { ok = false; break; } if (ok) primes.push(c); c++; }
  for (var i = 0; i < 64; i++) { var p = primes[i]; // floor(cbrt(p) * 2^32) by bisection on BigInt
    var P = BigInt(p) << 96n, l = 0n, h2 = 1n << 36n; while (h2 - l > 1n) { var m = (l + h2) >> 1n; if (m * m * m <= P) l = m; else h2 = m; }
    K.push(Number(l & 0xffffffffn) | 0); }
  var msg = new Uint8Array(nbytes); for (var j = 0; j < nbytes; j++) msg[j] = rnd() & 255;
  var H; var W = new Int32Array(64);
  for (var r = 0; r < reps; r++) {
    H = [0x6a09e667, 0xbb67ae85 | 0, 0x3c6ef372, 0xa54ff53a | 0, 0x510e527f, 0x9b05688c | 0, 0x1f83d9ab, 0x5be0cd19];
    for (var off = 0; off + 64 <= nbytes; off += 64) {
      for (var t = 0; t < 16; t++) W[t] = (msg[off + 4 * t] << 24) | (msg[off + 4 * t + 1] << 16) | (msg[off + 4 * t + 2] << 8) | msg[off + 4 * t + 3];
      for (t = 16; t < 64; t++) { var x = W[t - 15], y = W[t - 2];
        var s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3), s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10);
        W[t] = (W[t - 16] + s0 + W[t - 7] + s1) | 0; }
      var a = H[0], b = H[1], cc = H[2], d = H[3], e = H[4], f = H[5], g = H[6], hh = H[7];
      for (t = 0; t < 64; t++) {
        var S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7)), ch = (e & f) ^ (~e & g);
        var t1 = (hh + S1 + ch + K[t] + W[t]) | 0, S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        var t2 = (S0 + ((a & b) ^ (a & cc) ^ (b & cc))) | 0;
        hh = g; g = f; f = e; e = (d + t1) | 0; d = cc; cc = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + cc) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + hh) | 0;
    }
    msg[r % nbytes] ^= H[0] & 255;
  }
  return H.map(function (w) { return (w >>> 0).toString(16).padStart(8, "0"); }).join("");
}

// 5. json: build a record tree, stringify, parse, walk
function k_json(n) {
  var recs = [];
  for (var i = 0; i < n; i++) recs.push({ id: i, name: "item" + (rnd() % 1000), price: (rnd() % 10000) / 100,
    tags: ["a" + (i & 7), "b" + (i % 5)], dims: { w: rnd() & 63, h: rnd() & 63 }, ok: (i & 1) == 0, note: null });
  var s = JSON.stringify({ version: 3, records: recs });
  var o = JSON.parse(s), sum = 0;
  for (var j = 0; j < o.records.length; j++) { var r = o.records[j]; sum = (sum + r.id + r.dims.w * r.dims.h + (r.ok ? 1 : 0) + r.tags[1].length + Math.round(r.price * 100)) | 0; }
  return s.length + ":" + sum;
}

// 6. regex: parse generated log lines with a regular expression, replace and test
function k_regex(n) {
  var lines = [], lv = ["INFO", "WARN", "ERROR", "DEBUG"];
  for (var i = 0; i < n; i++) lines.push("2026-11-" + (10 + (i % 20)) + " " + lv[rnd() & 3] + " [svc" + (rnd() % 9) + "] req=" + (rnd() % 100000) + " took " + (rnd() % 500) + "ms user=u" + (rnd() % 77) + "@example.org");
  var re = /^(\d{4})-(\d\d)-(\d\d) (INFO|WARN|ERROR|DEBUG) \[(\w+)\] req=(\d+) took (\d+)ms user=([a-z0-9]+)@([\w.]+)$/;
  var errs = 0, total = 0, users = {}, mails = 0;
  for (var j = 0; j < lines.length; j++) { var m = re.exec(lines[j]); if (!m) continue;
    if (m[4] === "ERROR") errs++; total += +m[7]; users[m[8]] = (users[m[8]] | 0) + 1; }
  var text = lines.join("\n").replace(/took (\d+)ms/g, function (_, d) { return "t=" + (d * 2); });
  mails = (text.match(/@example\.org/g) || []).length;
  return errs + ":" + total + ":" + Object.keys(users).length + ":" + mails + ":" + text.length;
}

// 7. strings: concatenation, split/join, slicing, char codes, template literals
function k_strings(n) {
  var parts = [], h = 0;
  for (var i = 0; i < n; i++) parts.push(`<li class="row r${i % 7}" data-id="${i}">${"x".repeat(i & 15)}</li>`);
  var html = parts.join("");
  var words = html.split(/[<>"= ]+/);
  for (var j = 0; j < words.length; j++) { var w = words[j]; for (var k = 0; k < w.length; k++) h = (h * 31 + w.charCodeAt(k)) | 0; }
  var s = ""; for (var q = 0; q < n; q++) s += String.fromCharCode(97 + (q % 26));
  var up = s.toUpperCase(), idx = 0, cnt = 0; while ((idx = up.indexOf("XYZ", idx)) >= 0) { cnt++; idx += 3; }
  return h + ":" + html.length + ":" + cnt + ":" + up.slice(n >> 1, (n >> 1) + 6);
}

// 8. dom: a DOM-like tree: build, query by class, mutate, serialise (the web-page flavour)
function k_dom(n) {
  function El(tag) { this.tag = tag; this.children = []; this.parent = null; this.attrs = new Map(); this.classList = new Set(); this.text = ""; }
  El.prototype.append = function (c) { c.parent = this; this.children.push(c); return c; };
  El.prototype.remove = function () { var p = this.parent, i = p.children.indexOf(this); p.children.splice(i, 1); this.parent = null; };
  El.prototype.query = function (cls, out) { if (this.classList.has(cls)) out.push(this); for (var i = 0; i < this.children.length; i++) this.children[i].query(cls, out); return out; };
  El.prototype.html = function () { var a = ""; this.attrs.forEach(function (v, k) { a += " " + k + "=\"" + v + "\""; });
    var s = "<" + this.tag + a + ">" + this.text; for (var i = 0; i < this.children.length; i++) s += this.children[i].html(); return s + "</" + this.tag + ">"; };
  var root = new El("body"), tags = ["div", "span", "p", "a", "ul", "li"], all = [root];
  for (var i = 0; i < n; i++) { var p = all[rnd() % all.length], e = p.append(new El(tags[rnd() % 6]));
    e.classList.add("c" + (rnd() & 7)); if (rnd() & 1) e.classList.add("hot"); e.attrs.set("id", "n" + i); e.text = (i & 3) ? "" : "t" + i; all.push(e); }
  var hot = root.query("hot", []);
  for (var j = 0; j < hot.length; j += 3) { var h = hot[j]; if (h.parent && h.children.length == 0) h.remove(); else h.attrs.set("data-x", j); }
  var c3 = root.query("c3", []), s = root.html(), sum = 0;
  for (var k = 0; k < s.length; k += 7) sum = (sum + s.charCodeAt(k)) | 0;
  return hot.length + ":" + c3.length + ":" + s.length + ":" + sum;
}

// 9. funcs: closures, higher-order array methods, sort with a comparator
function k_funcs(n) {
  var a = []; for (var i = 0; i < n; i++) a.push({ k: rnd() % 1000, v: i });
  var mk = function (m) { return function (x) { return (x.k * m) % 997; }; };
  var f3 = mk(3), f7 = mk(7);
  var b = a.map(function (x) { return { k: f3(x) + f7(x), v: x.v }; }).filter(function (x) { return x.k & 1; });
  b.sort(function (x, y) { return x.k - y.k || x.v - y.v; });
  var r = b.reduce(function (s, x, i) { return (s * 17 + x.k * (i & 15) + x.v) | 0; }, 0);
  return b.length + ":" + r;
}

var kernels = [
  ["props", function () { return k_props(3000 * S); }],
  ["sched", function () { return k_sched(5000 * S); }],
  ["navier", function () { return k_navier(24, 4 * S); }],
  ["sha256", function () { return k_sha(1024, 4 * S); }],
  ["json", function () { return k_json(400 * S); }],
  ["regex", function () { return k_regex(400 * S); }],
  ["strings", function () { return k_strings(400 * S); }],
  ["dom", function () { return k_dom(800 * S); }],
  ["funcs", function () { return k_funcs(2000 * S); }],
];
var only = typeof ONLY === "number" ? ONLY : -1;
for (var ki = 0; ki < kernels.length; ki++) {
  if (only >= 0 && ki != only) continue;
  seed = 12345 + ki;
  mark(0x10 + ki);
  var warm = kernels[ki][1]();
  seed = 12345 + ki;
  mark(0x20 + ki);
  var res = kernels[ki][1]();
  mark(0x30 + ki);
  if (warm === res) print(kernels[ki][0], res);
  else print(kernels[ki][0], res, "warm call differs:", warm);
}
