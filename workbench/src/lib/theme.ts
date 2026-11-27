const STORAGE_KEY = "xiaofan-workbench-theme";

export function applyWorkbenchTheme(theme: string): void {
  const value = theme.trim();
  const root = document.documentElement;
  if (value) root.dataset.wbTheme = value;
  else delete root.dataset.wbTheme;
  try {
    localStorage.setItem(STORAGE_KEY, value);
  } catch {
    // ignore
  }
}

export function restoreWorkbenchTheme(): void {
  try {
    // 旧页是主题的唯一来源；没设置过时才回退到工作台自己的缓存
    const legacy = localStorage.getItem("aria.theme");
    const value = legacy !== null ? legacy : localStorage.getItem(STORAGE_KEY) ?? "";
    if (value) document.documentElement.dataset.wbTheme = value;
    else delete document.documentElement.dataset.wbTheme;
  } catch {
    // ignore
  }
}
