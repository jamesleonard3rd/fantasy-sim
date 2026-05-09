import {
  GROUPS,
  firstSectionForGroup,
  groupForSection,
  sectionsForGroup,
  type SectionId,
} from "../sections";

type Props = {
  active: SectionId;
  onChange: (id: SectionId) => void;
  onAdvance: () => void;
};

function TopBar({ active, onChange, onAdvance }: Props) {
  const activeGroup = groupForSection(active);
  const subSections = sectionsForGroup(activeGroup);

  return (
    <header className="topbar">
      <div className="topbar-row topbar-row-main">
        <div className="topbar-left">
          <div className="brand">
            <div className="brand-crest">FS</div>
            <div className="brand-text">
              <div className="brand-title">Fantasy Sim</div>
              <div className="brand-sub">Realm Console</div>
            </div>
          </div>

          <nav className="primary-nav">
            {GROUPS.map((g) => (
              <PrimaryNavItem
                key={g.id}
                label={g.label}
                active={g.id === activeGroup}
                onClick={() => onChange(firstSectionForGroup(g.id))}
              />
            ))}
          </nav>
        </div>

        <div className="topbar-right">
          <div className="day-chip">
            <div className="day-chip-label">Realm Day</div>
            <div className="day-chip-value">001</div>
          </div>
          <button type="button" className="advance-btn" onClick={onAdvance}>
            <span>Refresh State</span>
            <span className="advance-arrow">›</span>
          </button>
        </div>
      </div>

      <div className="topbar-row topbar-row-sub">
        <div className="sub-nav">
          {subSections.map((s) => (
            <SubNavItem
              key={s.id}
              label={s.label}
              active={s.id === active}
              planned={s.status === "planned"}
              onClick={() => onChange(s.id)}
            />
          ))}
        </div>
      </div>
    </header>
  );
}

function PrimaryNavItem({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`primary-nav-item ${active ? "is-active" : ""}`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function SubNavItem({
  label,
  active,
  planned,
  onClick,
}: {
  label: string;
  active: boolean;
  planned: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`sub-nav-item ${active ? "is-active" : ""}`}
      onClick={onClick}
    >
      <span>{label}</span>
      {planned && <span className="badge-soon">soon</span>}
    </button>
  );
}

export default TopBar;
