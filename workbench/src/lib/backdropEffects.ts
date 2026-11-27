/**
 * 主题动效 / 照片漂浮：从旧页 index.html 的 #meteors 引擎移植到工作台外壳。
 * 保留旧页的 10 套主题映射和粒子算法，只把画布尺寸改成适配整屏 + DPR。
 */
import { loadWallpaperManifest } from "./appearance";

export type BackdropEffectType =
  | "meteor"
  | "bubble"
  | "aurora"
  | "firefly"
  | "ember"
  | "petal"
  | "dust"
  | "cloud"
  | "leaf"
  | "photo";

interface EffectDefinition {
  type: BackdropEffectType;
  color: string;
}

interface Particle {
  type: BackdropEffectType;
  color: string;
  x: number;
  y: number;
  phase: number;
  seed: number;
  vx?: number;
  vy?: number;
  len?: number;
  life?: number;
  delay?: number;
  r?: number;
  sway?: number;
  amp?: number;
  speed?: number;
  width?: number;
  tw?: number;
  rot?: number;
  vr?: number;
  a?: number;
  img?: HTMLImageElement;
  scale?: number;
  alpha?: number;
  drift?: number;
}

export interface BackdropEffects {
  setTheme(theme: string, photoRain: boolean): void;
  dispose(): void;
}

const EFFECTS: Record<string, EffectDefinition> = {
  "": { type: "meteor", color: "242,212,146" },
  ocean: { type: "bubble", color: "120,190,255" },
  violet: { type: "aurora", color: "186,130,255" },
  forest: { type: "firefly", color: "170,255,190" },
  ember: { type: "ember", color: "255,150,90" },
  rose: { type: "petal", color: "255,150,180" },
  "light-warm": { type: "dust", color: "190,155,80" },
  "light-cool": { type: "cloud", color: "120,160,220" },
  "light-gray": { type: "dust", color: "110,110,140" },
  mint: { type: "leaf", color: "90,190,140" },
};

const COUNTS: Record<BackdropEffectType, number> = {
  meteor: 14,
  bubble: 26,
  aurora: 4,
  firefly: 34,
  ember: 30,
  petal: 22,
  dust: 46,
  cloud: 18,
  leaf: 20,
  photo: 0,
};

