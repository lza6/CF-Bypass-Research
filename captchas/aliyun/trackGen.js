// trackGen.js — slider-captcha-lab human_track.py (feedback 变体) 的忠实 JS 移植。
// 运行时生成真人形态轨迹: 慢逼近+谷底犹豫+末端甩鞭+量化噪声+零位移帧
// +中途反向微调+犹豫停顿+末端回拉, 距离守恒 <1e-9。
// 每次 run 全新随机(静态复用同一轨迹 = 强机器人指纹)。
"use strict";

// ---- seeded PRNG (mulberry32): SEED 固定时可复现 ----
function makeRng(seed) {
  let a = seed >>> 0;
  const f = function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  f.uniform = (lo, hi) => lo + f() * (hi - lo);
  f.int = (lo, hi) => lo + Math.floor(f() * (hi - lo + 1));
  f.choice = (arr) => arr[Math.floor(f() * arr.length)];
  return f;
}

// ---- human_longtail 时间网格 (Python time_grid mode="human_longtail") ----
function timeGridLongtail(totalS, n, rng) {
  const raw = [];
  for (let i = 0; i < n - 1; i++) {
    const r = rng();
    if (r < 0.62) raw.push(rng.uniform(0.0035, 0.0065));
    else if (r < 0.78) raw.push(rng.uniform(0.008, 0.018));
    else if (r < 0.90) raw.push(rng.uniform(0.025, 0.060));
    else raw.push(rng.uniform(0.070, 0.220));
  }
  const scale = totalS / Math.max(raw.reduce((x, y) => x + y, 0), 1e-9);
  const minDt = 0.0012;
  let times;
  if (scale * 0.004 < minDt) {
    times = [0.0];
    for (const dt of raw) times.push(times[times.length - 1] + Math.max(dt * scale, minDt));
    const maxEnd = totalS * 1.5;
    if (times[times.length - 1] > maxEnd) {
      const k = maxEnd / times[times.length - 1];
      times = times.map((t) => t * k);
    }
    times[times.length - 1] = Math.max(times[times.length - 1], totalS);
    return times;
  }
  times = [0.0];
  for (const dt of raw) times.push(times[times.length - 1] + dt * scale);
  times[times.length - 1] = totalS;
  return times;
}

