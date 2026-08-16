/**
 * One authored icon set: 1.6px stroke, 24px grid, round caps, no fills.
 * Keeping them here rather than pulling a library guarantees a single stroke
 * weight across the console — mixed icon vocabularies are the fastest way to
 * make a dense UI feel assembled rather than designed.
 */

type IconProps = {
  size?: number;
  className?: string;
};

function base(size: number, className?: string) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className,
    "aria-hidden": true,
  };
}

export function IconPin({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M12 21s7-5.4 7-11a7 7 0 1 0-14 0c0 5.6 7 11 7 11Z" />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  );
}

export function IconLayers({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 13 9 5 9-5" />
    </svg>
  );
}

export function IconDownload({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M12 3v11" />
      <path d="m7.5 10.5 4.5 4 4.5-4" />
      <path d="M4 20h16" />
    </svg>
  );
}

export function IconImage({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <rect x="3" y="4.5" width="18" height="15" rx="2.5" />
      <circle cx="8.5" cy="10" r="1.6" />
      <path d="m4 17 4.5-4.5L13 17l3-3 4 4" />
    </svg>
  );
}

export function IconTarget({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22" />
    </svg>
  );
}

export function IconFlag({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M5.5 21V4" />
      <path d="M5.5 5h11l-1.8 3.5L16.5 12h-11" />
    </svg>
  );
}

export function IconExternal({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M14 4h6v6" />
      <path d="m20 4-8.5 8.5" />
      <path d="M19 14.5V19a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V6.5A1.5 1.5 0 0 1 5 5h4.5" />
    </svg>
  );
}

export function IconSun({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

export function IconMoon({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />
    </svg>
  );
}

export function IconSearch({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4.5 4.5" />
    </svg>
  );
}

export function IconClose({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

export function IconAlert({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M12 4.5 2.8 20h18.4L12 4.5Z" />
      <path d="M12 10v4" />
      <path d="M12 17.2v.1" />
    </svg>
  );
}

export function IconSettings({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 14.5a1.7 1.7 0 0 0 .35 1.9l.05.05a2 2 0 1 1-2.85 2.85l-.05-.05a1.7 1.7 0 0 0-1.9-.35 1.7 1.7 0 0 0-1.05 1.57V21a2 2 0 0 1-4 0v-.15a1.7 1.7 0 0 0-1.1-1.57 1.7 1.7 0 0 0-1.9.35l-.05.05A2 2 0 1 1 3.7 16.4l.05-.05a1.7 1.7 0 0 0 .35-1.9 1.7 1.7 0 0 0-1.57-1.05H3a2 2 0 0 1 0-4h.15A1.7 1.7 0 0 0 4.7 8.3a1.7 1.7 0 0 0-.35-1.9l-.05-.05A2 2 0 1 1 7.15 3.5l.05.05a1.7 1.7 0 0 0 1.9.35H9.2a1.7 1.7 0 0 0 1.05-1.57V2a2 2 0 0 1 4 0v.15a1.7 1.7 0 0 0 1.05 1.57 1.7 1.7 0 0 0 1.9-.35l.05-.05a2 2 0 1 1 2.85 2.85l-.05.05a1.7 1.7 0 0 0-.35 1.9v.05a1.7 1.7 0 0 0 1.57 1.05H21a2 2 0 0 1 0 4h-.15a1.7 1.7 0 0 0-1.45 1.05Z" />
    </svg>
  );
}

export function IconChart({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M3 3v16.5a1.5 1.5 0 0 0 1.5 1.5H21" />
      <path d="M7.5 15.5v-3" />
      <path d="M12 15.5v-7" />
      <path d="M16.5 15.5v-5" />
    </svg>
  );
}

/* Sort indicators. Three states, because "unsorted" and "sorted ascending" have
   to be tellable apart at a glance in a header row — an arrow that only appears
   when active leaves you guessing whether the column can be sorted at all. */

export function IconSortNone({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M8 9l4-4 4 4" />
      <path d="M8 15l4 4 4-4" />
    </svg>
  );
}

export function IconSortAsc({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M6 14l6-7 6 7" />
    </svg>
  );
}

export function IconSortDesc({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M6 10l6 7 6-7" />
    </svg>
  );
}

export function IconFilter({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M3 5h18l-7 8v6l-4-2v-4z" />
    </svg>
  );
}

export function IconCheck({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M4 12.5l5 5L20 6.5" />
    </svg>
  );
}

export function IconCommand({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M9 6a3 3 0 10-3 3h12a3 3 0 10-3-3v12a3 3 0 103-3H6a3 3 0 10 3 3z" />
    </svg>
  );
}

export function IconArrowRight({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <path d="M5 12h13" />
      <path d="M13 6l6 6-6 6" />
    </svg>
  );
}

export function IconClock({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}

export function IconDatabase({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size, className)}>
      <ellipse cx="12" cy="6" rx="7.5" ry="3" />
      <path d="M4.5 6v12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6" />
      <path d="M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3" />
    </svg>
  );
}
