/** Leaflet treats strings as HTML. Addresses must always enter through textContent. */
export function mapPopup(title: string, ...lines: string[]): HTMLElement {
  const container = document.createElement('div');
  container.dir = 'rtl';
  container.className = 'text-start font-sans text-sm';
  const heading = document.createElement('strong');
  heading.textContent = title;
  container.appendChild(heading);
  for (const line of lines) {
    const paragraph = document.createElement('p');
    paragraph.textContent = line;
    container.appendChild(paragraph);
  }
  return container;
}