// ---- generate_drag (variant=feedback) 主轨迹 ----
// 返回 [{dx, dy, dt}] (dt 毫秒), 累计 dx == D + biasPx (误差 <1e-9)
function generateDrag(D, biasPx, rng) {
  const events = rng.int(130, 200);
  const decay = rng.uniform(4.0, 12.0);
  const frontRamp = rng.uniform(0.08, 0.25);          // combo/feedback 峰值后移
  const yAmplitude = rng.uniform(8.0, 18.0);          // feedback y 振幅
  // feedback y 线性漂移: 75% 向上(安全) / 25% 小幅向下
  const yDrift = rng() < 0.75 ? -rng.uniform(25.0, 90.0) : rng.uniform(10.0, 35.0);
  const yCycles = rng.uniform(0.5, 1.1);
  const DActual = D + biasPx;

  // 爆发前载速度形状 (归一化)
  const vUnit = (u) => {
    if (u < frontRamp && frontRamp > 0) return u / frontRamp;
    const uu = (u - frontRamp) / Math.max(1e-6, 1.0 - frontRamp);
    return Math.pow(1.0 - uu, decay);
  };
  const M = 400;
  const gridU = Array.from({ length: M }, (_, i) => i / (M - 1));
  const Vn = gridU.map(vUnit);
  const Sn = new Array(M).fill(0);
  for (let i = 1; i < M; i++) Sn[i] = Sn[i - 1] + (Vn[i - 1] + Vn[i]) * 0.5 * (gridU[i] - gridU[i - 1]);
  const VnSum = Sn[M - 1];
  const interp = (u) => {           // 线性插值 Sn
    if (u <= 0) return 0;
    if (u >= 1) return Sn[M - 1];
    const fi = u * (M - 1), i = Math.floor(fi), t = fi - i;
    return Sn[i] * (1 - t) + Sn[Math.min(i + 1, M - 1)] * t;
  };

  // 时长分布 (feedback): 20% 0.9-1.25 / 65% 1.25-1.9 / 15% 1.9-3.1 s
  const r = rng();
  const totalS = r < 0.20 ? rng.uniform(0.9, 1.25)
               : r < 0.65 ? rng.uniform(1.25, 1.9)
                          : rng.uniform(1.9, 3.1);

  const times = timeGridLongtail(totalS, events, rng);

  // 采样位置曲线 + y = 漂移(手臂缓移) + 振荡(手腕抖动)
  const points = [];
  for (const t of times) {
    const u = totalS > 0 ? Math.min(1.0, t / totalS) : 1.0;
    const x = DActual * interp(u) / VnSum;
    const phase = 2 * Math.PI * yCycles * u;
    const envelope = Math.pow(Math.sin(Math.PI * u), 1.7);
    const y = yDrift * u + yAmplitude * envelope * Math.sin(phase);
    points.push([x, y, t]);
  }

  let track = [];
  for (let i = 1; i < points.length; i++) {
    const [x0, y0, t0] = points[i - 1], [x1, y1, t1] = points[i];
    let dx = x1 - x0;
    if (dx < 0.01) dx = 0.01;      // 长尾段最小位移钳
    track.push([dx, y1 - y0, (t1 - t0) * 1000.0]);
  }

  // 主段缩放保证总位移
  let cur = track.reduce((s, t) => s + t[0], 0);
  if (Math.abs(cur - DActual) > 1e-9) {
    const nMain = Math.max(2, Math.floor(track.length * 0.8));
    const mainSum = track.slice(0, nMain).reduce((s, t) => s + t[0], 0);
    if (mainSum > 1.0) {
      const k = (mainSum + (DActual - cur)) / mainSum;
      for (let i = 0; i < nMain; i++) track[i][0] *= k;
    }
  }

  // ================= feedback 微结构 =================
  // 0) 修剪 0.01px 死帧尾巴 (dt 并入最后活帧, 距离归还主段)
  let live = track.length;
  while (live > 10 && track[live - 1][0] <= 0.05) live--;
  const deadSum = track.slice(live).reduce((s, t) => s + t[0], 0);
  const deadDy = track.slice(live).reduce((s, t) => s + t[1], 0);
  const deadDt = track.slice(live).reduce((s, t) => s + t[2], 0);
  if (live < track.length && deadDt > 0) {
    const [dx, dy, dt] = track[live - 1];
    track[live - 1] = [dx, dy, dt + deadDt];
  }
  track = track.slice(0, live);
  if (deadSum > 1e-9) {
    const c = track.reduce((s, t) => s + t[0], 0);
    if (c > 0.01) {
      const k = (c + deadSum) / c;
      track = track.map(([dx, dy, dt]) => [Math.max(0.01, dx * k), dy, dt]);
    }
  }
  if (Math.abs(deadDy) > 1e-9 && track.length) {
    const [dx, dy, dt] = track[track.length - 1];
    track[track.length - 1] = [dx, dy + deadDy, dt];
  }
  let n = track.length;

  if (n >= 10 && track.reduce((s, t) => s + t[0], 0) > 10) {
    // 1) 形态重构: 前段压速(15~30%距离) + 谷底 + 甩鞭(86~94%) + 收尾
    const split = Math.floor(n * rng.uniform(0.45, 0.60));
    const DNow = track.reduce((s, t) => s + t[0], 0);
    const frontBudget = DNow * rng.uniform(0.15, 0.30);
    const front = track.slice(0, split);
    const frontSum = front.reduce((s, t) => s + t[0], 0);
    if (frontSum > 1.0) {
      const kf = frontBudget / frontSum;
      for (let i = 0; i < split; i++) track[i][0] = Math.max(0.01, track[i][0] * kf);
    }
    const flickTotal = DNow - frontBudget;
    const backDyTotal = track.slice(split).reduce((s, t) => s + t[1], 0);
    if (flickTotal > 5.0 && n - split >= 6) {
      const valleyN = rng.int(3, 6);
      const flickN = rng.int(16, 28);
      const coastN = rng.int(5, 10);
      const valleyShare = rng.uniform(0.02, 0.05);
      const flickShare = rng.uniform(0.86, 0.94);
      const valleyDx = flickTotal * valleyShare;
      const flickDx = flickTotal * flickShare;
      const coastDx = flickTotal - valleyDx - flickDx;
      // 谷底: 微位移 + 大 dt(40~110ms, 看缺口)
      const vFrames = Array.from({ length: valleyN }, () =>
        [valleyDx / valleyN, 0.0, rng.uniform(40, 110)]);
      // 甩鞭: 窄高斯驼峰 @ dt 2.5~6ms → 峰值 5000~15000 px/s
      const pk = rng.uniform(0.35, 0.6), sigma = rng.uniform(0.07, 0.11);
      const fShape = [];
      for (let j = 0; j < flickN; j++) {
        const ph = j / Math.max(1, flickN - 1);
        fShape.push(0.05 + Math.exp(-((ph - pk) ** 2) / (2 * sigma * sigma)));
      }
      const fs = fShape.reduce((x, y) => x + y, 0);
      const fFrames = fShape.map((s2) => [flickDx * s2 / fs, 0.0, rng.uniform(2.5, 6.0)]);
      // 收尾: 中速滑行 6~16ms
      const cFrames = Array.from({ length: coastN }, () => [coastDx / coastN, 0.0, rng.uniform(6.0, 16.0)]);
      const newBack = vFrames.concat(fFrames, cFrames);
      const totNew = newBack.reduce((s, t) => s + t[0], 0);
      for (let j = 0; j < newBack.length; j++) {
        newBack[j] = [Math.max(0.01, newBack[j][0]),
                      backDyTotal * newBack[j][0] / Math.max(totNew, 1e-9),
                      newBack[j][2]];
      }
      track = track.slice(0, split).concat(newBack);
      n = track.length;
    }

    // 2) 整数量化噪声: 0.42~0.58px 网格 + 35% 帧 ±1 格, 距离守恒
    const grid = rng.uniform(0.42, 0.58);
    const orig = track.reduce((s, t) => s + t[0], 0);
    const quant = track.map(([dx]) => {
      let q = Math.round(dx / grid) * grid;
      if (q > 0.5 && rng() < 0.35) q += rng.choice([-1, 1]) * grid;
      return Math.max(0.01, q);
    });
    const qSum = quant.reduce((x, y) => x + y, 0);
    let resQ = orig - qSum;
    if (Math.abs(resQ) > 1e-9 && qSum > 0.01) {
      for (let i = 0; i < n; i++) quant[i] = Math.max(0.01, quant[i] + resQ * quant[i] / qSum);
      const still = orig - quant.reduce((x, y) => x + y, 0);
      if (Math.abs(still) > 1e-9) {
        const imax = quant.indexOf(Math.max(...quant));
        quant[imax] += still;
      }
    }
    for (let i = 0; i < n; i++) track[i][0] = quant[i];

    // 3) 零位移帧 (真人 4% 帧完全静止)
    const nZero = Math.max(1, Math.floor(n * rng.uniform(0.03, 0.07)));
    for (let k = 0; k < nZero; k++) {
      const zi = rng.int(2, n - 3);
      if (track[zi][0] > 0.05) {
        track[zi + 1][0] += track[zi][0];
        track[zi][0] = 0.0;
      }
    }

    // 4) 中途反向微调 (真人 speed_reversal p50=6)
    const nRev = rng.int(1, 3);
    for (let k = 0; k < nRev; k++) {
      const ri = rng.int(Math.floor(n * 0.25), Math.max(Math.floor(n * 0.25) + 2, Math.floor(n * 0.80)));
      if (ri + 3 >= n) continue;
      const pull = rng.uniform(0.8, 2.2);
      track[ri][0] -= pull * 0.6;
      track[ri + 1][0] -= pull * 0.4;
      track[ri + 2][0] += pull;
    }

    // 5) 中途犹豫停顿 (40% 无 / 40% 一次 / 20% 两次, 40~85% 进度处)
    const rp = rng();
    const nPauses = rp < 0.40 ? 0 : rp < 0.80 ? 1 : 2;
    for (let k = 0; k < nPauses; k++) {
      const i = rng.int(Math.floor(n * 0.40), Math.max(Math.floor(n * 0.40) + 1, Math.floor(n * 0.85)));
      track[i][2] += rng.uniform(60, 160);
    }

    // 6) 末端回拉 (55% 概率, 6~13 帧负 dx 共 3~12px, 距离守恒)
    if (rng() < 0.55) {
      const backN = rng.int(6, 13);
      if (n - backN > 10) {
        const backTotal = rng.uniform(3.0, 12.0);
        const w = Array.from({ length: backN }, (_, k) => 1.0 + Math.sin(Math.PI * (k + 1) / backN));
        const wSum = w.reduce((x, y) => x + y, 0);
        const backs = w.map((ww) => backTotal * ww / wSum);
        const mainFrames = track.slice(0, n - backN);
        const mainSum = mainFrames.reduce((s, t) => s + t[0], 0);
        const need = DActual + backTotal;
        if (mainSum > 1.0 && need > 0) {
          const ks = need / mainSum;
          for (let i = 0; i < n - backN; i++) track[i][0] = Math.max(0.01, track[i][0] * ks);
        }
        const dyBackTotal = track.slice(n - backN).reduce((s, t) => s + t[1], 0);
        const dyBackW = track.slice(n - backN).map((t) => Math.abs(t[1]) + 0.01);
        const dwSum = dyBackW.reduce((x, y) => x + y, 0);
        for (let k = 0; k < backN; k++) {
          const dtNew = k === 0 ? rng.uniform(40, 140) : rng.uniform(3.5, 10.0);
          const dyNew = dwSum > 0 ? dyBackTotal * dyBackW[k] / dwSum : 0.0;
          track[n - backN + k] = [-backs[k], dyNew, dtNew];
        }
        const finalSum = track.reduce((s, t) => s + t[0], 0);
        const resid = DActual - finalSum;
        if (Math.abs(resid) > 1e-9) {
          const wts = track.slice(0, n - backN).map((t) => Math.max(t[0], 0.01));
          const wsum = wts.reduce((x, y) => x + y, 0);
          if (wsum > 0.01) {
            for (let i = 0; i < n - backN; i++) track[i][0] = Math.max(0.01, track[i][0] + resid * wts[i] / wsum);
          }
        }
      }
    }
  }

  // 7) 松手前微动作清除 (最后 200ms 内 0<|dx|<1 → 0 或 1.15px)
  n = track.length;
  let winStart = n, rem = 0.2;
  for (let i = n - 1; i >= 0; i--) {
    rem -= track[i][2] / 1000.0;
    if (rem <= 0) { winStart = i; break; }
  }
  let snapDiff = 0.0;
  for (let i = winStart; i < n; i++) {
    const dx = track[i][0];
    if (dx !== 0 && Math.abs(dx) < 1.0) {
      if (rng() < 0.6) { snapDiff -= dx; track[i][0] = 0.0; }
      else { const sign = dx > 0 ? 1 : -1; snapDiff += sign * 1.15 - dx; track[i][0] = sign * 1.15; }
    }
  }
  if (Math.abs(snapDiff) > 1e-9) {
    let placed = false;
    for (let i = winStart - 1; i >= 0; i--) {
      if (track[i][0] >= 1.0) { track[i][0] = Math.max(0.01, track[i][0] + snapDiff); placed = true; break; }
    }
    if (!placed) track[0][0] = Math.max(0.01, track[0][0] + snapDiff);
  }

  // 8) 全局距离终校
  const finalDiff = DActual - track.reduce((s, t) => s + t[0], 0);
  if (Math.abs(finalDiff) > 1e-9) {
    const wts2 = track.map((t) => (t[0] >= 1.0 ? t[0] : 0.0));
    const ws2 = wts2.reduce((x, y) => x + y, 0);
    if (ws2 > 0.5) {
      for (let i = 0; i < track.length; i++) {
        if (wts2[i] > 0) track[i][0] = Math.max(0.01, track[i][0] + finalDiff * wts2[i] / ws2);
      }
    } else {
      track[0][0] = Math.max(0.01, track[0][0] + finalDiff);
    }
  }
  return track;
}

