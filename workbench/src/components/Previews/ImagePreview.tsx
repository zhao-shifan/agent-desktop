import { PhotoProvider, PhotoView } from "react-photo-view";
import type { PreviewFile } from "../../types/workbench";
import { formatBytes } from "../../lib/preview";
import { PreviewToolbar } from "./PreviewParts";

export function ImagePreview({ file }: { file: PreviewFile }) {
  const url = file.url || file.path;

  return (
    <div className="wb-preview wb-image-preview">
      <PreviewToolbar>
        <span className="wb-preview-file">
          <span className="wb-preview-ext">IMG</span>
          {file.name}
        </span>
        <span className="wb-preview-meta">{formatBytes(file.size)}</span>
        <span className="wb-preview-spacer" />
        <span className="wb-preview-chip">点击放大 · 滚轮缩放 · 拖拽平移</span>
      </PreviewToolbar>
      <div className="wb-preview-stage wb-image-stage">
        <PhotoProvider maskOpacity={0.9} bannerVisible className="wb-photo-provider">
          <PhotoView src={url}>
            <figure className="wb-image-card">
              <img src={url} alt={file.name} className="wb-image-thumb" draggable={false} />
              <figcaption>
                <strong>{file.name}</strong>
                <span>{formatBytes(file.size) || "图片"} · 点击进入全屏预览</span>
              </figcaption>
            </figure>
          </PhotoView>
        </PhotoProvider>
      </div>
    </div>
  );
}
