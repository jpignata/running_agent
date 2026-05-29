const fs = require("fs");
const zlib = require("zlib");

const size = 1024;
const scale = 3;
const big = size * scale;
const orange = [252, 76, 2, 255];
const transparent = [255, 255, 255, 0];

const pixels = new Uint8ClampedArray(big * big * 4);
for (let i = 0; i < pixels.length; i += 4) {
  pixels.set(transparent, i);
}

function setPixel(x, y, color) {
  if (x < 0 || y < 0 || x >= big || y >= big) return;
  pixels.set(color, (y * big + x) * 4);
}

function fillCircle(cx, cy, radius) {
  cx *= scale;
  cy *= scale;
  radius *= scale;
  const minX = Math.max(0, Math.floor(cx - radius));
  const maxX = Math.min(big - 1, Math.ceil(cx + radius));
  const minY = Math.max(0, Math.floor(cy - radius));
  const maxY = Math.min(big - 1, Math.ceil(cy + radius));
  const r2 = radius * radius;

  for (let y = minY; y <= maxY; y += 1) {
    for (let x = minX; x <= maxX; x += 1) {
      const dx = x + 0.5 - cx;
      const dy = y + 0.5 - cy;
      if (dx * dx + dy * dy <= r2) {
        setPixel(x, y, orange);
      }
    }
  }
}

function fillCapsule(x1, y1, x2, y2, radius) {
  x1 *= scale;
  y1 *= scale;
  x2 *= scale;
  y2 *= scale;
  radius *= scale;

  const minX = Math.max(0, Math.floor(Math.min(x1, x2) - radius));
  const maxX = Math.min(big - 1, Math.ceil(Math.max(x1, x2) + radius));
  const minY = Math.max(0, Math.floor(Math.min(y1, y2) - radius));
  const maxY = Math.min(big - 1, Math.ceil(Math.max(y1, y2) + radius));
  const vx = x2 - x1;
  const vy = y2 - y1;
  const len2 = vx * vx + vy * vy;
  const r2 = radius * radius;

  for (let y = minY; y <= maxY; y += 1) {
    for (let x = minX; x <= maxX; x += 1) {
      const px = x + 0.5;
      const py = y + 0.5;
      const t = Math.max(0, Math.min(1, ((px - x1) * vx + (py - y1) * vy) / len2));
      const cx = x1 + t * vx;
      const cy = y1 + t * vy;
      const dx = px - cx;
      const dy = py - cy;
      if (dx * dx + dy * dy <= r2) {
        setPixel(x, y, orange);
      }
    }
  }
}

function drawPolyline(points, radius) {
  for (let i = 0; i < points.length - 1; i += 1) {
    fillCapsule(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1], radius);
  }
}

drawPolyline(
  [
    [202, 730],
    [318, 618],
    [408, 598],
    [492, 514],
    [602, 404],
    [694, 386],
    [822, 282],
  ],
  43,
);

fillCircle(202, 730, 58);
fillCircle(492, 514, 58);
fillCircle(822, 282, 58);
fillCapsule(356, 284, 516, 284, 36);
fillCapsule(436, 204, 436, 364, 36);

const small = Buffer.alloc(size * (size * 4 + 1));
for (let y = 0; y < size; y += 1) {
  const rowStart = y * (size * 4 + 1);
  small[rowStart] = 0;
  for (let x = 0; x < size; x += 1) {
    let r = 0;
    let g = 0;
    let b = 0;
    let a = 0;
    for (let sy = 0; sy < scale; sy += 1) {
      for (let sx = 0; sx < scale; sx += 1) {
        const idx = (((y * scale + sy) * big + (x * scale + sx)) * 4);
        r += pixels[idx];
        g += pixels[idx + 1];
        b += pixels[idx + 2];
        a += pixels[idx + 3];
      }
    }
    const samples = scale * scale;
    const out = rowStart + 1 + x * 4;
    small[out] = Math.round(r / samples);
    small[out + 1] = Math.round(g / samples);
    small[out + 2] = Math.round(b / samples);
    small[out + 3] = Math.round(a / samples);
  }
}

function chunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const name = Buffer.from(type);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([name, data])));
  return Buffer.concat([length, name, data, crc]);
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let k = 0; k < 8; k += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const ihdr = Buffer.alloc(13);
ihdr.writeUInt32BE(size, 0);
ihdr.writeUInt32BE(size, 4);
ihdr[8] = 8;
ihdr[9] = 6;
ihdr[10] = 0;
ihdr[11] = 0;
ihdr[12] = 0;

const png = Buffer.concat([
  signature,
  chunk("IHDR", ihdr),
  chunk("IDAT", zlib.deflateSync(small, { level: 9 })),
  chunk("IEND", Buffer.alloc(0)),
]);

fs.writeFileSync("assets/running-agent-icon.png", png);
