import { useState } from "react";
import { Sparkles } from "lucide-react";

const MESSAGES = [
  "You're keeping roofs over heads today — that matters.",
  "Every ticket you close is someone's home feeling right again.",
  "Small fixes, big peace of mind. Nice work.",
  "Residents notice the care you put in, even when they don't say it.",
  "You've got this. One unit, one task at a time.",
  "A well-run property starts with someone who shows up. That's you.",
  "Take a breath — you're doing better than you think.",
  "Great property management is quiet excellence. Keep going.",
];

const STYLES = [
  "from-indigo-500 to-fuchsia-500",
  "from-teal-500 to-emerald-500",
  "from-amber-500 to-orange-500",
  "from-sky-500 to-indigo-500",
  "from-rose-500 to-pink-500",
];

export default function AffirmationBanner() {
  const [message] = useState(() => MESSAGES[Math.floor(Math.random() * MESSAGES.length)]);
  const [gradient] = useState(() => STYLES[Math.floor(Math.random() * STYLES.length)]);

  return (
    <div className={`bg-gradient-to-r ${gradient} text-white rounded-xl px-4 py-3 mb-5 flex items-center gap-2.5 shadow-sm animate-fade-in`}>
      <Sparkles size={18} className="flex-shrink-0" />
      <p className="text-sm font-medium">{message}</p>
    </div>
  );
}
