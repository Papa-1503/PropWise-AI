const COLORS = [
  "bg-rose-600", "bg-orange-600", "bg-amber-600", "bg-emerald-600",
  "bg-teal-600", "bg-sky-600", "bg-indigo-600", "bg-violet-600", "bg-pink-600",
];

function colorForName(name) {
  const str = name || "?";
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  return COLORS[Math.abs(hash) % COLORS.length];
}

function initialsForName(name) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  const first = parts[0]?.[0] || "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase() || "?";
}

export default function Avatar({ name, size = 32, className = "" }) {
  const dim = `${size}px`;
  return (
    <div
      className={`rounded-full text-white font-semibold flex items-center justify-center flex-shrink-0 ${colorForName(name)} ${className}`}
      style={{ width: dim, height: dim, fontSize: size * 0.4 }}
    >
      {initialsForName(name)}
    </div>
  );
}
