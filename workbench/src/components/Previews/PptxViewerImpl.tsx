import "pptx-react-viewer/styles";
import { PowerPointViewer } from "pptx-react-viewer";

const viewerTheme = {
  colors: {
    background: "#14151a",
    foreground: "#ece8df",
    card: "#1b1c21",
    cardForeground: "#ece8df",
    popover: "#1b1c21",
    popoverForeground: "#ece8df",
    primary: "#e2b857",
    primaryForeground: "#17181d",
    secondary: "#24252b",
    secondaryForeground: "#ece8df",
    muted: "#24252b",
    mutedForeground: "#98938a",
    accent: "#2b2518",
    accentForeground: "#f2d492",
    destructive: "#c4644f",
    destructiveForeground: "#fff5f0",
    border: "#2a2b31",
    input: "#2a2b31",
    ring: "#e2b857",
  },
  radius: "10px",
  cssVars: {
    "--pptx-font-sans": "'Microsoft YaHei', 'PingFang SC', sans-serif",
  },
} as const;

export default function PptxViewerImpl({
  bytes,
  fileName,
}: {
  bytes: Uint8Array;
  fileName: string;
}) {
  return (
    <div className="wb-pptx-viewer-host">
      <PowerPointViewer
        content={bytes}
        fileName={fileName}
        canEdit={false}
        showToolbar={false}
        showThumbnails={false}
        showCompatibilityToasts={false}
        inspectorInitiallyOpen={false}
        customization={{
          hiddenPanels: [
            "statusBar",
            "slidesPane",
            "inspector",
            "notes",
            "quickAccessToolbar",
            "titleBar",
            "selectionPane",
            "findReplace",
            "accessibilityPane",
            "comparePane",
          ],
        }}
        googleFonts={false}
        allowExternalContent={false}
        theme={viewerTheme}
        className="wb-pptx-viewer"
      />
    </div>
  );
}
