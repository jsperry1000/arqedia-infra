import { Linking } from 'react-native';
import { api } from '@/api/client';

/** A memo's PDF, opened in whatever the phone views PDFs with.
 *
 *  GET /memos/{id}/pdf renders it when asked and answers with a link; the
 *  link is handed to the phone, and saving a copy is the viewer's to offer.
 *  The one way the app opens a PDF, wherever it is opened from. */
export async function openMemoPdf(memoId: number): Promise<void> {
  const { url } = await api.memoPdf(memoId);
  await Linking.openURL(url);
}
