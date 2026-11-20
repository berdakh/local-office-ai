import { useState } from "react";
import { FileText } from "lucide-react";

export default function StarterPicker<T extends { title: string }>({ label, items, onUse, disabled, action = "Use starter" }: {
  label: string; items: readonly T[]; onUse: (item: T) => void; disabled?: boolean; action?: string;
}) {
  const [choice, setChoice] = useState("");
  return (
    <div className="starter-picker">
      <label>{label}
        <select aria-label={label} value={choice} disabled={disabled} onChange={(event) => setChoice(event.target.value)}>
          <option value="">Choose a starter</option>
          {items.map((item) => <option key={item.title} value={item.title}>{item.title}</option>)}
        </select>
      </label>
      <button type="button" disabled={disabled || !choice} onClick={() => {
        const item = items.find((option) => option.title === choice);
        if (item) onUse(item);
      }}><FileText size={15} aria-hidden="true" /> {action}</button>
    </div>
  );
}
