import { useEffect, useMemo, useRef, useState } from "react";
import {
  DockviewReact,
  type DockviewReadyEvent,
  type DockviewTheme,
  type IDockviewPanelHeaderProps,
} from "dockview-react";
import { useDroppable } from "@dnd-kit/core";
import type { PreviewSpec } from "../types/workbench";
import { useWorkbench } from "../store/workbench";
import {
  attachDockview,
  closeAllTabs,
  detachDockview,
  openSampleDiff,
  openTerminal,
  resetLayout,
} from "../lib/dockController";
import { extOf } from "../lib/preview";
import { PreviewPanel } from "./Previews/PreviewPanel";
import {
  CloseIcon,
  DiffIcon,
  FileTypeIcon,
  LayoutIcon,
  PanelIcon,
  TerminalIcon,
} from "./Icons";

const wbTheme: DockviewTheme = {
  name: "wb",
  className: "wb-dv-theme",
  colorScheme: "dark",
  gap: 0,
  dndOverlayMounting: "absolute",
  dndPanelOverlay: "group",
  dndTabIndicator: "line",
  tabAnimation: "smooth",
  tabGroupIndicator: "none",
  dndOverlayBorder: "1px solid var(--wb-accent)",
};

const components = { preview: PreviewPanel };

function tabIcon(spec?: PreviewSpec) {
  if (!spec) return <FileTypeIcon size={13} />;
  if (spec.kind === "terminal") return <TerminalIcon size={13} />;
  if (spec.kind === "diff") return <DiffIcon size={13} />;
  return <FileTypeIcon ext={extOf(spec.file?.path ?? spec.title)} size={13} />;
}

function DockTab({ api, params }: IDockviewPanelHeaderProps<{ preview?: PreviewSpec }>) {
  const [title, setTitle] = useState(api.title || "预览");
  const spec = params?.preview;

  useEffect(() => {
    const disposable = api.onDidTitleChange((event) => setTitle(event.title));
    return () => disposable.dispose();
  }, [api]);

  return (
    <div
      className="wb-dv-tab"
      data-kind={spec?.kind}
      onAuxClick={(event) => {
        if (event.button === 1) {
          event.preventDefault();
          api.close();
        }
      }}
    >
      <span className="wb-dv-tab-icon">{tabIcon(spec)}</span>
      <span className="wb-dv-tab-title" title={title}>
        {title}
      </span>
      <button
        type="button"
        className="wb-dv-tab-close"
        title="关闭标签"
        onMouseDown={(event) => {
          event.preventDefault();
          event.stopPropagation();
        }}
        onPointerDown={(event) => {
          event.stopPropagation();
        }}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          api.close();
        }}
      >
        <CloseIcon size={11} />
      </button>
    </div>
  );
}

function DockWatermark() {
  return (
    <div className="wb-dock-empty">
      <div className="wb-dock-empty-mark">◫</div>
      <h3>预览停靠区</h3>
      <p>
        点击左侧文件节点自动新建 Tab；也可以把文件节点直接拖到这里。
        <br />
        拖动 Tab 到面板边缘可拆分布局，布局会自动保存。
      </p>
      <div className="wb-dock-empty-actions">
        <button type="button" className="wb-btn" onClick={() => openTerminal()}>
          <TerminalIcon size={14} /> 打开终端
        </button>
        <button type="button" className="wb-btn wb-btn--ghost" onClick={() => openSampleDiff()}>
          <DiffIcon size={14} /> 示例 Diff
        </button>
      </div>
    </div>
  );
}

export function DockHost() {
  const rightOpen = useWorkbench((state) => state.rightOpen);
  const setRightOpen = useWorkbench((state) => state.setRightOpen);
  const [count, setCount] = useState(0);
  const disposables = useRef<Array<{ dispose: () => void }>>([]);
  const { setNodeRef, isOver } = useDroppable({ id: "preview-drop" });

  const onReady = (event: DockviewReadyEvent) => {
    attachDockview(event.api);
    setCount(event.api.panels.length);
    disposables.current.push(
      event.api.onDidAddPanel(() => setCount(event.api.panels.length)),
      event.api.onDidRemovePanel(() => setCount(event.api.panels.length)),
      event.api.onDidLayoutFromJSON(() => setCount(event.api.panels.length)),
    );
  };

  useEffect(() => {
    return () => {
      for (const disposable of disposables.current.splice(0, disposables.current.length)) {
        disposable.dispose();
      }
      detachDockview();
    };
  }, []);

  const theme = useMemo(() => wbTheme, []);

  return (
    <section className={`wb-right ${rightOpen ? "is-open" : "is-collapsed"}`}>
      <div className="wb-panel-head wb-right-head">
        <div className="wb-panel-title">
          <span className="wb-panel-kicker">DOCKVIEW</span>
          <strong>预览</strong>
          <span className="wb-panel-count">{count}</span>
        </div>
        <div className="wb-right-actions">
          <button type="button" className="wb-icon-btn" title="打开终端" onClick={() => openTerminal()}>
            <TerminalIcon size={15} />
          </button>
          <button type="button" className="wb-icon-btn" title="示例 Diff" onClick={() => openSampleDiff()}>
            <DiffIcon size={15} />
          </button>
          <button type="button" className="wb-icon-btn" title="重置布局" onClick={() => resetLayout()}>
            <LayoutIcon size={15} />
          </button>
          <button
            type="button"
            className="wb-icon-btn"
            title="关闭全部 Tab"
            onClick={() => closeAllTabs()}
          >
            <CloseIcon size={15} />
          </button>
          <button
            type="button"
            className="wb-icon-btn"
            title="收起面板"
            onClick={() => setRightOpen(false)}
          >
            <PanelIcon size={15} />
          </button>
        </div>
      </div>

      <div ref={setNodeRef} className={`wb-dock-wrap ${isOver ? "is-drop-over" : ""}`}>
        <DockviewReact
          components={components}
          defaultTabComponent={DockTab}
          watermarkComponent={DockWatermark}
          onReady={onReady}
          theme={theme}
          className="wb-dockview"
        />
        {isOver ? (
          <div className="wb-dock-drop-hint">
            <span>释放以在右侧打开预览</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}
