function legacyCopy(text: string): boolean {
  if (typeof document === 'undefined' || typeof document.execCommand !== 'function') return false;
  const previousFocus = document.activeElement;
  const field = document.createElement('textarea');
  field.value = text;
  field.readOnly = true;
  field.className = 'fixed top-0 opacity-0';
  document.body.append(field);
  field.select();
  try {
    return document.execCommand('copy');
  } finally {
    field.remove();
    if (previousFocus instanceof HTMLElement) previousFocus.focus();
  }
}

interface CopyOptions {
  writeClipboard?: (text: string) => Promise<void>;
  fallback?: (text: string) => boolean;
}

export async function copyText(text: string, options?: CopyOptions): Promise<boolean> {
  const writeClipboard = options?.writeClipboard ?? (
    typeof navigator !== 'undefined' && navigator.clipboard?.writeText
      ? (value: string) => navigator.clipboard.writeText(value)
      : undefined
  );
  if (writeClipboard) {
    try {
      await writeClipboard(text);
      return true;
    } catch {
      // HTTP and denied clipboard permission both have a manual-copy fallback.
    }
  }
  try {
    return (options?.fallback ?? legacyCopy)(text);
  } catch {
    return false;
  }
}
