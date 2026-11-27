import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 15, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    ...props,
  };
}

export function WorkspaceIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 8.5 12 4l8 4.5v7L12 20l-8-4.5z" />
      <path d="M4 8.5 12 13l8-4.5M12 13v7" />
    </svg>
  );
}

export function ChatIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M20 12a7.5 7.5 0 0 1-10.9 6.7L4 20l1.3-4.1A7.5 7.5 0 1 1 20 12Z" />
      <path d="M8.5 11.5h7M8.5 14.5h4.5" />
    </svg>
  );
}

export function AgentIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="4.5" y="7" width="15" height="12" rx="3" />
      <path d="M12 3v4M8.5 12.5h.01M15.5 12.5h.01M9 16h6" />
    </svg>
  );
}

export function ApiIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M9 8.5 5.5 12 9 15.5M15 8.5 18.5 12 15 15.5" />
      <path d="M13.5 6.5 10.5 17.5" />
    </svg>
  );
}

export function FileIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M6.5 3.5h7l4 4v13h-11z" />
      <path d="M13.5 3.5v4h4M9 13h6M9 16.5h4.5" />
    </svg>
  );
}

export function FolderIcon(props: IconProps & { open?: boolean }) {
  const { open, ...rest } = props;
  return (
    <svg {...base(rest)}>
      {open ? (
        <>
          <path d="M3.5 8.5V6.5h6l2 2h9l-2.5 11h-14.5z" />
          <path d="M3.5 10.5h17" />
        </>
      ) : (
        <path d="M3.5 7.5v-1h6l2 2h9v11h-17z" />
      )}
    </svg>
  );
}

export function ChevronIcon(props: IconProps & { open?: boolean }) {
  const { open, ...rest } = props;
  return (
    <svg {...base(rest)} style={{ transform: open ? "rotate(90deg)" : undefined, ...rest.style }}>
      <path d="m9 6 6 6-6 6" />
    </svg>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </svg>
  );
}

export function PencilIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="m4 20 4.2-1 10-10a2.1 2.1 0 0 0-3-3l-10 10z" />
      <path d="m13.5 6.5 4 4" />
    </svg>
  );
}

export function GripIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01" strokeWidth={2.6} />
    </svg>
  );
}

export function PanelIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <path d="M14.5 4.5v15" />
    </svg>
  );
}

export function TerminalIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3" y="4.5" width="18" height="15" rx="2.5" />
      <path d="m7 9 3 3-3 3M12.5 15h4.5" />
    </svg>
  );
}

export function DiffIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M6 4v16M18 4v16M6 8h5M13 16h5M8.5 5.5 6 8l2.5 2.5M15.5 18.5 18 16l-2.5-2.5" />
    </svg>
  );
}

export function RefreshIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M20 11a8 8 0 1 0-2.3 6.3" />
      <path d="M20 5v6h-6" />
    </svg>
  );
}

export function ExternalIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M14 4h6v6M20 4l-9 9" />
      <path d="M19 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-12A1.5 1.5 0 0 1 4 18.5v-12A1.5 1.5 0 0 1 5.5 5H10" />
    </svg>
  );
}

export function LayoutIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <path d="M9 4.5v15M15 4.5v15M3.5 10h5.5M9 14h6" />
    </svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </svg>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 4 2.8 20h18.4z" />
      <path d="M12 9.5v4.5M12 17.2h.01" />
    </svg>
  );
}

export function EyeIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M2.5 12S6 6 12 6s9.5 6 9.5 6S18 18 12 18 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

export function SettingsIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 2.8v2.1M12 19.1v2.1M4.5 4.5l1.5 1.5M18 18l1.5 1.5M2.8 12h2.1M19.1 12h2.1M4.5 19.5 6 18M18 6l1.5-1.5" />
    </svg>
  );
}

export function PaletteIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 3a9 9 0 1 0 0 18h1.2a2 2 0 0 0 0-4h-.7a1.8 1.8 0 0 1 0-3.6H16a5 5 0 0 0 5-5C21 5.4 16.9 3 12 3Z" />
      <path d="M7.5 10h.01M9.5 6.8h.01M14 6.5h.01" strokeWidth={2.4} />
    </svg>
  );
}

export function SkillsIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="m12 3 1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z" />
      <path d="m18.5 15 .8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" />
    </svg>
  );
}

export function PlugIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M9 3v5M15 3v5M7 8h10v3a5 5 0 0 1-10 0zM12 16v5" />
    </svg>
  );
}

export function PhoneIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="7" y="2.5" width="10" height="19" rx="2.5" />
      <path d="M10.5 5.5h3M11 18.5h2" />
    </svg>
  );
}

export function TrashIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4.5 7h15M9 7V4.5h6V7M6.5 7l.9 13h9.2l.9-13M10 11v5.5M14 11v5.5" />
    </svg>
  );
}

export function FileTypeIcon({ ext, size = 16 }: { ext?: string; size?: number }) {
  switch (ext) {
    case "docx":
    case "doc":
      return (
        <svg {...base({ size })}>
          <path d="M6.5 3.5h7l4 4v13h-11z" />
          <path d="M13.5 3.5v4h4M9 12h6M9 15h4.5" />
        </svg>
      );
    case "pptx":
    case "ppt":
      return (
        <svg {...base({ size })}>
          <rect x="3.5" y="4.5" width="17" height="12" rx="1.8" />
          <path d="M12 16.5V20M9 20h6M7.5 12.5l2.5-4 2 3 1.5-2 2.5 3" />
        </svg>
      );
    case "pdf":
      return (
        <svg {...base({ size })}>
          <path d="M6.5 3.5h7l4 4v13h-11z" />
          <path d="M13.5 3.5v4h4M8.5 16.5v-5h2a1.5 1.5 0 0 1 0 3h-2M14 16.5v-5h2.5" />
        </svg>
      );
    case "xlsx":
    case "xls":
    case "csv":
      return (
        <svg {...base({ size })}>
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <path d="M4 9.5h16M4 14.5h16M9.5 4v16M14.5 4v16" />
        </svg>
      );
    case "png":
    case "jpg":
    case "jpeg":
    case "webp":
    case "gif":
    case "bmp":
    case "svg":
      return (
        <svg {...base({ size })}>
          <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
          <circle cx="9" cy="9.5" r="1.4" />
          <path d="m5 17 5-5 4 4 2-2 3 3" />
        </svg>
      );
    case "diff":
    case "patch":
      return <DiffIcon size={size} />;
    case "md":
    case "txt":
      return (
        <svg {...base({ size })}>
          <path d="M6.5 3.5h7l4 4v13h-11z" />
          <path d="M13.5 3.5v4h4M8.5 11h7M8.5 14h7M8.5 17h4" />
        </svg>
      );
    default:
      return <FileIcon size={size} />;
  }
}
