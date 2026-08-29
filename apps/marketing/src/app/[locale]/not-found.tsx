import { Link } from "@/i18n/navigation";

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--background)]">
      <div className="text-center px-6 md:px-[40px]">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/50 mb-8">
          <span className="text-[13px] text-[var(--muted)] tracking-[0.05em] uppercase font-['Manrope',system-ui,sans-serif]">
            404
          </span>
        </div>
        <h1 className="text-[42px] md:text-[54px] font-bold tracking-[-0.03em] leading-[1.1] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
          Page not found
        </h1>
        <p className="text-[17px] text-[var(--muted)] mb-10 max-w-md mx-auto tracking-[-0.01em]">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <Link
          href="/"
          className="inline-flex items-center px-8 py-3 bg-[var(--accent)] text-white rounded-[10px] font-medium text-[15px] hover:bg-[var(--accent-hover)] transition-colors duration-150 btn-press"
        >
          Go home
        </Link>
      </div>
    </div>
  );
}