// ---- 审计 (真人参考: peak_pos=0.75 speed_max=9722 sign_changes~25 y_std=38 neg_dx=0.04) ----
function audit(track) {
  const vels = track.map(([dx, , dt]) => dx / Math.max(dt / 1000.0, 1e-4));
  const accels = [];
  for (let i = 1; i < vels.length; i++) {
    const dt = Math.max(track[i][2] / 1000.0, 1e-4);
    accels.push((vels[i] - vels[i - 1]) / dt);
  }
  let cum = 0;
  const totalD = track.reduce((s, t) => s + Math.abs(t[0]), 0) || 1;
  let peakPos = 0, best = -1;
  for (let i = 0; i < vels.length; i++) {
    cum += Math.abs(track[i][0]);
    if (vels[i] > best) { best = vels[i]; peakPos = cum / totalD; }
  }
  const nz = accels.filter((a) => Math.abs(a) > 1e-9).map((a) => Math.sign(a));
  let signChanges = 0;
  for (let i = 1; i < nz.length; i++) if (nz[i] !== nz[i - 1]) signChanges++;
  const dts = track.map((t) => t[2]);
  const mean = dts.reduce((x, y) => x + y, 0) / dts.length;
  const sd = Math.sqrt(dts.reduce((s, d) => s + (d - mean) ** 2, 0) / dts.length);
  return {
    events: track.length,
    durationS: dts.reduce((x, y) => x + y, 0) / 1000,
    distancePx: track.reduce((s, t) => s + t[0], 0),
    peakSpeedPos: peakPos,
    speedMax: Math.max(...vels.map(Math.abs)),
    signChanges,
    negDx: track.filter((t) => t[0] < 0).length,
    zeroDx: track.filter((t) => t[0] === 0).length,
    dtCv: sd / Math.max(mean, 1e-9),
  };
}

