import { useCallback, useEffect, useState } from "react";
import { probeLegacyPage } from "../../lib/legacy";
import { useWorkbench } from "../../store/workbench";
import type { LegacyPageKey } from "../../types/workbench";

export function useLegacyAvailability(url: string, page: LegacyPageKey) {
  const [status, setStatus] = useState<"checking" | "ready" | "missing">("checking");
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setStatus("checking");
    useWorkbench.getState().setLegacyStatus(page, "checking");
    probeLegacyPage(url)
      .then((result) => {
        if (!alive) return;
        setStatus(result);
        useWorkbench.getState().setLegacyStatus(page, result);
      })
      .catch(() => {
        if (!alive) return;
        setStatus("missing");
        useWorkbench.getState().setLegacyStatus(page, "missing");
      });
    return () => {
      alive = false;
    };
  }, [url, page, nonce]);

  const recheck = useCallback(() => setNonce((value) => value + 1), []);
  return { status, recheck };
}
