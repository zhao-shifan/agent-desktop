import { useEffect, useRef, useState } from "react";
import {
  Group,
  Panel,
  Separator,
  type PanelImperativeHandle,
} from "react-resizable-panels";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  pointerWithin,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { TopBar } from "./components/TopBar";
import { WorkbenchBackdrop } from "./components/WorkbenchBackdrop";
import { TreePanel } from "./components/TreePanel";
import { CenterPanel } from "./components/Center/CenterPanel";
import { DockHost } from "./components/DockHost";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { FileTypeIcon, CloseIcon } from "./components/Icons";
import { useWorkbench } from "./store/workbench";
import { openFileNode } from "./lib/dockController";
import { installLegacyMessageBridge, installWorkbenchApi } from "./lib/expose";
import type { TreeNode } from "./types/workbench";
import { extOf } from "./lib/preview";

export default function App() {
  const rightOpen = useWorkbench((state) => state.rightOpen);
  const toast = useWorkbench((state) => state.toast);
  const clearToast = useWorkbench((state) => state.clearToast);
  const rightRef = useRef<PanelImperativeHandle | null>(null);
  const [dragFile, setDragFile] = useState<TreeNode | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    }),
  );

  useEffect(() => {
    installWorkbenchApi();
    return installLegacyMessageBridge();
  }, []);

  useEffect(() => {
    const handle = rightRef.current;
    if (!handle) return;
    if (rightOpen) handle.expand();
    else handle.collapse();
  }, [rightOpen]);

  const handleDragStart = (event: DragStartEvent) => {
    const data = event.active.data.current as { file?: TreeNode } | undefined;
    if (data?.file) setDragFile(data.file);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const data = event.active.data.current as { file?: TreeNode } | undefined;
    setDragFile(null);
    if (event.over?.id === "preview-drop" && data?.file) {
      openFileNode(data.file);
    }
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={pointerWithin}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={() => setDragFile(null)}
    >
      <div className="wb-app">
        <WorkbenchBackdrop />
        <TopBar />
        <Group orientation="horizontal" className="wb-main">
          <Panel
            defaultSize="19%"
            minSize="238px"
            maxSize="30%"
            className="wb-panel wb-panel-left"
          >
            <TreePanel />
          </Panel>

          <Separator className="wb-sep">
            <span className="wb-sep-grip" />
          </Separator>

          <Panel defaultSize="51%" minSize="420px" className="wb-panel wb-panel-center">
            <CenterPanel />
          </Panel>

          <Separator
            className={`wb-sep wb-sep--collapsible ${rightOpen ? "" : "is-hidden"}`}
            disabled={!rightOpen}
          >
            <span className="wb-sep-grip" />
          </Separator>

          <Panel
            panelRef={rightRef}
            defaultSize="30%"
            minSize="340px"
            maxSize="52%"
            collapsible
            collapsedSize="0px"
            className="wb-panel wb-panel-right"
          >
            <DockHost />
          </Panel>
        </Group>

        {toast ? (
          <div className={`wb-toast is-${toast.tone}`} role="status">
            <span className="wb-toast-dot" />
            <span>{toast.message}</span>
            <button type="button" onClick={clearToast} title="关闭提示">
              <CloseIcon size={12} />
            </button>
          </div>
        ) : null}

        <ConfirmDialog />

        <DragOverlay dropAnimation={null}>
          {dragFile ? (
            <div className="wb-drag-chip">
              <FileTypeIcon ext={extOf(dragFile.path || dragFile.name)} size={14} />
              <span>{dragFile.name}</span>
            </div>
          ) : null}
        </DragOverlay>
      </div>
    </DndContext>
  );
}
