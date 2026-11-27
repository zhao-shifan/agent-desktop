import { useCallback, useEffect, useState } from "react";

export type ResourceState<T> =
  | { status: "loading"; data: null; error: null }
  | { status: "ready"; data: T; error: null }
  | { status: "error"; data: null; error: string };

export function useBinaryResource(url?: string) {
  const [state, setState] = useState<ResourceState<ArrayBuffer>>(() =>
    url
      ? { status: "loading", data: null, error: null }
      : { status: "error", data: null, error: "文件缺少可预览的 URL" },
  );
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!url) {
      setState({ status: "error", data: null, error: "文件缺少可预览的 URL" });
      return;
    }
    const controller = new AbortController();
    setState({ status: "loading", data: null, error: null });
    fetch(url, { signal: controller.signal, credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`);
        return response.arrayBuffer();
      })
      .then((buffer) => {
        if (!controller.signal.aborted) {
          setState({ status: "ready", data: buffer, error: null });
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : String(error);
        setState({ status: "error", data: null, error: message });
      });
    return () => controller.abort();
  }, [url, tick]);

  const reload = useCallback(() => setTick((value) => value + 1), []);
  return { ...state, reload };
}

export function useTextResource(url?: string) {
  const [state, setState] = useState<ResourceState<string>>(() =>
    url
      ? { status: "loading", data: null, error: null }
      : { status: "error", data: null, error: "文件缺少可预览的 URL" },
  );
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!url) {
      setState({ status: "error", data: null, error: "文件缺少可预览的 URL" });
      return;
    }
    const controller = new AbortController();
    setState({ status: "loading", data: null, error: null });
    fetch(url, { signal: controller.signal, credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`);
        return response.text();
      })
      .then((text) => {
        if (!controller.signal.aborted) setState({ status: "ready", data: text, error: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : String(error);
        setState({ status: "error", data: null, error: message });
      });
    return () => controller.abort();
  }, [url, tick]);

  const reload = useCallback(() => setTick((value) => value + 1), []);
  return { ...state, reload };
}
