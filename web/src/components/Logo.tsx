// The mark: a main track and a branch leaving it at a yellow point, the transfer.
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <rect width="64" height="64" rx="14" fill="var(--petrol)" />
      <path d="M22 54V10" stroke="#fff" strokeWidth="5.5" strokeLinecap="round" fill="none" />
      <path d="M44 54V44C44 30 36 22 22 22" stroke="#fff" strokeWidth="5.5" strokeLinecap="round" fill="none" />
      <circle cx="22" cy="22" r="7.5" fill="var(--signal)" stroke="var(--petrol)" strokeWidth="3" />
    </svg>
  );
}