export function createBackdropEffects(canvas: HTMLCanvasElement): BackdropEffects {
  const rawContext = canvas.getContext("2d");
  if (!rawContext) {
    return { setTheme() {}, dispose() {} };
  }
  const ctx: CanvasRenderingContext2D = rawContext;

  let width = 0;
  let height = 0;
  let parts: Particle[] = [];
  let raf = 0;
  let currentTheme = "";
  let photoRainOn = false;
  let disposed = false;
  let photoImgs: HTMLImageElement[] = [];
  let photoPromise: Promise<HTMLImageElement[]> | null = null;
  let rainFallbackTimer = 0;

  const random = (a: number, b: number) => Math.random() * (b - a) + a;

  function resize(): void {
    width = window.innerWidth;
    height = window.innerHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.max(1, Math.floor(width * dpr));
    canvas.height = Math.max(1, Math.floor(height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function spawn(definition: EffectDefinition): Particle {
    const color = definition.color;
    const type = definition.type;
    const base: Particle = {
      type,
      color,
      x: random(0, width),
      y: random(0, height),
      phase: random(0, Math.PI * 2),
      seed: Math.random(),
    };

    switch (type) {
      case "meteor":
        return {
          ...base,
          vx: -random(2.5, 5),
          vy: random(2, 4),
          len: random(80, 180),
          life: 1,
          delay: random(0, 400),
        };
      case "bubble":
        return { ...base, r: random(2, 7), vy: -random(0.2, 0.7), sway: random(20, 50) };
      case "aurora":
        return {
          ...base,
          amp: random(40, 90),
          y: height * random(0.1, 0.45),
          speed: random(0.15, 0.4),
          width: random(60, 140),
        };
      case "firefly":
        return {
          ...base,
          r: random(1.5, 3),
          vx: random(-0.4, 0.4),
          vy: random(-0.3, 0.3),
          tw: random(0, 7),
        };
      case "ember":
        return { ...base, r: random(1, 2.6), vy: -random(0.6, 1.6), sway: random(15, 40) };
      case "petal":
        return {
          ...base,
          r: random(3, 6),
          vy: random(0.3, 0.9),
          rot: random(0, 7),
          vr: random(-0.02, 0.02),
          sway: random(25, 60),
        };
      case "dust":
        return { ...base, r: random(0.8, 2), vy: -random(0.05, 0.2), tw: random(0, 7) };
      case "cloud":
        return { ...base, r: random(40, 110), vy: -random(0.06, 0.18), a: random(0.03, 0.07) };
      case "leaf":
        return {
          ...base,
          r: random(3, 5.5),
          vy: random(0.3, 0.8),
          rot: random(0, 7),
          vr: random(-0.03, 0.03),
          sway: random(20, 50),
        };
      default:
        return base;
    }
  }

  function build(theme: string): void {
    currentTheme = theme;
    const definition = EFFECTS[theme] || EFFECTS[""];
    const count = COUNTS[definition.type] || 20;
    parts = [];
    for (let index = 0; index < count; index += 1) {
      parts.push(spawn(definition));
    }
  }

  function draw(particle: Particle): void {
    const light = currentTheme.startsWith("light");
    switch (particle.type) {
      case "meteor": {
        const vx = particle.vx || -3;
        const vy = particle.vy || 2;
        const gradient = ctx.createLinearGradient(
          particle.x,
          particle.y,
          particle.x + (particle.len || 100),
          particle.y - (particle.len || 100) * (vy / vx),
        );
        gradient.addColorStop(0, `rgba(${particle.color},${((particle.life || 1) * 0.85).toFixed(2)})`);
        gradient.addColorStop(1, "rgba(0,0,0,0)");
        ctx.strokeStyle = gradient;
        ctx.lineWidth = 1.6;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(particle.x, particle.y);
        ctx.lineTo(
          particle.x + (particle.len || 100),
          particle.y - (particle.len || 100) * (vy / vx),
        );
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, 1.5, 0, 7);
        ctx.fillStyle = `rgba(${particle.color},${particle.life || 1})`;
        ctx.fill();
        break;
      }
      case "bubble": {
        const sway = particle.sway || 30;
        ctx.beginPath();
        ctx.arc(particle.x + Math.sin(particle.phase) * sway * 0.4, particle.y, particle.r || 3, 0, 7);
        ctx.strokeStyle = `rgba(${particle.color},.35)`;
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(
          particle.x + Math.sin(particle.phase) * sway * 0.4 - (particle.r || 3) * 0.3,
          particle.y - (particle.r || 3) * 0.3,
          (particle.r || 3) * 0.25,
          0,
          7,
        );
        ctx.fillStyle = `rgba(${particle.color},.25)`;
        ctx.fill();
        break;
      }
      case "aurora": {
        const amp = particle.amp || 60;
        const gradient = ctx.createLinearGradient(0, particle.y - amp, 0, particle.y + amp);
        gradient.addColorStop(0, `rgba(${particle.color},0)`);
        gradient.addColorStop(
          0.5,
          `rgba(${particle.color},${(0.1 + 0.05 * Math.sin(particle.phase)).toFixed(3)})`,
        );
        gradient.addColorStop(1, `rgba(${particle.color},0)`);
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.moveTo(0, particle.y + amp);
        for (let x = 0; x <= width; x += 24) {
          ctx.lineTo(x, particle.y + Math.sin(x * 0.004 + particle.phase) * amp);
        }
        ctx.lineTo(width, particle.y - amp);
        ctx.closePath();
        ctx.fill();
        break;
      }
      case "firefly": {
        const alpha = 0.25 + 0.55 * Math.abs(Math.sin(particle.tw || 0));
        const radius = particle.r || 2;
        const gradient = ctx.createRadialGradient(
          particle.x,
          particle.y,
          0,
          particle.x,
          particle.y,
          radius * 4,
        );
        gradient.addColorStop(0, `rgba(${particle.color},${alpha.toFixed(2)})`);
        gradient.addColorStop(1, `rgba(${particle.color},0)`);
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, radius * 4, 0, 7);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, radius * 0.8, 0, 7);
        ctx.fillStyle = `rgba(${particle.color},${Math.min(1, alpha + 0.3)})`;
        ctx.fill();
        break;
      }
      case "ember": {
        const alpha = 0.5 + 0.4 * Math.sin(particle.phase * 2);
        ctx.beginPath();
        ctx.arc(
          particle.x + Math.sin(particle.phase) * (particle.sway || 20) * 0.3,
          particle.y,
          particle.r || 2,
          0,
          7,
        );
        ctx.fillStyle = `rgba(${particle.color},${alpha.toFixed(2)})`;
        ctx.fill();
        break;
      }
      case "petal":
      case "leaf": {
        ctx.save();
        ctx.translate(
          particle.x + Math.sin(particle.phase) * (particle.sway || 30) * 0.4,
          particle.y,
        );
        ctx.rotate(particle.rot || 0);
        ctx.fillStyle = `rgba(${particle.color},.4)`;
        ctx.beginPath();
        ctx.ellipse(0, 0, particle.r || 4, (particle.r || 4) * 0.5, 0, 0, 7);
        ctx.fill();
        ctx.restore();
        break;
      }
      case "dust": {
        const alpha = (0.2 + 0.3 * Math.abs(Math.sin(particle.tw || 0))) * (light ? 1.1 : 1);
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.r || 1, 0, 7);
        ctx.fillStyle = `rgba(${particle.color},${alpha.toFixed(2)})`;
        ctx.fill();
        break;
      }
      case "cloud": {
        const gradient = ctx.createRadialGradient(
          particle.x,
          particle.y,
          0,
          particle.x,
          particle.y,
          particle.r || 60,
        );
        gradient.addColorStop(0, `rgba(${particle.color},${particle.a || 0.05})`);
        gradient.addColorStop(1, `rgba(${particle.color},0)`);
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.r || 60, 0, 7);
        ctx.fill();
        break;
      }
      case "photo": {
        const image = particle.img;
        if (!image || !image.complete || !image.naturalWidth) break;
        const w = 84 * (particle.scale || 0.6);
        const h = (w * image.naturalHeight) / image.naturalWidth;
        ctx.save();
        ctx.globalAlpha = particle.alpha || 0.25;
        ctx.translate(
          particle.x + Math.sin(particle.phase) * (particle.sway || 50) * 0.5,
          particle.y,
        );
        ctx.rotate((particle.rot || 0) + Math.sin(particle.phase) * 0.1);
        ctx.shadowColor = "rgba(0,0,0,.3)";
        ctx.shadowBlur = 10;
        ctx.shadowOffsetY = 4;
        ctx.drawImage(image, -w / 2, -h / 2, w, h);
        ctx.restore();
        break;
      }
      default:
        break;
    }
  }

  function step(particle: Particle): boolean {
    particle.phase += 0.01;
    switch (particle.type) {
      case "meteor":
        if ((particle.delay || 0) > 0) {
          particle.delay = (particle.delay || 0) - 16;
          return false;
        }
        particle.x += particle.vx || -3;
        particle.y += particle.vy || 2;
        particle.life = (particle.life || 1) - 0.01;
        if ((particle.life || 0) <= 0 || particle.x < -200 || particle.y > height + 200) {
          const definition = EFFECTS[currentTheme] || EFFECTS[""];
          Object.assign(particle, spawn(definition));
          particle.delay = random(200, 2500);
        }
        return true;
      case "bubble":
        particle.y += particle.vy || -0.4;
        if (particle.y < -10) {
          particle.y = height + 10;
          particle.x = random(0, width);
        }
        return true;
      case "aurora":
        particle.phase += (particle.speed || 0.2) * 0.02;
        return true;
      case "firefly":
        particle.tw = (particle.tw || 0) + 0.04;
        particle.x += (particle.vx || 0) + Math.sin(particle.phase) * 0.3;
        particle.y += (particle.vy || 0) + Math.cos(particle.phase * 0.7) * 0.3;
        if (particle.x < 0 || particle.x > width) particle.vx = -(particle.vx || 0.2);
        if (particle.y < 0 || particle.y > height) particle.vy = -(particle.vy || 0.2);
        return true;
      case "ember":
        particle.y += particle.vy || -1;
        particle.phase += 0.02;
        if (particle.y < -10) {
          particle.y = height + 10;
          particle.x = random(0, width);
        }
        return true;
      case "petal":
      case "leaf":
        particle.y += particle.vy || 0.5;
        particle.rot = (particle.rot || 0) + (particle.vr || 0);
        particle.phase += 0.015;
        if (particle.y > height + 15) {
          particle.y = -15;
          particle.x = random(0, width);
        }
        return true;
      case "dust":
        particle.y += particle.vy || -0.1;
        particle.tw = (particle.tw || 0) + 0.02;
        if (particle.y < -5) {
          particle.y = height + 5;
          particle.x = random(0, width);
        }
        return true;
      case "cloud":
        particle.y += particle.vy || -0.1;
        if (particle.y < -(particle.r || 60)) {
          particle.y = height + (particle.r || 60);
          particle.x = random(0, width);
        }
        return true;
      case "photo":
        particle.y += particle.vy || 0.15;
        particle.rot = (particle.rot || 0) + (particle.vr || 0);
        particle.phase += 0.008;
        particle.x += particle.drift || 0;
        if (particle.y > height + 200) {
          particle.y = -220;
          particle.x = random(0, width);
        }
        if (particle.x < -160) particle.x = width + 120;
        if (particle.x > width + 160) particle.x = -120;
        return true;
      default:
        return true;
    }
  }

  function frame(): void {
    if (disposed) return;
    ctx.clearRect(0, 0, width, height);
    for (const particle of parts) {
      if (step(particle)) draw(particle);
    }
    raf = requestAnimationFrame(frame);
  }

  function stop(): void {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    window.clearTimeout(rainFallbackTimer);
  }

  function start(): void {
    if (raf || disposed) return;
    raf = requestAnimationFrame(frame);
  }

  function ensurePhotos(): Promise<HTMLImageElement[]> {
    if (photoImgs.length) return Promise.resolve(photoImgs);
    if (photoPromise) return photoPromise;

    photoPromise = loadWallpaperManifest()
      .then((manifest) =>
        Promise.all(
          manifest.cards.map(
            (id) =>
              new Promise<HTMLImageElement | null>((resolve) => {
                const image = new Image();
                image.onload = () => resolve(image);
                image.onerror = () => resolve(null);
                image.src = `/wallpapers/card${String(id).padStart(2, "0")}.jpg`;
              }),
          ),
        ),
      )
      .then((images) => {
        photoImgs = images.filter((image): image is HTMLImageElement => Boolean(image));
        return photoImgs;
      })
      .catch(() => []);

    return photoPromise;
  }

  function startPhotoRain(images: HTMLImageElement[]): void {
    if (!images.length || disposed) return;
    stop();
    parts = [];
    for (const image of images) {
      parts.push({
        type: "photo",
        color: "",
        img: image,
        x: random(0, width),
        y: random(-height, height),
        vy: random(0.08, 0.25),
        rot: random(-0.3, 0.3),
        vr: random(-0.005, 0.005),
        sway: random(35, 80),
        scale: random(0.45, 0.85),
        alpha: random(0.16, 0.42),
        drift: random(-0.12, 0.12),
        phase: random(0, Math.PI * 2),
        seed: Math.random(),
      });
    }
    start();
  }

  function setTheme(theme: string, photoRain: boolean): void {
    if (disposed) return;
    currentTheme = theme;
    photoRainOn = photoRain;
    stop();
    resize();

    if (photoRain) {
      ensurePhotos().then((images) => {
        if (!photoRainOn || disposed) return;
        if (images.length) startPhotoRain(images);
      });
      // 卡片图加载失败 / 太慢时，退回当前主题的普通动效，避免背景一直空白
      rainFallbackTimer = window.setTimeout(() => {
        if (photoRainOn && !parts.length && !disposed) {
          build(currentTheme);
          start();
        }
      }, 2400);
      return;
    }

    build(theme);
    start();
  }

  const handleResize = () => {
    if (disposed) return;
    stop();
    resize();
    if (photoRainOn && parts.length && parts[0]?.type === "photo") {
      startPhotoRain(photoImgs);
    } else {
      build(currentTheme);
      start();
    }
  };

  window.addEventListener("resize", handleResize);

  return {
    setTheme,
    dispose() {
      disposed = true;
      stop();
      window.removeEventListener("resize", handleResize);
      parts = [];
      photoImgs = [];
    },
  };
}
