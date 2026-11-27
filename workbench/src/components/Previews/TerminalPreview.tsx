import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import type { TerminalInput } from "../../types/workbench";
import { PreviewToolbar } from "./PreviewParts";

const SHELL = "~/xiaofan";
const PROMPT = `\x1b[38;2;226;184;87m${SHELL}\x1b[0m \x1b[38;2;242;212;146m$\x1b[0m `;

const SAMPLE_FILES = [
  "samples/product-spec.docx",
  "samples/quarterly-review.pptx",
  "samples/tech-plan.pdf",
  "samples/design.png",
  "samples/sales-data.xlsx",
  "samples/code-review.diff",
  "samples/README.md",
];

function writeBanner(term: Terminal, cwd: string) {
  term.write(
    "\x1b[38;2;226;184;87m✦ 小凡工作台 · 网页终端\x1b[0m\r\n" +
      "\x1b[38;2;152;147;138m演示模式：未接入后端 PTY，输入 \x1b[38;2;242;212;146mhelp\x1b[38;2;152;147;138m 查看命令。\x1b[0m\r\n" +
      `\x1b[38;2;103;99;89m工作目录：${cwd} · 真实终端可通过 openTerminal({ wsUrl }) 接入\x1b[0m\r\n\r\n`,
  );
  term.write(PROMPT);
}

