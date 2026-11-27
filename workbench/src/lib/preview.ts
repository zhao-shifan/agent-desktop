import type { PreviewFile, PreviewKind, PreviewSpec, TreeNode } from "../types/workbench";

const IMAGE_EXT = new Set([
  "png",
  "jpg",
  "jpeg",
  "webp",
  "gif",
  "bmp",
  "svg",
  "avif",
  "ico",
]);

const TEXT_EXT = new Set([
  "txt",
  "md",
  "markdown",
  "json",
  "jsonc",
  "js",
  "jsx",
  "ts",
  "tsx",
  "css",
  "scss",
  "less",
  "html",
  "htm",
  "xml",
  "yml",
  "yaml",
  "toml",
  "ini",
  "log",
  "py",
  "sh",
  "ps1",
  "bat",
  "sql",
  "go",
  "rs",
  "java",
  "c",
  "h",
  "cpp",
  "hpp",
  "vue",
  "svelte",
]);

export function extOf(path: string): string {
  const clean = path.split("?")[0].split("#")[0];
  const name = clean.replace(/\\/g, "/").split("/").pop() ?? clean;
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index + 1).toLowerCase() : "";
}

/** 后缀 → 预览组件类型（工作台唯一的匹配入口）；node.ext 优先于路径后缀 */
export function resolvePreviewKind(path: string, extHint?: string): PreviewKind {
  const ext = (extHint || extOf(path)).toLowerCase();
  if (ext === "docx" || ext === "doc") return "docx";
  if (ext === "pptx" || ext === "ppt") return "pptx";
  if (ext === "pdf") return "pdf";
  if (IMAGE_EXT.has(ext)) return "image";
  if (ext === "xlsx" || ext === "xls" || ext === "csv" || ext === "tsv") return "sheet";
  if (ext === "diff" || ext === "patch") return "diff";
  if (TEXT_EXT.has(ext)) return "text";
  return "unknown";
}

export function fileNameOf(path: string): string {
  return path.replace(/\\/g, "/").split("/").pop() || path;
}

export function formatBytes(size?: number): string {
  if (!size || size <= 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

export function previewFromFile(
  file: {
    path: string;
    name?: string;
    url?: string;
    size?: number;
    mime?: string;
    ext?: string;
  },
  key?: string,
): PreviewSpec | null {
  const kind = resolvePreviewKind(file.path, file.ext);
  if (kind === "unknown") return null;
  const previewFile: PreviewFile = {
    path: file.path,
    name: file.name || fileNameOf(file.path),
    url: file.url,
    size: file.size,
    mime: file.mime,
    ext: (file.ext || extOf(file.path)).toLowerCase(),
  };
  return {
    kind,
    title: previewFile.name,
    file: previewFile,
    key: key ?? `file:${file.path}`,
  };
}

export function previewFromNode(node: TreeNode): PreviewSpec | null {
  if (node.kind !== "file") return null;
  const spec = previewFromFile(
    {
      path: node.path || node.url || node.name,
      name: node.name,
      url: node.url,
      size: node.size,
      mime: node.mime,
      ext: node.ext,
    },
    node.id,
  );
  if (!spec) return null;
  return { ...spec, title: node.name };
}

/**
 * 极简行级 diff（用于外部 API 传 oldText/newText 的场景）。
 * 生成单个 hunk，diff2html 会自己做 word/line 高亮。
 */
export function createUnifiedDiff(
  oldText: string,
  newText: string,
  fileName = "file.txt",
): string {
  const oldLines = oldText.replace(/\r\n/g, "\n").split("\n");
  const newLines = newText.replace(/\r\n/g, "\n").split("\n");
  if (oldText === newText) return "";

  const n = oldLines.length;
  const m = newLines.length;
  // 为超大文本留保护，避免 DP 表爆炸
  if (n * m > 4_000_000) {
    return [
      `--- a/${fileName}`,
      `+++ b/${fileName}`,
      `@@ -1,${n} +1,${m} @@`,
      ...oldLines.map((line) => `-${line}`),
      ...newLines.map((line) => `+${line}`),
    ].join("\n");
  }

  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] =
        oldLines[i] === newLines[j]
          ? dp[i + 1][j + 1] + 1
          : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const ops: Array<{ type: " " | "-" | "+"; line: string }> = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (oldLines[i] === newLines[j]) {
      ops.push({ type: " ", line: oldLines[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ type: "-", line: oldLines[i] });
      i++;
    } else {
      ops.push({ type: "+", line: newLines[j] });
      j++;
    }
  }
  while (i < n) ops.push({ type: "-", line: oldLines[i++] });
  while (j < m) ops.push({ type: "+", line: newLines[j++] });

  return [
    `--- a/${fileName}`,
    `+++ b/${fileName}`,
    `@@ -1,${n} +1,${m} @@`,
    ...ops.map((op) => `${op.type}${op.line}`),
  ].join("\n");
}
