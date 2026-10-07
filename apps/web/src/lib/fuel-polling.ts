/** Auto-resume each inquiry once per visit; manual retry remains explicit. */
export function nextUnobservedInquiry<T extends { id: number; status: string }>(
  inquiries: readonly T[], observed: ReadonlySet<number>, activeId: number | null,
): T | undefined {
  if (activeId !== null) return undefined;
  return inquiries.find(item => !observed.has(item.id) && ['pending', 'processing', 'running'].includes(item.status));
}
