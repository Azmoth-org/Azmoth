import Link from "next/link";

export default function RootNotFound() {
  return (
    <div className="min-h-screen bg-[var(--background)] flex items-center justify-center">
      <div className="text-center max-w-md mx-auto px-8">
        <h1 className="text-[64px] font-bold text-white mb-4 font-['Manrope',system-ui,sans-serif]">
          404
        </h1>
        <p className="text-[var(--muted)] mb-8 text-[17px] tracking-[-0.01em]">
          Page not found
        </p>
        <Link
          href="/"
          className="inline-flex items-center px-6 py-3 bg-[var(--accent)] text-white rounded-[10px] font-medium text-[15px] hover:bg-[var(--accent-hover)] transition-colors duration-150 btn-press"
        >
          Go Home
        </Link>
      </div>
    </div>
  );
}
