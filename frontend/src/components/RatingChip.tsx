import { ratingColor, ratingLabel, ratingWeak } from '../lib/rating';
import { ratingChip, ratingDot } from '../styles/workspace.css';

export function RatingChip({ rating }: { rating: string | null }) {
  const color = ratingColor(rating);
  return (
    <span className={ratingChip} style={{ color, backgroundColor: ratingWeak(rating) }}>
      <span className={ratingDot} style={{ backgroundColor: color }} />
      {ratingLabel(rating)}
    </span>
  );
}
