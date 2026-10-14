import { BaseCatalogueReview as Review } from '../lib/workflowApi';

export function BaseCatalogueReview({ review }: { review?: Review }) {
  return <>Base catalogue: {review?.status ?? 'unreviewed'}{review?.status === 'reviewed' && <>
    {review.reviewer && <> · {review.reviewer}</>}{review.reviewed_at && <> · {review.reviewed_at}</>}
  </>}</>;
}