export function TerminalPreview({ terminal }: { terminal?: TerminalInput }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<"local" | "connecting" | "online" | "offline">(
    terminal?.wsUrl ? "connecting" : "local",
  );
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: "bar",
      convertEol: true,
      fontFamily: '"JetBrains Mono", "SFMono-Regular", Consolas, monospace',
      fontSize: 13,
      lineHeight: 1.35,
      letterSpacing: 0.2,
      scrollback: 6000,
      theme: {
        background: "#0f1014",
        foreground: "#d9d4c8",
        cursor: "#e2b857",
        cursorAccent: "#0f1014",
        selectionBackground: "rgba(226, 184, 87, 0.26)",
        black: "#17181d",
        red: "#e07a6a",
        green: "#8fc99a",
        yellow: "#e2b857",
        blue: "#7fa8e8",
        magenta: "#c39be8",
        cyan: "#7bc8c0",
        white: "#ece8df",
        brightBlack: "#676359",
        brightRed: "#f09a8b",
        brightGreen: "#a8dcb2",
        brightYellow: "#f2d492",
        brightBlue: "#9dc0f2",
        brightMagenta: "#d8b8f2",
        brightCyan: "#9adbd4",
        brightWhite: "#fffdf8",
      },
    });
    termRef.current = term;

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(host);
    const safeFit = () => {
      try {
        fitAddon.fit();
      } catch {
        // 面板隐藏时宽高为 0，忽略即可
      }
    };
    const raf = window.requestAnimationFrame(safeFit);

    const cwd = terminal?.cwd || SHELL;
    let buffer = "";
    let ws: WebSocket | null = null;
    let disposed = false;

    const prompt = () => term.write(PROMPT);

    const runCommand = (raw: string) => {
      const input = raw.trim();
      if (!input) {
        prompt();
        return;
      }
      const [command, ...rest] = input.split(/\s+/);
      const arg = rest.join(" ");
      switch (command) {
        case "help":
          term.write(
            "\x1b[38;2;242;212;146m可用命令\x1b[0m\r\n" +
              "  help              查看帮助\r\n" +
              "  ls                列出示例文件\r\n" +
              "  pwd               显示当前目录\r\n" +
              "  date              当前时间\r\n" +
              "  echo <text>       回显文本\r\n" +
              "  open <path>       用工作台右侧打开预览\r\n" +
              "  clear             清屏\r\n" +
              "  whoami            当前用户\r\n" +
              "  exit              退出（演示模式无进程）\r\n",
          );
          break;
        case "ls":
          term.write(
            SAMPLE_FILES.map(
              (file) =>
                `  \x1b[38;2;127;168;232m${file}\x1b[0m  \x1b[38;2;103;99;89m${file
                  .split(".")
                  .pop()}\x1b[0m`,
            ).join("\r\n") + "\r\n",
          );
          break;
        case "pwd":
          term.write(`${cwd}\r\n`);
          break;
        case "date":
          term.write(`${new Date().toLocaleString("zh-CN")}\r\n`);
          break;
        case "echo":
          term.write(`${arg}\r\n`);
          break;
        case "whoami":
          term.write("workbench\r\n");
          break;
        case "open": {
          if (!arg) {
            term.write("\x1b[38;2;224;122;106m用法：open samples/design.png\x1b[0m\r\n");
            break;
          }
          const file = arg.replace(/^\/+/, "");
          window.xiaofanWorkbench?.openFile({
            path: file,
            name: file.split("/").pop(),
            url: `/${file}`,
          });
          term.write(`\x1b[38;2;143;201;154m已发送到右侧预览：${file}\x1b[0m\r\n`);
          break;
        }
        case "clear":
          term.clear();
          break;
        case "exit":
          term.write("演示终端没有可退出的进程。\r\n");
          break;
        default:
          term.write(`\x1b[38;2;224;122;106mcommand not found:\x1b[0m ${command}\r\n`);
      }
      prompt();
    };

    term.onData((data) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(data);
        return;
      }
      if (ws) {
        term.write("\x1b[38;2;224;122;106m[终端未连接]\x1b[0m\r\n");
        return;
      }
      for (const char of data) {
        if (char === "\r" || char === "\n") {
          term.write("\r\n");
          runCommand(buffer);
          buffer = "";
          continue;
        }
        if (char === "\x7f") {
          if (buffer.length) {
            buffer = buffer.slice(0, -1);
            term.write("\b \b");
          }
          continue;
        }
        if (char === "\x03") {
          term.write("^C\r\n");
          buffer = "";
          prompt();
          continue;
        }
        if (char === "\x1b" || char.charCodeAt(0) < 32) continue;
        buffer += char;
        term.write(char);
      }
    });

    if (!terminal?.wsUrl) {
      writeBanner(term, cwd);
      setStatus("local");
    } else {
      try {
        ws = new WebSocket(terminal.wsUrl);
        wsRef.current = ws;
        ws.onopen = () => {
          if (disposed) return;
          setStatus("online");
          term.write(`\x1b[38;2;143;201;154m已连接 PTY：${terminal.wsUrl}\x1b[0m\r\n`);
        };
        ws.onmessage = (event) => {
          if (typeof event.data === "string") term.write(event.data);
          else term.write(new Uint8Array(event.data as ArrayBuffer));
        };
        ws.onerror = () => {
          if (disposed) return;
          setStatus("offline");
          term.write("\x1b[38;2;224;122;106mPTY 连接失败，可点右上角重新连接。\x1b[0m\r\n");
        };
        ws.onclose = () => {
          if (disposed) return;
          setStatus("offline");
          term.write("\r\n\x1b[38;2;103;99;89m[连接已断开]\x1b[0m\r\n");
        };
      } catch (error) {
        setStatus("offline");
        term.write(`\x1b[38;2;224;122;106mWebSocket 地址无效：${String(error)}\x1b[0m\r\n`);
      }
    }

    const observer = new ResizeObserver(() => safeFit());
    observer.observe(host);

    return () => {
      disposed = true;
      window.cancelAnimationFrame(raf);
      observer.disconnect();
      ws?.close();
      wsRef.current = null;
      term.dispose();
      termRef.current = null;
    };
  }, [terminal?.wsUrl, terminal?.cwd, generation]);

  return (
    <div className="wb-preview wb-terminal-preview">
      <PreviewToolbar>
        <span className="wb-preview-file">
          <span className="wb-preview-ext">TERM</span>
          网页终端
        </span>
        <span className={`wb-term-status is-${status}`}>
          {status === "local"
            ? "演示模式"
            : status === "connecting"
              ? "连接中"
              : status === "online"
                ? "已连接"
                : "已断开"}
        </span>
        <span className="wb-preview-spacer" />
        <button
          type="button"
          className="wb-btn wb-btn--ghost"
          onClick={() => termRef.current?.clear()}
        >
          清屏
        </button>
        <button
          type="button"
          className="wb-btn wb-btn--ghost"
          onClick={() => setGeneration((value) => value + 1)}
        >
          重连 / 重置
        </button>
      </PreviewToolbar>
      <div className="wb-preview-stage wb-terminal-stage">
        <div ref={hostRef} className="wb-terminal-host" />
      </div>
    </div>
  );
}
