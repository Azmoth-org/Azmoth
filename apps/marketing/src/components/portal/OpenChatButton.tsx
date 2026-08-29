"use client";

export function OpenChatButton({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={() => window.dispatchEvent(new CustomEvent("silkdev:open-chat"))}
      className={className}
    >
      {children}
    </button>
  );
}
