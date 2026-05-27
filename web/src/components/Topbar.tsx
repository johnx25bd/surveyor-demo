import osLogo from "../assets/os-logo.svg";
import type { Mood } from "../App";

interface Props {
  queryTitle: string | null;
  mood: Mood;
  onToggleMood(): void;
}

// The civic top bar: OS lockup on the left, the live query in the centre, controls on the right.
export function Topbar({ queryTitle, mood, onToggleMood }: Props) {
  return (
    <header className="sv-topbar">
      <div className="sv-topbar-l">
        <img src={osLogo} alt="Ordnance Survey" className="sv-os" />
        <span className="sv-divider" aria-hidden="true" />
        <div className="sv-brand">
          <span className="sv-brand-mark" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <path d="M4 18l5-8 4 5 3-3 4 6H4z" fill="currentColor" />
              <circle cx="17" cy="6" r="2" fill="currentColor" />
            </svg>
          </span>
          <span className="sv-brand-name">Surveyor</span>
          <span className="sv-brand-tag">v0.1</span>
        </div>
      </div>

      <div className="sv-topbar-c">
        {queryTitle && <span className="sv-query-title">{queryTitle}</span>}
      </div>

      <div className="sv-topbar-r">
        <button
          className="sv-ghostbtn"
          onClick={onToggleMood}
          aria-label={`Switch to ${mood === "dark" ? "light" : "night"} basemap`}
        >
          {mood === "dark" ? "Light" : "Night"}
        </button>
        <div className="sv-avatar sv-avatar--user" aria-label="Account">
          JD
        </div>
      </div>
    </header>
  );
}
