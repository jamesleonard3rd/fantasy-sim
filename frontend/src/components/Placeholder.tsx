type Props = {
  title: string;
  description?: string;
};

function Placeholder({
  title,
  description = "This area is reserved for a future part of the simulation. Once the schema and API endpoints are in place, this view will plug right in.",
}: Props) {
  return (
    <div className="placeholder">
      <div className="placeholder-mark">Coming soon</div>
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}

export default Placeholder;
