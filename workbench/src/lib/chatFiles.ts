/**
 * 聊天里生成的文件（blob）登记表。
 *
 * 旧聊天页把生成的 docx / xlsx / pdf 放在 iframe 的 `fileBlobs` 里，父窗口拿不到内存；
 * 桥会把 Blob 用 postMessage 结构克隆传过来，这里把它变成 ObjectURL 供 dockview 预览。
 *
 * 注意：ObjectURL 只在当前页面会话内有效，刷新后需要旧页重新生成一次文件。
 */
const urls = new Map<string, { url: string; blob: Blob }>();

export function registerChatBlob(fileId: string, blob: Blob): string {
  const existing = urls.get(fileId);
  // 同一个文件名重新生成时 blob 是新的，旧 ObjectURL 必须换掉
  if (existing) URL.revokeObjectURL(existing.url);
  const url = URL.createObjectURL(blob);
  urls.set(fileId, { url, blob });
  return url;
}

export function getChatBlobUrl(fileId: string): string | undefined {
  return urls.get(fileId)?.url;
}

export function getChatBlob(fileId: string): Blob | undefined {
  return urls.get(fileId)?.blob;
}

export function releaseChatBlob(fileId: string): void {
  const existing = urls.get(fileId);
  if (!existing) return;
  URL.revokeObjectURL(existing.url);
  urls.delete(fileId);
}

/** 聊天文件在树里的稳定 id：同一会话内同名文件视为同一个产物 */
export function chatFileId(chatId: string, name: string): string {
  return `${chatId}:${name}`;
}
