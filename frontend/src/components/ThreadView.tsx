/**
 * ThreadView.tsx —— 用 assistant-ui 原语组件组装的聊天区
 *
 * 为什么不用 styled 的 <Thread>：@assistant-ui/react-ui 0.2.1 与
 * @assistant-ui/react 0.15.38 导出不兼容（官方包自身版本错位）。
 * 原语（ThreadPrimitive/MessagePrimitive/ComposerPrimitive）是稳定 API，
 * 自己组装反而可控，样式完全 Tailwind 自持。
 */
import {
  ThreadPrimitive,
  MessagePrimitive,
  ComposerPrimitive,
} from "@assistant-ui/react";

/** 用户消息：绿色气泡右对齐 */
function UserMessage() {
  return (
    <MessagePrimitive.Root
      data-role="user"
      className="flex justify-end px-2 py-1"
    >
      <div className="aui-thread-message-content max-w-[85%] sm:max-w-[75%]
                      bg-emerald-600 text-white rounded-2xl rounded-br-md px-4 py-2">
        <MessagePrimitive.Content components={{ Text: undefined }} />
      </div>
    </MessagePrimitive.Root>
  );
}

/** 助手消息：无气泡平铺（长回答/代码更好读） */
function AssistantMessage() {
  return (
    <MessagePrimitive.Root data-role="assistant" className="px-2 py-1">
      <div className="aui-thread-message-content text-zinc-800 dark:text-zinc-200">
        <MessagePrimitive.Content components={{ Text: undefined }} />
      </div>
    </MessagePrimitive.Root>
  );
}

export function ThreadView() {
  return (
    <ThreadPrimitive.Root className="flex h-full flex-col min-w-0">
      {/* 消息滚动区：autoScroll 自动吸底 */}
      <ThreadPrimitive.Viewport autoScroll
        className="aui-thread-viewport flex-1 min-h-0 overflow-y-auto">
        <ThreadPrimitive.Messages
          components={{ UserMessage, AssistantMessage }}
        />
        <ThreadPrimitive.If running={false}>
          <ThreadPrimitive.Empty>
            <div className="py-16 text-center text-zinc-400 text-sm">
              <p className="text-2xl mb-2">👋</p>
              <p>你好呀主人～小凡在这里待命啦！</p>
              <p className="mt-1 text-xs">查资料 / 搜网页 / 写文件 / 画画 / 聊天都可以</p>
            </div>
          </ThreadPrimitive.Empty>
        </ThreadPrimitive.If>
      </ThreadPrimitive.Viewport>

      {/* 输入区：移动端贴底自适应 */}
      <div className="border-t border-zinc-200 dark:border-zinc-800 p-2 sm:p-3">
        <ComposerPrimitive.Root
          className="flex items-end gap-2 rounded-2xl border border-zinc-300
                     dark:border-zinc-700 bg-white dark:bg-zinc-900 p-2">
          <ComposerPrimitive.Input
            rows={1}
            autoFocus
            placeholder="输入你的问题…（Enter 发送 / Shift+Enter 换行）"
            className="flex-1 resize-none bg-transparent outline-none
                       text-sm px-2 py-1.5 max-h-32 text-zinc-900 dark:text-zinc-100
                       placeholder:text-zinc-400"
          />
          {/* 运行中显示停止按钮，空闲显示发送按钮 */}
          <ThreadPrimitive.If running>
            <ComposerPrimitive.Cancel
              className="rounded-xl bg-zinc-200 dark:bg-zinc-700 text-zinc-700 dark:text-zinc-200
                         px-3 py-2 text-sm hover:opacity-80 shrink-0">
              ⏹ 停止
            </ComposerPrimitive.Cancel>
          </ThreadPrimitive.If>
          <ThreadPrimitive.If running={false}>
            <ComposerPrimitive.Send
              className="rounded-xl bg-emerald-600 text-white px-3 py-2 text-sm
                         hover:bg-emerald-700 disabled:opacity-40 shrink-0">
              ➤ 发送
            </ComposerPrimitive.Send>
          </ThreadPrimitive.If>
        </ComposerPrimitive.Root>
      </div>
    </ThreadPrimitive.Root>
  );
}
