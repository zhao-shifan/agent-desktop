/**
 * 旧页的外观状态（主题 / 壁纸 / 我的照片 / 照片漂浮）。
 *
 * 工作台和 /legacy/chat.html 同源，旧页把这几项存在 localStorage 的 aria.* 键里。
 * 父页面直接读取，并通过 storage 事件跟随旧页里的每一次切换，不复制旧页的表单。
 */

export type WallpaperMode = "smart" | "cover" | "contain";

export interface WorkbenchAppearance {
  theme: string;
  bgImage: string;
  bgMode: WallpaperMode;
  photoRain: boolean;
}

const WORKBENCH_THEME_KEY = "xiaofan-workbench-theme";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function normalizeMode(value: string | null): WallpaperMode {
  return value === "cover" || value === "contain" ? value : "smart";
}

export function readAppearance(): WorkbenchAppearance {
  const legacyTheme = read("aria.theme");
  return {
    // 旧页把「鎏金墨黑」存成空字符串，必须用 null 区分「没设置过」
    theme: legacyTheme !== null ? legacyTheme : read(WORKBENCH_THEME_KEY) ?? "",
    bgImage: read("aria.bgImage") ?? "",
    bgMode: normalizeMode(read("aria.bgMode")),
    photoRain: read("aria.photoRain") === "1",
  };
}

export function sameAppearance(
  a: WorkbenchAppearance,
  b: WorkbenchAppearance,
): boolean {
  return (
    a.theme === b.theme &&
    a.bgImage === b.bgImage &&
    a.bgMode === b.bgMode &&
    a.photoRain === b.photoRain
  );
}

export interface WallpaperManifest {
  ids: number[];
  cards: number[];
}

export async function loadWallpaperManifest(): Promise<WallpaperManifest> {
  try {
    const response = await fetch("/wallpapers/manifest.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(`manifest ${response.status}`);
    const raw = (await response.json()) as Partial<WallpaperManifest>;
    return {
      ids: Array.isArray(raw.ids) ? raw.ids.filter((id) => Number.isFinite(id)) : [],
      cards: Array.isArray(raw.cards) ? raw.cards.filter((id) => Number.isFinite(id)) : [],
    };
  } catch {
    return {
      ids: Array.from({ length: 25 }, (_, index) => index + 1),
      cards: Array.from({ length: 40 }, (_, index) => index + 1),
    };
  }
}
