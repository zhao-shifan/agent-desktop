import { useEffect, useRef, useState } from "react";
import {
  readAppearance,
  sameAppearance,
  type WorkbenchAppearance,
} from "../lib/appearance";
import { createBackdropEffects, type BackdropEffects } from "../lib/backdropEffects";
import { applyWorkbenchTheme } from "../lib/theme";

type Fit = "cover" | "contain";

/**
 * 桌面背景层：旧页的主题动效、壁纸、自定义照片、照片漂浮都在这里渲染。
 * 旧页 iframe 只负责对话内容，背景统一由这层接管，所以三栏看到的是同一张壁纸。
 */
export function WorkbenchBackdrop() {
  const [appearance, setAppearance] = useState<WorkbenchAppearance>(() => readAppearance());
  const [fit, setFit] = useState<Fit>("cover");
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const effectsRef = useRef<BackdropEffects | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const effects = createBackdropEffects(canvas);
    effectsRef.current = effects;
    return () => {
      effects.dispose();
      effectsRef.current = null;
    };
  }, []);

  useEffect(() => {
    const refresh = () => {
      setAppearance((previous) => {
        const next = readAppearance();
        return sameAppearance(previous, next) ? previous : next;
      });
    };

    const handleStorage = (event: StorageEvent) => {
      if (!event.key || event.key.startsWith("aria.") || event.key === "xiaofan-workbench-theme") {
        refresh();
      }
    };
    const handleMessage = (event: MessageEvent) => {
      const data = event.data as
        | { __wb?: number; source?: string; type?: string; theme?: unknown }
        | null;
      if (!data || data.__wb !== 1 || data.source !== "chat" || data.type !== "theme") return;
      applyWorkbenchTheme(typeof data.theme === "string" ? data.theme : "");
      refresh();
    };

    window.addEventListener("storage", handleStorage);
    window.addEventListener("message", handleMessage);
    return () => {
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener("message", handleMessage);
    };
  }, []);

  useEffect(() => {
    applyWorkbenchTheme(appearance.theme);
    effectsRef.current?.setTheme(appearance.theme, appearance.photoRain);
  }, [appearance.theme, appearance.photoRain]);

  useEffect(() => {
    const root = document.documentElement;
    if (appearance.bgImage) root.dataset.wbWall = "1";
    else delete root.dataset.wbWall;
  }, [appearance.bgImage]);

  useEffect(() => {
    if (!appearance.bgImage) return;
    if (appearance.bgMode !== "smart") {
      setFit(appearance.bgMode);
      return;
    }

    let cancelled = false;
    const image = new Image();
    image.onload = () => {
      if (cancelled) return;
      const screenRatio = window.innerWidth / Math.max(1, window.innerHeight);
      const imageRatio = image.naturalWidth / Math.max(1, image.naturalHeight);
      const close = Math.abs(imageRatio - screenRatio) / screenRatio < 0.08;
      setFit(close ? "cover" : "contain");
    };
    image.src = appearance.bgImage;
    return () => {
      cancelled = true;
      image.onload = null;
    };
  }, [appearance.bgImage, appearance.bgMode]);

  const hasWallpaper = Boolean(appearance.bgImage);

  return (
    <div className="wb-backdrop" aria-hidden="true" data-has-wall={hasWallpaper ? "1" : "0"}>
      {hasWallpaper ? (
        fit === "contain" ? (
          <>
            <div
              className="wb-backdrop-blur"
              style={{ backgroundImage: `url("${appearance.bgImage}")` }}
            />
            <img className="wb-backdrop-img" src={appearance.bgImage} alt="" draggable={false} />
          </>
        ) : (
          <div
            className="wb-backdrop-cover"
            style={{ backgroundImage: `url("${appearance.bgImage}")` }}
          />
        )
      ) : null}
      {hasWallpaper ? <div className="wb-backdrop-dim" /> : null}
      <canvas ref={canvasRef} className="wb-backdrop-effects" />
    </div>
  );
}
