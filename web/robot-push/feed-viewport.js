// Reserve six complete ordinary rows, including wrapped warning text.
export function ordinaryViewportHeight(rows, padding = 0) {
  let height = 400;
  for (let i = 0; i < rows.length; i++) {
    const last = rows[Math.min(i + 5, rows.length - 1)];
    height = Math.max(height, Math.ceil(last.bottom - rows[i].top + padding + 2));
  }
  return height;
}