// ---- 质量门: 形态不达标就重生成 (最多 8 次) ----
function generateDragChecked(D, biasPx, rng) {
  for (let k = 0; k < 8; k++) {
    const track = generateDrag(D, biasPx, rng);
    const a = audit(track);
    // 峰值必须在中后段(前载=强机器指纹) + 必须有甩鞭速度 + 距离守恒
    if (a.peakSpeedPos >= 0.50 && a.speedMax >= 3000 &&
        Math.abs(a.distancePx - (D + biasPx)) <= 0.01) {
      return track;
    }
  }
  return generateDrag(D, biasPx, rng);   // 兜底
}

// ---- 组装完整事件流 (接近→按下→停顿→主轨迹→静止→松手) ----
function buildEvents(D, seed) {
  const rng = makeRng(seed != null ? seed : (Date.now() ^ (Math.random() * 0xffffffff)));
  const X0 = 348.0, Y0 = 96.0;
  const events = [];
  let t = 0.0;
  // 接近段
  const nApproach = rng.int(3, 6);
  const ax0 = X0 - rng.uniform(40, 120), ay0 = Y0 + rng.uniform(-25, 25);
  for (let i = 0; i < nApproach; i++) {
    const u = (i + 1) / nApproach;
    t += rng.uniform(18, 55);
    events.push({ dt: Math.round(t * 1000) / 1000, ty: "mousemove",
                  x: Math.round((ax0 + (X0 - ax0) * u) * 1000) / 1000,
                  y: Math.round((ay0 + (Y0 - ay0) * u + rng.uniform(-1.5, 1.5)) * 1000) / 1000 });
  }
  // 按下 + 反应停顿
  t += rng.uniform(15, 40);
  events.push({ dt: Math.round(t * 1000) / 1000, ty: "mousedown", x: X0, y: Y0 });
  t += rng.uniform(50, 110);
  // 主轨迹 (全浮点, 不取整!)
  const bias = rng.uniform(2.0, 4.0);
  const track = generateDragChecked(D, bias, rng);
  let x = X0, y = Y0;
  for (const [dx, dy, dtMs] of track) {
    t += dtMs; x += dx; y += dy;
    events.push({ dt: Math.round(t * 1000) / 1000, ty: "mousemove",
                  x: Math.round(x * 10000) / 10000, y: Math.round(y * 10000) / 10000 });
  }
  // 松手前静止
  const nStill = rng.int(1, 3);
  for (let k = 0; k < nStill; k++) {
    t += rng.uniform(30, 90);
    events.push({ dt: Math.round(t * 1000) / 1000, ty: "mousemove",
                  x: Math.round(x * 10000) / 10000, y: Math.round(y * 10000) / 10000 });
  }
  // mouseup
  t += rng.uniform(8, 25);
  events.push({ dt: Math.round(t * 1000) / 1000, ty: "mouseup",
                x: Math.round(x * 1000) / 1000, y: Math.round(y * 1000) / 1000 });
  return { events, track };
}

module.exports = { generateDrag, generateDragChecked, buildEvents, audit, makeRng };

// CLI 审计: node trackGen.js [D]
if (require.main === module) {
  const D = parseFloat(process.argv[2] || process.env.D || "712");
  const seed = process.env.SEED ? parseInt(process.env.SEED) : undefined;
  const { events, track } = buildEvents(D, seed);
  const a = audit(track);
  console.log(`轨迹: ${events.length} 事件 ${a.durationS.toFixed(2)}s 位移 ${a.distancePx.toFixed(0)}px`);
  console.log(`  峰值速度位置: ${a.peakSpeedPos.toFixed(2)}  (真人 0.75)`);
  console.log(`  峰值速度:     ${a.speedMax.toFixed(0)} px/s  (真人 9722)`);
  console.log(`  加减速切换:   ${a.signChanges}  (真人 ~25)`);
  console.log(`  负dx: ${a.negDx}  零dx: ${a.zeroDx}  dt_cv: ${a.dtCv.toFixed(2)}  (真人 2.7)`);
}
