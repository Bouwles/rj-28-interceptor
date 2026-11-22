// Stand-in drawing set, used only while src/data/sheets.json does not exist.
// Regenerate with `npm run placeholder`.

import { normaliseSheets } from '../data';
import type { SheetSet } from '../data/types';
import index from './placeholder/sheets.json';

const files = import.meta.glob('./placeholder/*.svg', {
  query: '?url',
  import: 'default',
  eager: true,
}) as Record<string, string>;

export function placeholderSheetSet(): SheetSet | null {
  const sheets = normaliseSheets(
    index,
    (file) => {
      const url = files[`./placeholder/${file}`];
      return url ? { url, key: `dev/${file}` } : null;
    },
    true,
  );
  return sheets.length ? { sheets, pdfUrl: null, revision: null, placeholder: true } : null;
}
